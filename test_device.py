"""MultiRegistrator test device.

Runs a Modbus/TCP slave that continuously publishes a randomised temperature
(and a couple of extra channels) so the server/client can be tested without
real hardware.  It stays active until the user closes the console window.

Recommended register map (configure a device like this in the server):

    holding  1   float32   temperature   °C
    holding  3   uint16    humidity      масштаб (scale) 0.1, %
    holding  4   uint16    counter
    coil     1   bool      relay
"""

from __future__ import annotations

import argparse
import random
import sys
import time

from multiregistrator.common.models import encode_registers
from multiregistrator.tools.modbus_simulator import ModbusSimulator
from multiregistrator.tools.temperature import TemperatureSource

BANNER = """============================================================
 MultiRegistrator - ТЕСТОВОЕ УСТРОЙСТВО (Modbus TCP)
============================================================
Адрес:        {host}:{port}
Обновление:   каждые {interval:g} c
Карта данных (для настройки устройства в сервере):
    holding  1   float32   temperature   °C
    holding  3   uint16    humidity      масштаб 0.1, %
    holding  4   uint16    counter
    coil     1   bool      relay
------------------------------------------------------------
Закройте это окно, чтобы остановить устройство.
============================================================"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MultiRegistrator test Modbus device")
    parser.add_argument("--host", default="0.0.0.0", help="адрес для прослушивания")
    parser.add_argument("--port", type=int, default=5020, help="TCP порт (по умолчанию 5020)")
    parser.add_argument("--interval", type=float, default=1.0, help="период обновления, с")
    parser.add_argument("--base-temp", type=float, default=25.0, help="средняя температура")
    parser.add_argument("--amplitude", type=float, default=5.0, help="размах температуры")
    parser.add_argument("--step", type=float, default=0.4, help="шаг случайного блуждания")
    parser.add_argument("--seed", type=int, default=None, help="зерно генератора (для повторяемости)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:  # make Cyrillic output render correctly in the Windows console
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    simulator = ModbusSimulator(args.host, args.port)
    temperature = TemperatureSource(
        base=args.base_temp,
        amplitude=args.amplitude,
        step=args.step,
        rng=random.Random(args.seed),
    )
    humidity_rng = random.Random(None if args.seed is None else args.seed + 1)
    counter = 0

    try:
        simulator.start()
    except OSError as exc:
        print(f"Не удалось занять {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1

    print(BANNER.format(host=args.host, port=args.port, interval=args.interval))
    print()

    try:
        while True:
            value = temperature.next()
            humidity = round(humidity_rng.uniform(30.0, 70.0), 1)
            counter = (counter + 1) & 0xFFFF

            simulator.set_holding(1, encode_registers(value, "float32"))
            simulator.set_holding(3, encode_registers(humidity, "uint16", scale=0.1))
            simulator.set_holding(4, counter)
            simulator.set_coil(1, counter % 2 == 1)

            print(
                f"[{time.strftime('%H:%M:%S')}] temperature = {value:6.2f} °C   "
                f"humidity = {humidity:5.1f} %   counter = {counter:5d}   "
                f"клиентов: {simulator.connections}",
                flush=True,
            )
            time.sleep(max(0.01, args.interval))
    except KeyboardInterrupt:
        print("\nОстановка...")
    finally:
        simulator.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
