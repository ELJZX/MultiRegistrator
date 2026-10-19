"""Configuration handling for the server and the client.

Configuration is stored as human readable JSON next to the program inside the
``config`` directory.  Both configs can be loaded/saved independently which
makes them easy to unit test with a temporary directory.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import DeviceConfig


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def app_root() -> Path:
    """Root directory of the program (the folder that also holds ``archive``).

    When frozen with PyInstaller the executable lives next to the
    ``archive``/``config`` folders, so its location is used instead of the
    bundled (temporary) source location.
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def config_dir(base_dir: Optional[Path] = None) -> Path:
    return Path(base_dir) if base_dir is not None else app_root() / "config"


def default_archive_dir(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir) if base_dir is not None else app_root()
    return root / "archive"


@dataclass
class DatabaseSettings:
    """PostgreSQL connection used to mirror the archive and the logs.

    The container setup (``docker-compose.yml``) passes the values through
    ``MULTIREGISTRATOR_DB_*`` environment variables, which take precedence over
    the JSON config so the same image works on any host.
    """

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 5432
    name: str = "multiregistrator"
    user: str = "multiregistrator"
    password: str = "multiregistrator"
    connect_timeout: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "name": self.name,
            "user": self.user,
            "password": self.password,
            "connect_timeout": self.connect_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatabaseSettings":
        defaults = cls()
        return cls(
            enabled=_env_bool(
                "MULTIREGISTRATOR_DB_ENABLED",
                bool(data.get("enabled", defaults.enabled)),
            ),
            host=_env_str("MULTIREGISTRATOR_DB_HOST", str(data.get("host", defaults.host))),
            port=_env_int("MULTIREGISTRATOR_DB_PORT", int(data.get("port", defaults.port))),
            name=_env_str("MULTIREGISTRATOR_DB_NAME", str(data.get("name", defaults.name))),
            user=_env_str("MULTIREGISTRATOR_DB_USER", str(data.get("user", defaults.user))),
            password=_env_str(
                "MULTIREGISTRATOR_DB_PASSWORD", str(data.get("password", defaults.password))
            ),
            connect_timeout=_env_int(
                "MULTIREGISTRATOR_DB_TIMEOUT",
                int(data.get("connect_timeout", defaults.connect_timeout)),
            ),
        )


@dataclass
class ServerSettings:
    api_host: str = "0.0.0.0"
    api_port: int = 8120
    archive_dir: str = "archive"
    default_poll_interval: float = 5.0
    default_timeout: float = 3.0
    default_retries: int = 1
    inter_request_delay: float = 0.0
    database: DatabaseSettings = field(default_factory=DatabaseSettings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_host": self.api_host,
            "api_port": self.api_port,
            "archive_dir": self.archive_dir,
            "default_poll_interval": self.default_poll_interval,
            "default_timeout": self.default_timeout,
            "default_retries": self.default_retries,
            "inter_request_delay": self.inter_request_delay,
            "database": self.database.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerSettings":
        defaults = cls()
        return cls(
            api_host=str(data.get("api_host", defaults.api_host)),
            api_port=int(data.get("api_port", defaults.api_port)),
            archive_dir=str(data.get("archive_dir", defaults.archive_dir)),
            default_poll_interval=float(
                data.get("default_poll_interval", defaults.default_poll_interval)
            ),
            default_timeout=float(data.get("default_timeout", defaults.default_timeout)),
            default_retries=int(data.get("default_retries", defaults.default_retries)),
            inter_request_delay=float(
                data.get("inter_request_delay", defaults.inter_request_delay)
            ),
            database=DatabaseSettings.from_dict(data.get("database", {})),
        )

    def resolve_archive_dir(self, base_dir: Optional[Path] = None) -> Path:
        path = Path(self.archive_dir)
        if path.is_absolute():
            return path
        root = Path(base_dir) if base_dir is not None else app_root()
        return root / path


@dataclass
class ServerConfig:
    settings: ServerSettings = field(default_factory=ServerSettings)
    devices: list[DeviceConfig] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "settings": self.settings.to_dict(),
            "devices": [d.to_dict() for d in self.devices],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerConfig":
        return cls(
            settings=ServerSettings.from_dict(data.get("settings", {})),
            devices=[DeviceConfig.from_dict(d) for d in data.get("devices", [])],
        )

    def device_by_id(self, device_id: str) -> Optional[DeviceConfig]:
        for device in self.devices:
            if device.id == device_id:
                return device
        return None


@dataclass
class ClientSettings:
    server_host: str = "127.0.0.1"
    server_port: int = 8120
    connection_name: str = "Сервер"
    live_refresh_ms: int = 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_host": self.server_host,
            "server_port": self.server_port,
            "connection_name": self.connection_name,
            "live_refresh_ms": self.live_refresh_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientSettings":
        defaults = cls()
        return cls(
            server_host=str(data.get("server_host", defaults.server_host)),
            server_port=int(data.get("server_port", defaults.server_port)),
            connection_name=str(data.get("connection_name", defaults.connection_name)),
            live_refresh_ms=int(data.get("live_refresh_ms", defaults.live_refresh_ms)),
        )


@dataclass
class ClientConfig:
    settings: ClientSettings = field(default_factory=ClientSettings)
    connections: list[ClientSettings] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "settings": self.settings.to_dict(),
            "connections": [c.to_dict() for c in self.connections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientConfig":
        return cls(
            settings=ClientSettings.from_dict(data.get("settings", {})),
            connections=[ClientSettings.from_dict(c) for c in data.get("connections", [])],
        )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_server_config(base_dir: Optional[Path] = None) -> ServerConfig:
    path = config_dir(base_dir) / "server_config.json"
    return ServerConfig.from_dict(_read_json(path))


def save_server_config(config: ServerConfig, base_dir: Optional[Path] = None) -> Path:
    path = config_dir(base_dir) / "server_config.json"
    _write_json(path, config.to_dict())
    return path


def load_client_config(base_dir: Optional[Path] = None) -> ClientConfig:
    path = config_dir(base_dir) / "client_config.json"
    return ClientConfig.from_dict(_read_json(path))


def save_client_config(config: ClientConfig, base_dir: Optional[Path] = None) -> Path:
    path = config_dir(base_dir) / "client_config.json"
    _write_json(path, config.to_dict())
    return path
