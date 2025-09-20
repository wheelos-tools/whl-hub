# -*- coding: utf-8 -*-
"""
Handles the file-system-level installation, removal, and querying of ML models.
This module is designed to be called by a higher-level asset manager.
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from whl_hub.meta import ModelMeta
from whl_hub.utils import download_from_url, unzip_file, user_confirmation


class AssetConfig:
    """Encapsulates all configuration required for model operations."""

    def __init__(self, workspace_path: Optional[str] = None):
        if workspace_path is None:
            workspace_path = os.getenv('APOLLO_ROOT_DIR', '/apollo')

        self.workspace_path: Path = Path(workspace_path)
        self.model_install_root: Path = self.workspace_path / \
            "modules/perception/data/models"
        self.unzip_tmp_dir: Path = Path("/tmp/whl_hub_model_extract")
        self.model_meta_filename: str = "apollo_deploy"
        self.cdn_url_template: str = "https://apollo-pkg-beta.cdn.bcebos.com/perception_model/{}.zip"
        self.framework_abbreviation: Dict[str, str] = {
            "Caffe": "caffe", "PaddlePaddle": "paddle", "PyTorch": "torch",
            "TensorFlow": "tf", "Onnx": "onnx"
        }

    def get_install_path(self, model_meta: ModelMeta) -> Path:
        """Generate the final installation path based on model metadata."""
        framework_abbr = self.framework_abbreviation.get(
            model_meta.framework, 'unknown')
        file_name = f"{model_meta.name}_{framework_abbr}"
        return self.model_install_root / file_name

    def find_meta_file(self, search_path: Path) -> Optional[Path]:
        """Find the metadata file in the given directory."""
        for ext in ['.yaml', '.yml']:
            meta_file = search_path / f"{self.model_meta_filename}{ext}"
            if meta_file.is_file():
                return meta_file
        return None


def install(path_or_name: str, skip_if_exists: bool) -> Optional[Dict[str, Any]]:
    """
    Core logic for installing a new model.

    Args:
        path_or_name: A URL, local file path, or model name to download from CDN.
        skip_if_exists: If True, skip installation if the model already exists.

    Returns:
        Returns metadata dict on success, None on failure.
    """
    config = AssetConfig()
    if config.unzip_tmp_dir.exists():
        shutil.rmtree(config.unzip_tmp_dir)
    config.unzip_tmp_dir.mkdir(parents=True)

    try:
        # --- Stage 1: Acquire and extract asset ---
        is_url = path_or_name.startswith(('http://', 'https://'))
        if not Path(path_or_name).is_file() and not is_url:
            path_or_name = config.cdn_url_template.format(path_or_name)
            logging.info(f"Interpreted as model name. Downloading from: {path_or_name}")

        downloaded_path = download_from_url(
            path_or_name) if is_url else Path(path_or_name)

        if not downloaded_path or not downloaded_path.exists():
            logging.error(f"Cannot access or download asset: {path_or_name}")
            return None

        if not unzip_file(downloaded_path, config.unzip_tmp_dir):
            return None

        meta_file = config.find_meta_file(config.unzip_tmp_dir)
        if not meta_file:
            logging.error(
                f"Metadata file '{config.model_meta_filename}.yaml/yml' not found in extracted archive!")
            return None
        unzipped_model_path = meta_file.parent

        # --- Stage 2: Parse metadata and check for conflicts ---
        model_meta = ModelMeta()
        if not model_meta.parse_from(meta_file):
            return None

        install_path = config.get_install_path(model_meta)

        if install_path.exists():
            if skip_if_exists:
                logging.warning(
                    f"Skipping installation: Model '{model_meta.name}' already exists at {install_path}.")
                return None

            question = f"Model '{model_meta.name}' already exists. Overwrite? [y/n]: "
            if not user_confirmation(question):
                logging.warning("Installation cancelled by user.")
                return None
            shutil.rmtree(install_path)

        # --- Stage 3: Perform installation ---
        shutil.move(str(unzipped_model_path), str(install_path))
        print(f"✅ Successfully installed model '{model_meta.name}' to {install_path}.")

        metadata = model_meta.to_dict()
        metadata['install_path'] = str(install_path)
        return metadata

    finally:
        if config.unzip_tmp_dir.exists():
            shutil.rmtree(config.unzip_tmp_dir)
            logging.debug("Temporary directory cleaned up.")


def remove(asset_name: str, metadata: Dict[str, Any]) -> bool:
    """Uninstall a model based on metadata."""
    install_path_str = metadata.get('install_path')
    if not install_path_str:
        logging.error(f"Cannot remove '{asset_name}'. 'install_path' not found in registry.")
        return False

    install_path = Path(install_path_str)
    if not install_path.exists():
        logging.warning(
            f"Cannot remove '{asset_name}'. Directory '{install_path}' does not exist. It may have been manually removed.")
        return True

    question = f"Are you sure you want to remove model '{asset_name}'? This action is irreversible. [y/n]: "
    if not user_confirmation(question):
        logging.warning(f"Removal of '{asset_name}' cancelled.")
        return False

    try:
        shutil.rmtree(install_path)
        print(f"🗑️ Successfully removed model '{asset_name}'.")
        return True
    except OSError as e:
        logging.error(f"Failed to remove directory {install_path}: {e}", exc_info=True)
        return False


def info(asset_name: str, metadata: Dict[str, Any]) -> None:
    """Print detailed information about the asset."""
    print(f"--- Model Info: {asset_name} ---")
    for key, value in metadata.items():
        display_key = key.replace('_', ' ').title()
        print(f"  {display_key:<15}: {value}")

