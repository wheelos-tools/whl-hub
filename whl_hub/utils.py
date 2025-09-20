"""
A general-purpose file utility toolkit providing download, extraction, user interaction, and other features.
This module can exist independently and does not depend on other modules in the project, making it easy to reuse.
"""
import logging
import shutil
import sys
from pathlib import Path
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
  # Robustness: Handle the case where total is 0 to prevent division by zero.
  if total == 0:
    percent = 1.0
  else:
    percent = cur / total

  cur_p = int(percent * bar_size)
  # Use f-string for better readability.
  progress_bar = f"[{'#' * cur_p}{'.' * (bar_size - cur_p)}]"
  # Add percentage display for better user experience.
  status = f"{prefix} {progress_bar} {cur}/{total} ({percent:.1%})"
  # Use sys.stdout.write and control refresh to achieve single-line dynamic refresh.
  sys.stdout.write(status + '\r')
  sys.stdout.flush()


def download_from_url(url: str) -> Path | None:
  """
  Download a file from the given URL and display a progress bar.

  - Supports resuming downloads.
  - Handles caching automatically.
  - Includes detailed error handling and logging.

  Args:
    url (str): The URL of the file to download.

  Returns:
    Path | None: Returns the file path (Path) on success, otherwise None.
  """
  try:
    local_filename = url.split('/')[-1]
    # Ensure the download directory exists
    DOWNLOAD_TMP_DIR.mkdir(exist_ok=True)
    download_file = DOWNLOAD_TMP_DIR / local_filename

    # Resume download logic
    headers = {}
    current_size = 0
    if download_file.exists():
      current_size = download_file.stat().st_size
      # Add Range header
      headers['Range'] = f'bytes={current_size}-'
      logging.info(f"File already exists, attempting to resume from {current_size} bytes.")

    # Use timeout parameter to prevent requests from hanging indefinitely
    with requests.get(url, stream=True, timeout=30, headers=headers) as r:
      # If server returns 200 OK, it does not support resuming, need to download from scratch
      if r.status_code == 200:
        current_size = 0
        logging.info("Server does not support resuming, downloading from scratch.")
      elif r.status_code == 206:  # Partial Content
        logging.info("Server supports resuming.")
      else:
        r.raise_for_status()  # Raise exception for non-2xx status codes

      total_length = int(r.headers.get(
        'content-length', 0)) + current_size
      chunk_size = 8192

      # 'ab' mode is used to append content for resuming
      mode = 'ab' if current_size > 0 else 'wb'
      with open(download_file, mode) as f:
        # Initial progress is the number of chunks already downloaded
        current_chunks = current_size // chunk_size
        total_chunks = total_length // chunk_size if chunk_size > 0 else 0
        _progress("Downloading:", current_chunks, total_chunks)

        for i, chunk in enumerate(r.iter_content(chunk_size=chunk_size)):
          if chunk:  # Filter out keep-alive new chunks
            f.write(chunk)
            _progress("Downloading:", i +
                  current_chunks, total_chunks)

    # Check file integrity
    if download_file.stat().st_size != total_length:
      logging.error(
        f"Download failed: incomplete file. Expected size: {total_length}, actual size: {download_file.stat().st_size}")
      return None

    sys.stdout.write('\n')  # Newline after download completes
    logging.info(f"Downloaded successfully to {download_file}")
    return download_file

  except requests.exceptions.RequestException as e:
    logging.error(f"Download failed: {e}", exc_info=True)
    return None
  except IOError as e:
    logging.error(f"File write failed: {e}", exc_info=True)
    return None


def unzip_file(file_path: Path, extract_path: Path) -> bool:
  """
  Extract a compressed file to the specified path.

  - The target folder will be cleared before extraction.
  - Provides more specific error catching.

  Args:
    file_path (Path): Path to the compressed file to extract.
    extract_path (Path): Target path for extraction.

  Returns:
    bool: Returns True if extraction succeeds, otherwise False.
  """
  if not file_path.is_file():
    logging.error(f"Compressed file not found: {file_path}")
    return False
  if extract_path.exists():
    logging.warning(f"Target path {extract_path} already exists, clearing it.")
    shutil.rmtree(extract_path)

  try:
    # Ensure the target directory exists
    extract_path.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(file_path), str(extract_path))
    logging.info(f"Successfully extracted {file_path} to {extract_path}")
    return True
  except (ValueError, shutil.ReadError, EOFError) as e:
    # shutil.ReadError and EOFError are common extraction errors
    logging.error(
      f"Extraction failed {file_path}. Possibly unsupported format or corrupted file. Error: {e}", exc_info=True)
    return False


def user_confirmation(question: str) -> bool:
  """
  Request command-line confirmation from the user.

  Args:
    question (str): The prompt question to display to the user.

  Returns:
    bool: Returns True if the user confirms, otherwise False.
  """
  prompt = f"{question} [{'/'.join(YES_CHOICES)}|{'|'.join(NO_CHOICES)}]: "
  # Reduce the number of retries, or prompt outside the loop
  for _ in range(3):
    user_input = input(prompt).lower().strip()
    if user_input in YES_CHOICES:
      return True
    if user_input in NO_CHOICES:
      return False
    print("Invalid input, please enter 'yes' or 'no' (or 'y'/'n').")
  logging.warning("No valid confirmation received, operation aborted.")
  return False
