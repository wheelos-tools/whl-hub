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
from whl_hub.utils import resolve_asset_path, unzip_file, user_confirmation


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

    def find_meta_file(self, search_dir: Path) -> Optional[Path]:
        """
        Recursively finds the model metadata file within a directory.

        It handles cases where the zip archive extracts to a single root folder.
        It searches for both .yaml and .yml extensions.

        Args:
            search_dir: The directory to search within (e.g., /tmp/whl_hub_model_extract).

        Returns:
            A Path object to the first found metadata file, or None if not found.
        """
        logging.info(f"Recursively searching for '{self.model_meta_filename}.(yaml|yml)' in '{search_dir}'...")

        # Use rglob to search in the current directory and all subdirectories
        # for a file with the base name and either .yaml or .yml extension.

        # Search for .yaml first
        found_files = list(search_dir.rglob(f'{self.model_meta_filename}.yaml'))
        if found_files:
            if len(found_files) > 1:
                logging.warning(f"Multiple '{self.model_meta_filename}.yaml' files found. Using the first one: {found_files[0]}")
            logging.info(f"Found metadata file: {found_files[0]}")
            return found_files[0]

        # If not found, search for .yml
        found_files = list(search_dir.rglob(f'{self.model_meta_filename}.yml'))
        if found_files:
            if len(found_files) > 1:
                logging.warning(f"Multiple '{self.model_meta_filename}.yml' files found. Using the first one: {found_files[0]}")
            logging.info(f"Found metadata file: {found_files[0]}")
            return found_files[0]

        # If we reach here, neither was found.
        logging.error(f"Metadata file '{self.model_meta_filename}.(yaml|yml)' not found anywhere inside '{search_dir}'.")
        return None


def install(path_or_name: str, skip_if_exists: bool) -> Optional[Dict[str, Any]]:
    """
    Core logic for installing a new model.

    Args:
        path_or_name: A URL, local file path, or a model name to download from the CDN.
        skip_if_exists: If True and the model already exists, skip the installation.

    Returns:
        On success, returns a metadata dictionary including the installation path. On failure, returns None.
    """
    config = AssetConfig()

    # Manage the top-level existence of the temp directory outside the try block.
    # This ensures the `finally` block can execute correctly even if `install` fails to start.
    if config.unzip_tmp_dir.exists():
        logging.warning(f"Temporary directory {config.unzip_tmp_dir} already exists, clearing it.")
        shutil.rmtree(config.unzip_tmp_dir)
    config.unzip_tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # --- Stage 1: Acquire Asset ---
        # `_resolve_asset_path` encapsulates all decision logic for URL, CDN, or local files.
        archive_path = resolve_asset_path(path_or_name, config)
        if not archive_path:
            logging.error("Asset acquisition failed, aborting installation.")
            return None

        # --- Stage 2: Extract Asset ---
        # `unzip_file` now returns the path to the directory where it extracted the files.
        extraction_path = unzip_file(archive_path, config.unzip_tmp_dir)
        if not extraction_path:
            logging.error("Asset extraction failed, aborting installation.")
            return None

        # --- Stage 3: Parse Metadata ---
        meta_file = config.find_meta_file(extraction_path)
        if not meta_file:
            logging.error(f"Metadata file '{config.model_meta_filename}.yaml/yml' not found in the extracted archive!")
            return None

        model_meta = ModelMeta()
        if not model_meta.parse_from(meta_file):
            # `parse_from` should log detailed errors internally.
            logging.error("Failed to parse metadata, aborting installation.")
            return None

        # The directory containing the metadata file is the actual model content we need to move.
        unzipped_model_content_path = meta_file.parent

        # --- Stage 4: Check for Conflicts and Get Confirmation ---
        install_path = config.get_install_path(model_meta)

        if install_path.exists():
            if skip_if_exists:
                logging.warning(f"Skipping installation: Model '{model_meta.name}' already exists at {install_path}.")
                return None  # This is an explicit skip, not an error.

            question = f"Model '{model_meta.name}' already exists at {install_path}. Overwrite? [y/n]: "
            if not user_confirmation(question):
                logging.warning("Installation was canceled by the user.")
                return None

            logging.info(f"Removing existing model to overwrite: {install_path}")
            shutil.rmtree(install_path)

        # --- Stage 5: Perform Installation ---
        logging.info(f"Installing '{unzipped_model_content_path}' to '{install_path}'...")
        shutil.move(str(unzipped_model_content_path), str(install_path))
        print(f"✅ Successfully installed model '{model_meta.name}' to {install_path}.")

        # --- Stage 6: Prepare Return Data ---
        metadata = model_meta.to_dict()
        metadata['install_path'] = str(install_path)
        return metadata

    finally:
        # This block executes regardless of success or failure to ensure cleanup.
        if config.unzip_tmp_dir.exists():
            shutil.rmtree(config.unzip_tmp_dir)
            logging.debug("Temporary directory has been successfully cleaned up.")


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

