import logging
import os
import yaml


class ModelMeta:
    """Model meta object"""

    def __init__(self):
        self.name = None
        self.version = None
        self.date = None
        self.task_type = None
        self.sensor_type = None
        self.framework = None
        self.model = None
        self.dataset = None
        self._raw_model_meta = {}

    def parse_from(self, meta_file_path):
        """Parse model meta from yaml file"""
        if not os.path.isfile(meta_file_path):
            logging.error(f"Meta file not found at: {meta_file_path}")
            return False
        with open(meta_file_path, 'r') as meta_fp:
            try:
                self._raw_model_meta = yaml.safe_load(meta_fp)
                self.name = self._raw_model_meta.get("name")
                self.version = self._raw_model_meta.get("version", "1.0.0")
                self.date = self._raw_model_meta.get("date")
                self.task_type = self._raw_model_meta.get("task_type")
                self.sensor_type = self._raw_model_meta.get("sensor_type")
                self.framework = self._raw_model_meta.get("framework")
                self.model = self._raw_model_meta.get("model")
                self.dataset = self._raw_model_meta.get("dataset")
            except (yaml.YAMLError, KeyError) as e:
                logging.error(
                    f"Failed to parse YAML or missing key in {meta_file_path}: {e}")
                return False
        return True

    def to_dict(self):
        data = self._raw_model_meta.copy()
        data['type'] = 'model'
        return data

    def __str__(self):
        """Model meta string"""
        return yaml.safe_dump(self._raw_model_meta, sort_keys=False)


class MapMeta:
    """Map meta object"""

    def __init__(self):
        self.name = None
        self.version = None
        self.date = None
        self.region = None
        self.district = None
        self.format = None
        self._raw_map_meta = {}

    def parse_from(self, meta_file_path):
        """Parse map meta from yaml file"""
        if not os.path.isfile(meta_file_path):
            logging.error(f"Meta file not found at: {meta_file_path}")
            return False
        with open(meta_file_path, 'r') as meta_fp:
            try:
                self._raw_map_meta = yaml.safe_load(meta_fp)
                self.name = self._raw_map_meta.get("name")
                self.version = self._raw_map_meta.get("version", "1.0.0")
                self.date = self._raw_map_meta.get("date")
                self.region = self._raw_map_meta.get("region")
                self.district = self._raw_map_meta.get("district")
                self.format = self._raw_map_meta.get("format")
            except (yaml.YAMLError, KeyError) as e:
                logging.error(
                    f"Failed to parse YAML or missing key in {meta_file_path}: {e}")
                return False
        return True

    def to_dict(self):
        data = self._raw_map_meta.copy()
        data['type'] = 'map'
        return data

    def __str__(self):
        """Map meta string"""
        return yaml.safe_dump(self._raw_map_meta, sort_keys=False)
