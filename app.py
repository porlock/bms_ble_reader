import argparse
import asyncio
import struct
from dataclasses import dataclass
from typing import Callable

from bleak import BleakClient, BleakScanner


SERVICE_UUID = "00000001-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "00000003-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "00000002-0000-1000-8000-00805f9b34fb"
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"
DEFAULT_ADDRESS = "8E:8A:C2:91:74:A2"
DEFAULT_NAME = "HS030302BC26150127"


@dataclass(frozen=True)
class BatteryStatus:
    voltage_v: float
    current_a: float
    state_of_charge: int
    state_of_health: int
    temperature_t1_c: int | None
    temperature_mos_c: int | None


def checksum_valid(frame: bytes) -> bool:
    if len(frame) < 5 or frame[0] != 0xAA:
        return False
    payload_length = frame[2]
    if len(frame) != payload_length + 5:
        return False
    calculated = sum(frame[1 : 3 + payload_length]) & 0xFFFF
    received = int.from_bytes(frame[-2:], "little")
    return calculated == received


def make_read_request(frame_type: int) -> bytes:
    body = bytes((frame_type, 0x00))
    checksum = sum(body).to_bytes(2, "little")
    return b"\xAA" + body + checksum


def decode_status(payload: bytes) -> BatteryStatus:
    if len(payload) < 10:
        raise ValueError("Ramka 0x21 ma za krotki payload")
    voltage_mv = int.from_bytes(payload[0:4], "little")
    current_ma = struct.unpack_from("<i", payload, 4)[0]
    return BatteryStatus(
        voltage_v=voltage_mv / 1000.0,
        current_a=current_ma / 1000.0,
        state_of_charge=payload[8],
        state_of_health=payload[9],
        temperature_t1_c=(
            int.from_bytes(payload[20:21], "little", signed=True)
            if len(payload) > 20
            else None
        ),
        temperature_mos_c=(
            int.from_bytes(payload[24:25], "little", signed=True)
            if len(payload) > 24
            else None
        ),
    )


def decode_cells(payload: bytes) -> list[float]:
    cells = []
    for offset in range(0, len(payload) - 1, 2):
        millivolts = int.from_bytes(payload[offset : offset + 2], "little")
        if millivolts == 0:
            continue
        cells.append(millivolts / 1000.0)
    return cells


class FrameStream:
    def __init__(self, callback: Callable[[bytes], None]) -> None:
        self.buffer = bytearray()
        self.callback = callback

    def feed(self, data: bytes) -> None:
        self.buffer.extend(data)
        while True:
            try:
                start = self.buffer.index(0xAA)
            except ValueError:
                self.buffer.clear()
                return

            if start:
                del self.buffer[:start]
            if len(self.buffer) < 3:
                return

            frame_length = self.buffer[2] + 5
            if len(self.buffer) < frame_length:
                return

            frame = bytes(self.buffer[:frame_length])
            if checksum_valid(frame):
                del self.buffer[:frame_length]
                self.callback(frame)
            else:
                del self.buffer[0]


class BmsReader:
    def __init__(self) -> None:
        self.received_status = False
        self.received_cells = False
        self.complete = asyncio.Event()
        self.stream = FrameStream(self.handle_frame)

    def notification(self, _sender, data: bytearray) -> None:
        self.stream.feed(bytes(data))

    def handle_frame(self, frame: bytes) -> None:
        frame_type = frame[1]
        payload = frame[3:-2]

        if frame_type == 0x21:
            status = decode_status(payload)
            discharged = max(0, min(100, 100 - status.state_of_charge))
            power = status.voltage_v * status.current_a
            print("\nStatus akumulatora")
            print(f"  Naladowanie:  {status.state_of_charge}%")
            print(f"  Rozladowanie: {discharged}%")
            print(f"  Napiecie:     {status.voltage_v:.3f} V")
            print(f"  Prad:         {status.current_a:.3f} A")
            print(f"  Moc:          {power:.1f} W")
            print(f"  SOH:          {status.state_of_health}%")
            if status.temperature_t1_c is not None:
                print(f"  Temperatura T1/otoczenia: {status.temperature_t1_c} C")
            if status.temperature_mos_c is not None:
                print(f"  Temperatura MOS:          {status.temperature_mos_c} C")
            self.received_status = True

        elif frame_type == 0x22:
            cells = decode_cells(payload)
            print("\nNapiecia cel")
            for number, voltage in enumerate(cells, 1):
                print(f"  Cela {number}: {voltage:.3f} V")
            if cells:
                print(f"  Roznica: {max(cells) - min(cells):.3f} V")
            self.received_cells = bool(cells)

        if self.received_status and self.received_cells:
            self.complete.set()


async def find_device(address: str, name: str, scan_timeout: float):
    print(f"Skanowanie BLE przez {scan_timeout:.0f} s...")
    devices = await BleakScanner.discover(timeout=scan_timeout)
    address_upper = address.upper()
    name_lower = name.lower()

    for device in devices:
        device_name = device.name or ""
        if device.address.upper() == address_upper or name_lower in device_name.lower():
            print(f"Znaleziono: {device_name or '(bez nazwy)'} [{device.address}]")
            return device

    print("Znalezione urzadzenia:")
    for device in devices:
        print(f"  {device.name or '(bez nazwy)'} [{device.address}]")
    return None


async def run(args: argparse.Namespace) -> int:
    device = await find_device(args.address, args.name, args.scan_timeout)
    if device is None:
        print("Nie znaleziono akumulatora. Wylacz aplikacje BMS w telefonie i sprobuj ponownie.")
        return 2
    if args.scan_only:
        return 0

    reader = BmsReader()
    print("Laczenie z BMS...")
    async with BleakClient(device, timeout=args.connect_timeout) as client:
        print(f"Polaczono: {client.is_connected}")
        services = client.services
        if services.get_service(SERVICE_UUID) is None:
            raise RuntimeError(f"Brak wymaganej uslugi {SERVICE_UUID}")

        notify_characteristic = services.get_characteristic(NOTIFY_UUID)
        if notify_characteristic is None:
            raise RuntimeError(f"Brak charakterystyki powiadomien {NOTIFY_UUID}")

        # start_notify wlacza lokalny callback i zapisuje 01 00 do CCCD 0x2902.
        await client.start_notify(NOTIFY_UUID, reader.notification)
        print("Powiadomienia wlaczone (CCCD 0x2902 = 01 00). Czekam na dane...")

        # Jawny zapis jest redundantny dla Bleak, ale pomaga z niektorymi
        # niestandardowymi implementacjami GATT w modulach BMS.
        cccd = next(
            (descriptor for descriptor in notify_characteristic.descriptors if descriptor.uuid.lower() == CCCD_UUID),
            None,
        )
        if cccd is not None:
            try:
                await client.write_gatt_descriptor(cccd.handle, b"\x01\x00")
                print("Jawnie zapisano CCCD 0x2902 = 01 00.")
            except Exception as error:
                print(f"Jawny zapis CCCD pominiety ({error}); start_notify juz wlaczyl subskrypcje.")

        for frame_type in (0x21, 0x22):
            request = make_read_request(frame_type)
            try:
                print(f"Wysylam zapytanie 0x{frame_type:02X}: {request.hex(' ').upper()}")
                await client.write_gatt_char(WRITE_UUID, request, response=True)
                print(f"Zapis zapytania 0x{frame_type:02X} potwierdzony.")
            except Exception as error:
                print(f"Nie udalo sie wyslac zapytania 0x{frame_type:02X}: {error}")

        try:
            await asyncio.wait_for(reader.complete.wait(), timeout=args.data_timeout)
        except asyncio.TimeoutError:
            print("Minelo oczekiwanie na komplet ramek 0x21 i 0x22.")
            return 3
        finally:
            await client.stop_notify(NOTIFY_UUID)

    print("Odczyt zakonczony poprawnie.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Odczyt BLE inteligentnego akumulatora BMC")
    parser.add_argument("--address", default=DEFAULT_ADDRESS, help="Adres BLE akumulatora")
    parser.add_argument("--name", default=DEFAULT_NAME, help="Nazwa lub fragment nazwy BLE")
    parser.add_argument("--scan-timeout", type=float, default=12.0)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--data-timeout", type=float, default=20.0)
    parser.add_argument("--scan-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except KeyboardInterrupt:
        print("\nPrzerwano przez uzytkownika.")
    except Exception as error:
        print(f"Blad: {type(error).__name__}: {error}")
        raise SystemExit(1)
