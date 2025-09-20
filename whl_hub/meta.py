# -*- coding: utf-8 -*-
import logging
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import ClassVar, Dict, Any, List, Optional


class BaseMeta:
    """
    Abstract base class for metadata.
    Encapsulates all common YAML parsing and data processing logic.
    """
    _REQUIRED_FIELDS: ClassVar[List[str]] = ["name", "date"]
    _OPTIONAL_FIELDS: ClassVar[Dict[str, Any]] = {"version": "1.0.0"}
    _meta_type: ClassVar[str] = "base"

    def __init__(self):
        self._raw_meta: Dict[str, Any] = {}

    def parse_from(self, meta_file_path: Path | str) -> bool:
        """Parse metadata from a YAML file."""
        meta_path = Path(meta_file_path)
        if not meta_path.is_file():
            logging.error(f"Metadata file not found: {meta_path}")
            return False

        try:
            with meta_path.open('r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    raise yaml.YAMLError("Top-level YAML structure must be a dictionary.")
                self._raw_meta = data
        except (yaml.YAMLError, IOError) as e:
            logging.error(f"Failed to parse or read YAML file {meta_path}: {e}", exc_info=True)
            return False

        try:
            # Automatically handle all fields
            all_fields = self._REQUIRED_FIELDS + \
                list(self._OPTIONAL_FIELDS.keys())

            # Validate required fields
            for key in self._REQUIRED_FIELDS:
                if key not in self._raw_meta:
                    raise KeyError(f"Required field '{key}' not found in file.")

            # Dynamically set instance attributes
            for key in all_fields:
                default_value = self._OPTIONAL_FIELDS.get(key)
                setattr(self, key, self._raw_meta.get(key, default_value))

        except KeyError as e:
            logging.error(f"Metadata format error {meta_path}: {e}", exc_info=True)
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to a dictionary and add type identifier."""
        data = self._raw_meta.copy()
        data['type'] = self._meta_type
        return data

    def __str__(self) -> str:
        """Format the raw metadata as a YAML string."""
        return yaml.safe_dump(self._raw_meta, sort_keys=False, allow_unicode=True)


@dataclass
class ModelMeta(BaseMeta):
    """Model metadata object."""
    # Define class-specific fields
    _REQUIRED_FIELDS: ClassVar[List[str]] = BaseMeta._REQUIRED_FIELDS + \
        ["task_type", "framework", "model"]
    _OPTIONAL_FIELDS: ClassVar[Dict[str, Any]] = {
        **BaseMeta._OPTIONAL_FIELDS, "sensor_type": None, "dataset": None}
    _meta_type: ClassVar[str] = "model"

    name: Optional[str] = None
    version: Optional[str] = None
    date: Optional[str] = None
    task_type: Optional[str] = None
    framework: Optional[str] = None
    model: Optional[str] = None
    sensor_type: Optional[str] = None
    dataset: Optional[str] = None


@dataclass
class MapMeta(BaseMeta):
    """Map metadata object."""
    _REQUIRED_FIELDS: ClassVar[List[str]
                               ] = BaseMeta._REQUIRED_FIELDS + ["region", "district"]
    _meta_type: ClassVar[str] = "map"

    name: Optional[str] = None
    version: Optional[str] = None
    date: Optional[str] = None
    region: Optional[str] = None
    district: Optional[str] = None
