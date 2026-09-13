# BMS BLE Reader

A Python command-line application for Windows that reads a smart battery's BMS over Bluetooth Low Energy.

It decodes battery status, state of charge, temperatures, and individual cell voltages. The parser includes tests for complete and fragmented response frames.

## Installation

Run these commands from the project directory in PowerShell:

```powershell
python -m pip install -r requirements.txt
```

Enable Bluetooth and close the phone's BMS app before connecting, so it does not occupy the connection.

## Usage

```powershell
python app.py
```

By default, the application searches for the device named `HS030302BC26150127` or address `8E:8A:C2:91:74:A2`. These defaults refer to the original test device; specify your own device as needed.

Scan without connecting:

```powershell
python app.py --scan-only
```

Select another device:

```powershell
python app.py --address "AA:BB:CC:DD:EE:FF" --name "device-name-fragment"
```

## Protocol

After connecting, the program enables notifications on characteristic `00000003-0000-1000-8000-00805f9b34fb`. Bleak writes `01 00` to the CCCD descriptor `0x2902`; the application also performs an explicit write for compatibility with this BMS's unusual GATT implementation.

It then sends read requests `AA 21 00 21 00` and `AA 22 00 22 00`. Response frame `0x21` contains battery status, state of charge, and T1/ambient and MOS temperatures. Frame `0x22` contains cell voltages.

## Tests

```powershell
python -m unittest test_parser -v
```
