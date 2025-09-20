# -*- coding: utf-8 -*-
"""
Manages the installation, removal, and querying of multiple independent high-definition maps.
Each map is installed in its own subdirectory under the main map data directory.
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional


from whl_hub.meta import MapMeta
from whl_hub.utils import download_from_url, unzip_file, user_confirmation

# --- Configuration ---
WORKSPACE_PATH = Path(os.getenv('APOLLO_ROOT_DIR', '/apollo'))
MAP_INSTALL_ROOT = WORKSPACE_PATH / "modules/map/data"
MAP_META_FILENAME = "map_meta"
UNZIP_TMP_DIR = Path("/tmp/whl_hub_map_extract")

def _find_meta_file(search_path: Path) -> Optional[Path]:
    """Find map_meta.yaml/yml file in the directory."""
    for ext in ['.yaml', '.yml']:
        meta_file = search_path / f"{MAP_META_FILENAME}{ext}"
        if meta_file.is_file():
            return meta_file
    return None


def install(path: str, skip_if_exists: bool) -> Optional[Dict[str, Any]]:
    """
    Install a new, named map into its own directory.

    Args:
        path: URL or local file path pointing to the map .zip archive.
        skip_if_exists: If True, skip installation when a map with the same name already exists.

    Returns:
        Returns the map's metadata dictionary on success, or None on failure.
    """
    if UNZIP_TMP_DIR.exists(): shutil.rmtree(UNZIP_TMP_DIR)
    UNZIP_TMP_DIR.mkdir(parents=True)

    try:
        # --- Phase 1: Download and extract ---
        is_url = path.startswith(('http://', 'https://'))
        archive_path = download_from_url(path) if is_url else Path(path)
        if not archive_path or not archive_path.exists():
            logging.error(f"Map archive not found: '{path}'")
            return None
        if not unzip_file(archive_path, UNZIP_TMP_DIR):
            return None

        # --- Phase 2: Parse metadata and determine install path ---
        meta_file = _find_meta_file(UNZIP_TMP_DIR)
        if not meta_file:
            logging.error(f"Meta file '{MAP_META_FILENAME}.yaml/yml' not found in archive!")
            return None

        map_meta = MapMeta()
        if not map_meta.parse_from(meta_file):
            return None

        map_name = getattr(map_meta, 'name', None)
        if not map_name:
            logging.error("Missing 'name' in meta file. Cannot determine install directory.")
            return None

        install_path = MAP_INSTALL_ROOT / map_name

        # --- Phase 3: Check for conflicts and get confirmation ---
        if install_path.exists():
            if skip_if_exists:
                logging.warning(f"Skip installation: Map '{map_name}' already exists at {install_path}.")
                return None

            question = f"Map '{map_name}' already exists. Overwrite? [y/n]: "
            if not user_confirmation(question):
                logging.warning("Installation cancelled by user.")
                return None
            shutil.rmtree(install_path)

        # --- Phase 4: Perform installation ---
        content_source_path = meta_file.parent
        shutil.move(str(content_source_path), str(install_path))

        print(f"✅ Successfully installed map '{map_name}' to {install_path}.")

        metadata = map_meta.to_dict()
        metadata['install_path'] = str(install_path)
        return metadata

    finally:
        if UNZIP_TMP_DIR.exists():
            shutil.rmtree(UNZIP_TMP_DIR)

def remove(map_name: str, metadata: Dict[str, Any]) -> bool:
    """
    Remove a specific map by name.
    The metadata parameter is accepted for interface compatibility but not used.
    """
    if not map_name:
        logging.error("Map name must be provided to remove a specific map.")
        return False

    install_path = MAP_INSTALL_ROOT / map_name

    if not install_path.exists():
        logging.warning(f"Cannot remove: Map '{map_name}' not found at '{install_path}'. It may have already been removed.")
        return True

    question = f"Are you sure you want to remove map '{map_name}' from '{install_path}'? [y/n]: "
    if not user_confirmation(question):
        logging.warning(f"Operation to remove map '{map_name}' was cancelled.")
        return False

    try:
        shutil.rmtree(install_path)
        print(f"🗑️ Successfully removed map '{map_name}'.")
        return True
    except OSError as e:
        logging.error(f"Failed to remove directory {install_path}: {e}", exc_info=True)
        return False

def info(map_name: str, metadata: Dict[str, Any]) -> None:
    """Display information for a specific installed map."""
    install_path = MAP_INSTALL_ROOT / map_name
    if not install_path.exists():
        print(f"Map '{map_name}' is not installed.")
        return

    # Use the passed-in metadata directly, no need to parse from file again
    print(f"--- Map Info: {map_name} ---")
    for key, value in metadata.items():
        print(f"  {key.replace('_', ' ').title():<15}: {value}")
