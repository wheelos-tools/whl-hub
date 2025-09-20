# -*- coding: utf-8 -*-
"""
Handles the file-system-level installation, removal, and querying of HD maps.
This module is designed to be called by a higher-level asset manager and mirrors
the structure of model_operations.
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from whl_hub.meta import MapMeta
from whl_hub.utils import resolve_asset_path, unzip_file, user_confirmation


class AssetConfig:
    """Encapsulates all configuration required for map operations."""

    def __init__(self, workspace_path: Optional[str] = None):
        """
        Initializes map-specific configurations.
        """
        if workspace_path is None:
            workspace_path = os.getenv('APOLLO_ROOT_DIR', '/apollo')

        self.workspace_path: Path = Path(workspace_path)
        self.map_install_root: Path = self.workspace_path / "modules/map/data"
        self.unzip_tmp_dir: Path = Path("/tmp/whl_hub_map_extract")
        self.map_meta_filename: str = "meta"
        # TODO(daohu527): Need to update the actual CDN URL
        self.cdn_url_template: str = "https://example.com/maps/{}.zip"

    def get_install_path(self, map_meta: MapMeta) -> Path:
        """
        Generate the final installation path based on map metadata.
        For maps, the installation path is simply the map's name.
        """
        if not map_meta.name:
            raise ValueError("Cannot get install path: map metadata is missing a 'name'.")
        return self.map_install_root / map_meta.name

    def find_meta_file(self, search_dir: Path, map_name: str) -> Optional[Path]:
        """
        Finds the metadata file in a subdirectory matching the map's name.

        This function assumes the zip archive extracts its contents into a
        folder named after the map itself.
        e.g., 'borregas_ave.zip' -> './borregas_ave/meta.yaml'

        Args:
            search_dir: The root directory where files were extracted (e.g., /tmp/...).
            map_name: The expected name of the map, used to identify the subdirectory.

        Returns:
            A Path object to the metadata file, or None if not found.
        """
        logging.info(f"Searching for metadata in subdirectory '{map_name}' within '{search_dir}'...")

        map_content_path = search_dir / map_name
        if not map_content_path.is_dir():
            logging.error(f"Expected map content directory '{map_content_path}' not found after extraction.")
            subdirs = [d for d in search_dir.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                logging.warning(f"Did not find '{map_name}', but found a single directory '{subdirs[0].name}'. Assuming this is the map content path.")
                map_content_path = subdirs[0]
            else:
                return None

        for ext in ['.yaml', '.yml']:
            meta_file = map_content_path / f'{self.map_meta_filename}{ext}'
            if meta_file.is_file():
                logging.info(f"Found metadata file: {meta_file}")
                return meta_file

        logging.error(f"Metadata file '{self.map_meta_filename}.(yaml|yml)' not found inside '{map_content_path}'.")
        return None


def install(path_or_name: str, skip_if_exists: bool) -> Optional[Dict[str, Any]]:
    """
    Core logic for installing a new map.

    Args:
        path_or_name: A URL, local file path, or a map name to download.
        skip_if_exists: If True, and the map already exists, skip the installation.

    Returns:
        On success, returns a metadata dictionary including the installation path. On failure, returns None.
    """
    config = AssetConfig()

    if config.unzip_tmp_dir.exists():
        logging.warning(f"Temporary directory {config.unzip_tmp_dir} already exists, clearing it.")
        shutil.rmtree(config.unzip_tmp_dir)
    config.unzip_tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # --- Stage 1: Acquire Asset ---
        archive_path = resolve_asset_path(path_or_name, config)
        if not archive_path:
            logging.error("Map asset acquisition failed, aborting installation.")
            return None

        # --- Stage 2: Extract Asset ---
        extraction_path = unzip_file(archive_path, config.unzip_tmp_dir)
        if not extraction_path:
            logging.error("Map asset extraction failed, aborting installation.")
            return None

        # --- Stage 3: Parse Metadata ---
        meta_file = config.find_meta_file(extraction_path, path_or_name)
        if not meta_file:
            return None

        map_meta = MapMeta()
        if not map_meta.parse_from(meta_file):
            logging.error("Failed to parse map metadata, aborting installation.")
            return None

        if not map_meta.name:
            logging.error("Missing 'name' attribute in map metadata file. Cannot determine install directory.")
            return None

        unzipped_map_content_path = meta_file.parent

        # --- Stage 4: Check for Conflicts and Get Confirmation ---
        install_path = config.get_install_path(map_meta)

        if install_path.exists():
            if skip_if_exists:
                logging.warning(f"Skipping installation: Map '{map_meta.name}' already exists at {install_path}.")
                return None

            question = f"Map '{map_meta.name}' already exists at {install_path}. Overwrite? [y/n]: "
            if not user_confirmation(question):
                logging.warning("Installation was canceled by the user.")
                return None

            logging.info(f"Removing existing map to overwrite: {install_path}")
            shutil.rmtree(install_path)

        # --- Stage 5: Perform Installation ---
        logging.info(f"Installing '{unzipped_map_content_path}' to '{install_path}'...")
        shutil.move(str(unzipped_map_content_path), str(install_path))
        print(f"✅ Successfully installed map '{map_meta.name}' to {install_path}.")

        # --- Stage 6: Prepare Return Data ---
        metadata = map_meta.to_dict()
        metadata['install_path'] = str(install_path)
        return metadata

    finally:
        if config.unzip_tmp_dir.exists():
            shutil.rmtree(config.unzip_tmp_dir)
            logging.debug("Temporary map directory has been successfully cleaned up.")


def remove(asset_name: str, metadata: Dict[str, Any]) -> bool:
    """Uninstall a map based on its name and metadata."""
    install_path_str = metadata.get('install_path')
    if not install_path_str:
        logging.error(f"Cannot remove '{asset_name}'. 'install_path' not found in registry.")
        return False

    install_path = Path(install_path_str)
    if not install_path.exists():
        logging.warning(
            f"Cannot remove '{asset_name}'. Directory '{install_path}' does not exist. It may have been manually removed.")
        return True

    question = f"Are you sure you want to remove map '{asset_name}' from '{install_path}'? This action is irreversible. [y/n]: "
    if not user_confirmation(question):
        logging.warning(f"Removal of map '{asset_name}' cancelled.")
        return False

    try:
        shutil.rmtree(install_path)
        print(f"🗑️ Successfully removed map '{asset_name}'.")
        return True
    except OSError as e:
        logging.error(f"Failed to remove directory {install_path}: {e}", exc_info=True)
        return False


def info(asset_name: str, metadata: Dict[str, Any]) -> None:
    """Print detailed information about the asset, using provided metadata."""
    print(f"--- Map Info: {asset_name} ---")
    for key, value in metadata.items():
        display_key = key.replace('_', ' ').title()
        print(f"  {display_key:<15}: {value}")
