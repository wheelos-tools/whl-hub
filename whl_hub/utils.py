"""
A general-purpose file utility toolkit providing download, extraction, user interaction, and other features.
This module can exist independently and does not depend on other modules in the project, making it easy to reuse.
"""
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional
import zipfile
import requests

# --- Constant Definitions ---
DOWNLOAD_TMP_DIR = Path("./temp_downloads")
YES_CHOICES = {'yes', 'y'}
NO_CHOICES = {'no', 'n'}


def _progress(prefix: str, cur: int, total: int, bar_size: int = 50) -> None:
    """
    Display a dynamic progress bar in the terminal.

    Args:
      prefix (str): Prefix text for the progress bar.
      cur (int): Current progress.
      total (int): Total progress.
      bar_size (int): Width of the progress bar.
    """
    if total == 0:
        percent = 1.0
    else:
        percent = cur / total

    cur_p = int(percent * bar_size)
    # Use f-string for better readability.
    progress_bar = f"[{'#' * cur_p}{'.' * (bar_size - cur_p)}]"
    status = f"{prefix} {progress_bar} {cur}/{total} ({percent:.1%})"
    sys.stdout.write(status + '\r')
    sys.stdout.flush()


def resolve_asset_path(path_or_name: str, config) -> Optional[Path]:
    """
    Resolves the final path to an asset based on a 3-step priority.

    Priority Order:
    1. If it's a full URL, download it directly.
    2. If it's not a URL or a local file, try to treat it as a name,
       concatenate it with the CDN template, and download it.
    3. If all else fails or is not applicable, treat it as a local file path.

    Args:
        path_or_name: The user's input string (URL, name, or local path).
        config: A configuration object containing the cdn_url_template.

    Returns:
        A Path object to the local asset after successful retrieval,
        or None if all attempts fail.
    """
    logging.info(f"Resolving asset path for: '{path_or_name}'...")

    # --- Priority 1: Check if it is a full URL ---
    if path_or_name.startswith(('http://', 'https://')):
        logging.info("Input recognized as a full URL. Attempting to download...")
        try:
            downloaded_path = download_from_url(path_or_name)
            if downloaded_path and downloaded_path.exists():
                logging.info(f"Successfully retrieved from URL: {downloaded_path}")
                return downloaded_path
            else:
                logging.error(f"Download failed from explicit URL '{path_or_name}'. Aborting asset resolution.")
                return None
        except Exception as e:
            # Any exception during download from a user-provided URL is a fatal error for this process.
            logging.error(f"An error occurred while downloading from URL '{path_or_name}': {e}", exc_info=True)
            return None

    # --- Priority 2: Try to download from CDN as a name ---
    # This step is only executed if the input is not an existing local file.
    local_path_check = Path(path_or_name)
    if not local_path_check.exists():
        if hasattr(config, 'cdn_url_template') and config.cdn_url_template:
            cdn_url = config.cdn_url_template.format(path_or_name)
            logging.info(f"Input is not a local file. Attempting to download from CDN as a name: {cdn_url}")
            try:
                downloaded_path = download_from_url(cdn_url)
                if downloaded_path and downloaded_path.exists():
                    logging.info(f"Successfully downloaded from CDN to: {downloaded_path}")
                    return downloaded_path
                else:
                    logging.warning(f"Failed to download from CDN URL '{cdn_url}'. Will now check for local file.")
            except Exception as e:
                logging.error(f"An error occurred while downloading from CDN URL '{cdn_url}': {e}")
        else:
            logging.info("CDN template not configured, skipping name resolution step.")

    # --- Priority 3: Finally, treat it as a local file path ---
    logging.info(f"Trying to treat input as a local file path: '{local_path_check}'")
    if local_path_check.exists() and local_path_check.is_file():
        logging.info("Successfully located the local file.")
        return local_path_check

    logging.error(f"Could not resolve asset '{path_or_name}'. It is not a downloadable name from the CDN or an existing local file.")
    return None


def download_from_url(url: str, download_dir: str = "/tmp/whl_downloads") -> Optional[Path]:
    """
    Downloads a file from a URL with resume capability and handles 416 errors.
    """
    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)
    filename = Path(url.split('/')[-1])
    local_file = download_path / filename

    try:
        print(f"Starting download from: {url}")
        resume_header = {}
        if local_file.exists():
            local_size = local_file.stat().st_size
            resume_header = {'Range': f'bytes={local_size}-'}
            logging.info(f"File already exists, attempting to resume from {local_size} bytes.")

        with requests.get(url, stream=True, headers=resume_header, timeout=30) as r:
            # Handle the 416 error specifically
            if r.status_code == 416:
                logging.warning("Received 416 'Range Not Satisfiable'. The local file may be complete or corrupt. Restarting download from scratch.")
                # Delete the file and try again without the Range header
                local_file.unlink()
                with requests.get(url, stream=True, timeout=30) as r_fresh:
                    r_fresh.raise_for_status()
                    with open(local_file, 'wb') as f:
                        for chunk in r_fresh.iter_content(chunk_size=8192):
                            f.write(chunk)
                return local_file

            r.raise_for_status() # Raise exception for other non-2xx status codes

            # The mode depends on whether we are resuming or starting fresh
            mode = 'ab' if 'Range' in resume_header and r.status_code == 206 else 'wb'
            with open(local_file, mode) as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        print(f"✅ Download complete: {local_file}")
        return local_file

    except requests.exceptions.RequestException as e:
        logging.error(f"Download failed: {e}", exc_info=True)
        if local_file.exists() and 'Range' not in resume_header:
             local_file.unlink()
        return None


def unzip_file(zip_path: Path, extract_to: Path) -> Optional[Path]:
    """
    Extracts a zip archive to a specified directory.
    Returns the path to the extraction directory on success, None on failure.
    """
    try:
        if extract_to.exists():
            logging.warning(f"Target path {extract_to} already exists, clearing it.")
            shutil.rmtree(extract_to)
        extract_to.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)

        logging.info(f"Successfully extracted {zip_path} to {extract_to}")
        return extract_to
    except (zipfile.BadZipFile, FileNotFoundError) as e:
        logging.error(f"Failed to unzip file: {e}", exc_info=True)
        return None


def user_confirmation(question: str) -> bool:
    """
    Request command-line confirmation from the user.

    Args:
      question (str): The prompt question to display to the user.

    Returns:
      bool: Returns True if the user confirms, otherwise False.
    """
    prompt = f"{question} [{'/'.join(YES_CHOICES)}|{'|'.join(NO_CHOICES)}]: "
    for _ in range(3):
        user_input = input(prompt).lower().strip()
        if user_input in YES_CHOICES:
            return True
        if user_input in NO_CHOICES:
            return False
        print("Invalid input, please enter 'yes' or 'no' (or 'y'/'n').")
    logging.warning("No valid confirmation received, operation aborted.")
    return False
