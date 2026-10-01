import logging
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class EventLogger:
    """Stand-in for EventClient: accepts the structured keywords it takes."""

    def __init__(self):
        self._log = logging.getLogger("test")

    def info(self, message, **_):
        self._log.info(message)

    def warning(self, message, **_):
        self._log.warning(message)

    def error(self, message, **_):
        self._log.error(message)


class LocationClient:
    def __init__(self, geometry, key):
        self._locations = [
            SimpleNamespace(location_name=name, representations={key: rep})
            for name, rep in geometry.items()
        ]

    def get_locations(self):
        return self._locations
