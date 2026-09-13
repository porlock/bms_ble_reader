# BMS BLE Reader

Prosta aplikacja dla Windows/Pythona odczytujaca inteligentny akumulator BMC przez Bluetooth Low Energy.

## Instalacja

W PowerShell:

```powershell
cd "C:\Users\zieli\Downloads\OpenVTx-master\src\bms_ble_reader"
python -m pip install -r requirements.txt
```

Przed uruchomieniem wlacz Bluetooth i zamknij aplikacje BMS w telefonie, aby telefon nie zajmowal polaczenia.

## Uruchomienie

```powershell
python app.py
```

Program domyslnie szuka urzadzenia `HS030302BC26150127` lub adresu `8E:8A:C2:91:74:A2`.

Sam skan bez laczenia:

```powershell
python app.py --scan-only
```

Inne urzadzenie:

```powershell
python app.py --address "AA:BB:CC:DD:EE:FF" --name "fragment-nazwy"
```

Po polaczeniu program wlacza powiadomienia na charakterystyce `00000003-0000-1000-8000-00805f9b34fb`. Biblioteka Bleak zapisuje wtedy `01 00` do deskryptora CCCD `0x2902`; aplikacja wykonuje tez jawny zapis dla zgodnosci z nietypowym GATT BMS-a. Nastepnie wysyla zapytania odczytowe `AA 21 00 21 00` i `AA 22 00 22 00`. Ramka odpowiedzi `0x21` zawiera stan naladowania oraz temperatury T1/otoczenia i MOS, a `0x22` napiecia cel.
