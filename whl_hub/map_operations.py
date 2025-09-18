import logging
import os
import requests
import shutil
import sys
from pathlib import Path

from .meta import MapMeta

# --- Constant Definition ---
WORKSPACE_PATH = os.getenv('APOLLO_ROOT_DIR', '/apollo')
MAP_INSTALL_ROOT = Path(WORKSPACE_PATH) / "modules/map/data"
MAP_META_FILE_NAME = "map_meta"
DOWNLOAD_TMP_DIR = Path("/tmp/")
UNZIP_TMP_DIR = Path("/tmp/whl_hub_map_extract")


def _progress(prefix, cur, total):
    """Display download progress bar."""
    bar_size = 50
    if total == 0: # Avoid division by zero
        cur_p = bar_size
    else:
        cur_p = int(cur / total * bar_size)
    print(f"{prefix}[{'#'*cur_p}{'.'*(bar_size - cur_p)}] {cur}/{total}", end='\r', file=sys.stdout, flush=True)

def _download_from_url(url):
    """Download file from the given URL and display progress."""
    local_filename = url.split('/')[-1]
    download_file = DOWNLOAD_TMP_DIR / local_filename

    if download_file.is_file():
        logging.warning(f"File already cached at {download_file}. Using cached version.")
        return str(download_file)

    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_length = int(r.headers.get('content-length', 0))
            chunk_size = 8192
            with open(download_file, 'wb') as f:
                for i, chunk in enumerate(r.iter_content(chunk_size=chunk_size)):
                    f.write(chunk)
                    _progress("Downloading:", i, total_length // chunk_size)
        print() # New line
        logging.info(f"Successfully downloaded to {download_file}")
        return str(download_file)
    except requests.exceptions.RequestException as e:
        logging.error(f"Download failed: {e}")
        return None

def _unzip_file(file_path, extract_path):
    """Unzip file to the specified path."""
    if not Path(file_path).is_file():
        logging.error(f"Archive file not found: {file_path}")
        return False
    if extract_path.exists():
        shutil.rmtree(extract_path) # Clean up old temp files

    try:
        shutil.unpack_archive(file_path, extract_path)
        logging.info(f"Successfully unpacked {file_path} to {extract_path}")
        return True
    except (ValueError, shutil.ReadError) as e:
        logging.error(f"Failed to unpack archive {file_path}. Unsupported format or corrupt file. Error: {e}")
        return False

def _user_confirmation(question):
    """Request command-line confirmation from the user."""
    yes_choices = {'yes', 'y'}
    no_choices = {'no', 'n'}
    for _ in range(3): # Try at most 3 times
        user_input = input(question).lower()
        if user_input in yes_choices:
            return True
        if user_input in no_choices:
            return False
    logging.warning("No valid input provided. Aborting.")
    return False

def _join_meta_file(meta_path):
    """Find metadata file (.yaml or .yml) in the directory."""
    for ext in ['.yaml', '.yml']:
        meta_file = Path(meta_path) / f"{MAP_META_FILE_NAME}{ext}"
        if meta_file.is_file():
            return meta_file
    return None


def install(path, skip, registry):
    """
    Core logic for installing a map.
    Returns metadata dict on success, None on failure.
    """
    logging.info(f"Starting map installation from: {path}")

    # 1. Handle path: support URL or local path
    is_url = path.startswith('http://') or path.startswith('https://')
    if is_url:
        archive_path = _download_from_url(path)
        if not archive_path:
            return None
    elif Path(path).is_file():
        archive_path = path
    else:
        logging.error(f"Input path '{path}' is not a valid URL or local file.")
        return None

    # 2. Unzip to temp directory
    if not _unzip_file(archive_path, UNZIP_TMP_DIR):
        return None

    # 3. Parse metadata
    # Assume after extraction, the metadata file is at the top level of the extracted directory
    meta_file = _join_meta_file(UNZIP_TMP_DIR)
    if not meta_file:
        logging.error(f"Meta file '{MAP_META_FILE_NAME}.yaml/yml' not found in the root of the archive!")
        shutil.rmtree(UNZIP_TMP_DIR)
        return None

    map_meta = MapMeta()
    if not map_meta.parse_from(meta_file):
        logging.error(f"Failed to parse map meta file: {meta_file}")
        shutil.rmtree(UNZIP_TMP_DIR)
        return None

    # 4. Check for conflicts and perform installation
    map_name = map_meta.name
    if not map_name:
        logging.error("Map name is missing in the meta file. Cannot install.")
        shutil.rmtree(UNZIP_TMP_DIR)
        return None

    install_path = MAP_INSTALL_ROOT / map_name

    if install_path.exists():
        if skip:
            logging.warning(f"Skipped install: Map '{map_name}' already exists at {install_path}.")
            shutil.rmtree(UNZIP_TMP_DIR)
            return None

        question = f"Map '{map_name}' already exists. Do you want to override it? [y/n]: "
        if not _user_confirmation(question):
            shutil.rmtree(UNZIP_TMP_DIR)
            return None

        logging.info(f"Removing existing map at {install_path} to override.")
        shutil.rmtree(install_path)

    # 5. Move to final directory
    try:
        shutil.move(str(UNZIP_TMP_DIR), str(install_path))
        print(f"✅ Successfully installed map '{map_name}' to {install_path}.")
    except Exception as e:
        logging.error(f"Failed to move map data to final destination: {e}")
        if UNZIP_TMP_DIR.exists(): shutil.rmtree(UNZIP_TMP_DIR)
        if install_path.exists(): shutil.rmtree(install_path)
        return None

    # 6. Return metadata to AssetManager
    metadata = map_meta.to_dict()
    metadata['install_path'] = str(install_path)
    return metadata

def remove(asset_name, metadata):
    """Uninstall map, return True on success, False on failure."""
    install_path = Path(metadata.get('install_path'))
    if not install_path.exists():
        logging.warning(f"Map '{asset_name}' not found at expected path {install_path}. It might have been manually removed.")
        return True

    question = f"Are you sure you want to permanently remove map '{asset_name}' from {install_path}? [y/n]: "
    if not _user_confirmation(question):
        logging.warning(f"Removal of '{asset_name}' cancelled.")
        return False

    try:
        shutil.rmtree(install_path)
        print(f"✅ Successfully removed map '{asset_name}'.")
        return True
    except OSError as e:
        logging.error(f"Error removing directory {install_path}: {e}")
        return False

def info(asset_name, metadata):
    """Display map information."""
    print(f"--- Info for Map: {asset_name} ---")
    for key, value in metadata.items():
        print(f"  {str(key).replace('_', ' ').title():<15}: {value}")
