import json
import logging
from pathlib import Path
import yaml

from . import model_operations
from . import map_operations


REGISTRY_PATH = Path.home() / ".whl-hub" / "registry.json"

class AssetManager:
    """
    Coordinate installation, removal, and querying of models and maps, and manage the central registry.
    """
    def __init__(self):
        """Load or create the registry."""
        self.registry = {}
        try:
            REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, 'r') as f:
                    self.registry = json.load(f)
            else:
                self._save_registry()
        except (IOError, json.JSONDecodeError) as e:
            logging.critical(f"FATAL: Could not read or create registry at {REGISTRY_PATH}. Error: {e}")
            exit(1)

    def _save_registry(self):
        """Atomically write the current registry state to file."""
        try:
            with open(REGISTRY_PATH, 'w') as f:
                json.dump(self.registry, f, indent=2, sort_keys=True)
        except IOError as e:
            logging.error(f"Failed to save registry: {e}")

    def _get_asset_metadata(self, asset_name):
        """Safely get asset metadata from the registry."""
        return self.registry.get(asset_name)

    def list_all(self):
        """Format and print all installed models and maps."""
        if not self.registry:
            print("No assets (models or maps) are installed.")
            return

        print("--- Models ---")
        models = {k: v for k, v in self.registry.items() if v.get('type') == 'model'}
        if models:
            print(f"{'Name':<25} {'Version':<15} {'Framework':<15} {'Sensor':<20}")
            print("-" * 75)
            for name, meta in models.items():
                print(f"{name:<25} {meta.get('version', 'N/A'):<15} {meta.get('framework', 'N/A'):<15} {meta.get('sensor_type', 'N/A'):<20}")
        else:
            print("  No models installed.")

        print("\n--- Maps ---")
        maps = {k: v for k, v in self.registry.items() if v.get('type') == 'map'}
        if maps:
            print(f"{'Name':<25} {'Version':<15} {'Region':<20} {'Format':<15}")
            print("-" * 75)
            for name, meta in maps.items():
                print(f"{name:<25} {meta.get('version', 'N/A'):<15} {meta.get('region', 'N/A'):<20} {meta.get('format', 'N/A'):<15}")
        else:
            print("  No maps installed.")

    def info(self, asset_name):
        """Display detailed information for a specific asset."""
        metadata = self._get_asset_metadata(asset_name)
        if not metadata:
            logging.error(f"Asset '{asset_name}' not found.")
            return

        asset_type = metadata.get('type')
        print(f"--- Details for {asset_type.capitalize()}: {asset_name} ---")
        print(yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True))


    def install(self, path, asset_type, skip):
        """Call the corresponding install function and update the registry."""
        metadata = None
        if asset_type == 'model':
            metadata = model_operations.install(path, skip)
        elif asset_type == 'map':
            metadata = map_operations.install(path, skip)
        else:
            logging.error(f"Internal error: Unknown asset type '{asset_type}'.")
            return

        if metadata and metadata.get('name'):
            asset_name = metadata['name']
            self.registry[asset_name] = metadata
            self._save_registry()
            logging.info(f"Registry updated for asset: '{asset_name}'.")
        else:
            logging.error("Installation failed or did not return valid metadata. Registry not updated.")


    def remove(self, asset_name):
        """Call the corresponding remove function based on asset type and update the registry."""
        metadata = self._get_asset_metadata(asset_name)
        if not metadata:
            logging.error(f"Asset '{asset_name}' not found in registry. Cannot remove.")
            return

        asset_type = metadata.get('type')
        success = False
        if asset_type == 'model':
            success = model_operations.remove(asset_name, metadata)
        elif asset_type == 'map':
            success = map_operations.remove(asset_name, metadata)
        else:
            logging.error(f"Asset '{asset_name}' has an unknown type '{asset_type}' in registry.")
            return

        if success:
            del self.registry[asset_name]
            self._save_registry()
            logging.info(f"Asset '{asset_name}' was successfully removed and registry has been updated.")
        else:
            logging.error(f"Removal of asset '{asset_name}' failed. Registry was not changed.")
