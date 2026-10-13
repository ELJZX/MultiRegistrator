"""Generate demo archive data and register the test device in the server config.

Useful to try the client/graphs before any live data exists.  Run it once::

    python -m multiregistrator.tools.generate_test_data

It writes ``archive/<host>/<host>_<date>.txt`` files and adds the test device
to ``config/server_config.json`` so the server UI already knows about it.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..common.archive import ArchiveWriter
from ..common.config import (
    app_root,
    config_dir,
    load_server_config,
    save_server_config,
)
from ..common.models import DeviceConfig, RegisterConfig
from .temperature import TemperatureSource

TEST_DEVICE_NAME = "Тестовое устройство"
TEST_DEVICE_PORT = 5020


def test_device_config(host: str = "127.0.0.1", port: int = TEST_DEVICE_PORT) -> DeviceConfig:
    """Device definition matching :mod:`test_device`."""

    return DeviceConfig(
        id=host,
        name=TEST_DEVICE_NAME,
        host=host,
        port=port,
        device_id=1,
        registers=[
            RegisterConfig(name="temperature", address=1, data_type="float32", unit="°C"),
            RegisterConfig(name="humidity", address=3, data_type="uint16", scale=0.1, unit="%"),
            RegisterConfig(name="counter", address=4, data_type="uint16"),
            RegisterConfig(name="relay", address=1, function="coil"),
        ],
    )


def generate(
    archive_dir: str | Path,
    host: str = "127.0.0.1",
    hours: float = 24.0,
    interval: float = 60.0,
    base: float = 25.0,
    amplitude: float = 5.0,
    seed: Optional[int] = 12345,
    end: Optional[datetime] = None,
    port: int = TEST_DEVICE_PORT,
) -> int:
    """Write ``hours`` of demo samples and return the number of rows written."""

    if interval <= 0:
        raise ValueError("interval must be positive")
    writer = ArchiveWriter(archive_dir)
    device = test_device_config(host, port)
    temperature = TemperatureSource(
        base=base, amplitude=amplitude, rng=random.Random(seed)
    )
    humidity = random.Random(None if seed is None else seed + 1)

    end = end or datetime.now()
    start = end - timedelta(hours=hours)
    count = max(1, int(hours * 3600 / interval))
    counter = 0
    for index in range(count):
        moment = start + timedelta(seconds=index * interval)
        value = temperature.next()
        hum = round(humidity.uniform(30.0, 70.0), 1)
        counter = (counter + 1) & 0xFFFF
        writer.append_sample(
            device,
            moment,
            {
                "temperature": value,
                "humidity": hum,
                "counter": float(counter),
                "relay": float(counter % 2),
            },
        )
    return count


def install_config(
    config_directory: str | Path, host: str = "127.0.0.1", port: int = TEST_DEVICE_PORT
) -> bool:
    """Add the test device to the server config if it is not there yet.

    ``config_directory`` is the folder that directly holds ``server_config.json``
    (i.e. the app's ``config`` directory).
    """

    config = load_server_config(config_directory)
    for device in config.devices:
        if device.host == host and device.port == port:
            return False
    config.devices.append(test_device_config(host, port))
    save_server_config(config, config_directory)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate MultiRegistrator demo data")
    parser.add_argument("--archive", default=None, help="папка архива (по умолчанию <проект>/archive)")
    parser.add_argument("--host", default="127.0.0.1", help="IP устройства (папка архива)")
    parser.add_argument("--port", type=int, default=TEST_DEVICE_PORT, help="Modbus порт устройства")
    parser.add_argument("--hours", type=float, default=24.0, help="за сколько часов создать данные")
    parser.add_argument("--interval", type=float, default=60.0, help="шаг между точками, с")
    parser.add_argument("--base-temp", type=float, default=25.0)
    parser.add_argument("--amplitude", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--no-config", action="store_true", help="не добавлять устройство в конфиг")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = app_root()
    archive_dir = Path(args.archive) if args.archive else root / "archive"

    rows = generate(
        archive_dir,
        host=args.host,
        hours=args.hours,
        interval=args.interval,
        base=args.base_temp,
        amplitude=args.amplitude,
        seed=args.seed,
        port=args.port,
    )
    added = False
    if not args.no_config:
        added = install_config(config_dir(), host=args.host, port=args.port)

    print(f"Создано точек: {rows} в {archive_dir / args.host}")
    print(
        f"Устройство {'добавлено' if added else 'уже есть'} в "
        f"{config_dir() / 'server_config.json'}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
