import logging
import os
import requests
import sys
import shutil
from pathlib import Path

from .meta import ModelMeta

# --- Constant Definition ---
WORKSPACE_PATH = os.getenv('APOLLO_ROOT_DIR', '/apollo')
MODEL_INSTALL_ROOT = Path(WORKSPACE_PATH) / "modules/perception/data/models"
MODEL_META_FILE_NAME = "apollo_deploy"
DOWNLOAD_TMP_DIR = Path("/tmp/")
UNZIP_TMP_DIR = Path("/tmp/whl_hub_extract")

FRAMEWORK_ABBREVIATION = {
    "Caffe": "caffe", "PaddlePaddle": "paddle", "PyTorch": "torch",
    "TensorFlow": "tf", "Onnx": "onnx"
}

def _progress(prefix, cur, total):
    bar_size = 50
    cur_p = int(cur / total * bar_size)
    print("{}[{}{}] {}/{}".format(prefix, "#"*cur_p, "."*(bar_size - cur_p),
                                  cur, total), end='\r', file=sys.stdout, flush=True)


def _download_from_url(url):
    """Download file from url

    Args:
        url (str): url to download

    Returns:
        file: download file's path
    """
    local_filename = url.split('/')[-1]
    download_file = os.path.join(DOWNLOAD_TMP_DIR, local_filename)

    # File is cached
    if Path(download_file).is_file():
        logging.warn(
            "File downloaded before! use cached file in {}".format(download_file))
        return download_file

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        chunk_size = 8192
        total_length = int(r.headers.get('content-length', 0)) // chunk_size
        with open(download_file, 'wb') as f:
            for index, chunk in enumerate(r.iter_content(chunk_size)):
                f.write(chunk)
                _progress("Downloading:", index, total_length)
        print()
    return download_file


def _unzip_file(file_path, extract_path):
    """Unzip file_path to extract_path

    Args:
        file_path (str): zip file need to unzip
        extract_path (str): unzip path

    Returns:
        bool: success or not
    """
    if not os.path.isfile(file_path):
        return False
    if os.path.isdir(extract_path):
        shutil.rmtree(extract_path)

    try:
        shutil.unpack_archive(file_path, extract_path)
    except ValueError:
        logging.error("Unsupported unzip format! {}".format(file_path))
        return False
    except:
        logging.error("Unzip file failed! {}".format(file_path))
        return False
    return True


def _user_confirmation(question):
    """Command line confirmation interaction

    Args:
        question (str): Prompt user for confirmation

    Returns:
        bool: sure or not
    """
    yes_choices = ['yes', 'y']
    no_choices = ['no', 'n']
    count = 3
    while count > 0:
        count -= 1
        user_input = input(question)
        if user_input.lower() in yes_choices:
            return True
        elif user_input.lower() in no_choices:
            return False
    return False


def _get_install_path_by_meta(model_meta):
    file_name = f"{model_meta.name}_{FRAMEWORK_ABBREVIATION.get(model_meta.framework, 'unknown')}"
    return MODEL_INSTALL_ROOT / file_name


def _join_meta_file(meta_path):
    for ext in ['.yaml', '.yml']:
        meta_file = Path(meta_path) / f"{MODEL_META_FILE_NAME}{ext}"
        if meta_file.is_file():
            return meta_file
    return None


def _is_url(url_str):
    """Check url_str is url

    Args:
        url_str (str): url path

    Returns:
        bool: Is url or not
    """
    return url_str.startswith('https://') or url_str.startswith('http://')


def _progress(prefix, cur, total):
    bar_size = 50
    cur_p = int(cur / total * bar_size)
    print("{}[{}{}] {}/{}".format(prefix, "#"*cur_p, "."*(bar_size - cur_p),
                                  cur, total), end='\r', file=sys.stdout, flush=True)


def install(path, skip, registry):
  """
  Core logic for installing a model.
  Returns the metadata dictionary on success, or None on failure.
  """
  # 1. Download and extract (same logic as before)
  is_url = path.startswith('http://') or path.startswith('https://')
  if not Path(path).is_file() and not is_url:
    path = f"https://apollo-pkg-beta.cdn.bcebos.com/perception_model/{path}.zip"

  try:
    if is_url:
      downloaded_path = _download_from_url(path)
    else:
      downloaded_path = path
  except Exception as e:
    logging.error(f"Download/Access of {path} failed: {e}")
    return None

  if not _unzip_file(downloaded_path, UNZIP_TMP_DIR):
    return None

  # 2. Read metadata
  # After extraction, there is usually a folder with the same name as the zip file
  unzipped_folder_name = Path(downloaded_path).stem
  unzipped_model_path = UNZIP_TMP_DIR / unzipped_folder_name

  meta_file = _join_meta_file(unzipped_model_path)
  if not meta_file:
    logging.error(
      f"Meta file (apollo_deploy.yaml/yml) not found in {unzipped_model_path}!")
    shutil.rmtree(UNZIP_TMP_DIR)
    return None

  model_meta = ModelMeta()
  if not model_meta.parse_from(meta_file):
    logging.error(f"Failed to parse meta file: {meta_file}")
    shutil.rmtree(UNZIP_TMP_DIR)
    return None

  # 3. Check for conflicts and install
  install_path = _get_install_path_by_meta(model_meta)

  if install_path.exists():
    if skip:
      logging.warning(
        f"Skipped install: Model '{model_meta.name}' already exists at {install_path}.")
      shutil.rmtree(UNZIP_TMP_DIR)
      return None

    if not _user_confirmation(f"Model '{model_meta.name}' already exists. Override? [y/n]:"):
      shutil.rmtree(UNZIP_TMP_DIR)
      return None
    shutil.rmtree(install_path)

  shutil.move(unzipped_model_path, install_path)
  print(
    f"Successfully installed model '{model_meta.name}' to {install_path}.")

  # 4. Return metadata to AssetManager
  metadata = model_meta.to_dict()
  metadata['install_path'] = str(install_path)
  return metadata


def remove(asset_name, metadata):
  """Uninstall model, returns True on success, False on failure"""
  install_path = Path(metadata.get('install_path'))
  if not install_path or not install_path.exists():
    logging.error(
      f"Cannot remove '{asset_name}'. Install path not found in registry or directory does not exist.")
    return False

  if not _user_confirmation(f"Are you sure you want to remove model '{asset_name}'? [y/n]:"):
    logging.warning(f"Removal of '{asset_name}' cancelled.")
    return False

  try:
    shutil.rmtree(install_path)
    print(
      f"Successfully removed model '{asset_name}' from {install_path}.")
    return True
  except Exception as e:
    logging.error(f"Failed to remove directory {install_path}: {e}")
    return False


def info(asset_name, metadata):
  """Print detailed information"""
  print(f"--- Info for Model: {asset_name} ---")
  for key, value in metadata.items():
    print(f"  {key.replace('_', ' ').title():<15}: {value}")
