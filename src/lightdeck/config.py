"""Persistent settings, stored in the platform's standard config location."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import APP_ID, APP_NAME

# Where versions <= 0.2 (philips-hue-for-arch) kept their pairing.
LEGACY_CONFIG_FILE = Path.home() / ".config" / "philips-hue-for-arch" / "config.json"


def config_dir() -> Path:
    override = os.environ.get("LIGHTDECK_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / APP_ID


def config_file() -> Path:
    return config_dir() / "config.json"


@dataclass
class AppConfig:
    bridge_ip: str = ""
    bridge_id: str = ""
    bridge_name: str = ""
    app_key: str = ""
    client_key: str = ""
    # SHA-256 of the bridge's TLS certificate, pinned the first time we connect.
    cert_sha256: str = ""
    theme: str = "system"

    @property
    def is_paired(self) -> bool:
        return bool(self.bridge_ip and self.app_key)

    def forget_bridge(self) -> None:
        self.bridge_ip = self.bridge_id = self.bridge_name = ""
        self.app_key = self.client_key = self.cert_sha256 = ""


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_config(path: Path | None = None, legacy_path: Path | None = LEGACY_CONFIG_FILE) -> AppConfig:
    path = path or config_file()
    data = _read_json(path)
    if data is None:
        # A v1 "username" is the same whitelist entry the v2 API calls an
        # application key, so existing pairings keep working after upgrading.
        legacy = _read_json(legacy_path) if legacy_path else None
        if legacy and legacy.get("bridge_ip") and legacy.get("username"):
            config = AppConfig(bridge_ip=str(legacy["bridge_ip"]), app_key=str(legacy["username"]))
            save_config(config, path)
            return config
        return AppConfig()

    known = {field.name for field in fields(AppConfig)}
    return AppConfig(**{key: str(value) for key, value in data.items() if key in known})


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    if os.name == "posix":
        tmp.chmod(0o600)  # contains the bridge application key
    tmp.replace(path)
