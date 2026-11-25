# 🌸 LotusLamp X — Windows Bluetooth Controller

A modern Windows desktop app to control **ELK-BLEDOM / LotusLamp X** compatible
Bluetooth Low Energy RGB LED strips — the same hardware controlled by the
*LotusLamp X* Android app.

---

## ✨ Features

| Feature | Description |
|---|---|
| **BLE Device Scan** | Scans for nearby Bluetooth devices, highlights known LED controllers |
| **Connect / Disconnect** | One-click connect/disconnect with live status indicator |
| **Power Toggle** | Turn the strip on or off |
| **Colour Wheel** | Interactive HSV wheel for intuitive colour picking |
| **RGB Sliders** | Fine-tune Red, Green, Blue channels independently |
| **Hex Input** | Type any `#RRGGBB` hex code directly |
| **System Colour Picker** | Windows native colour chooser dialog |
| **Quick Palette** | 10 preset colour swatches |
| **Brightness Control** | Slider from 0–100 % |
| **Built-in Effects** | 22 hardware animation modes (RGB jump, fade, blink, strobe…) |
| **Effect Speed** | Control animation speed 0–100 % |

---

## 📦 Download (Windows `.exe`)

No Python installation required — grab the standalone executable from the **[Releases](https://github.com/overlordJ/Windows-App-for-LotusLamp-X/releases)** page (`LotusLamp X.exe`).

> [!NOTE]
> **VirusTotal & SmartScreen Disclaimer:**
> `LotusLamp X.exe` is packaged with **PyInstaller** (`--onefile`) and is **not code-signed**. Because PyInstaller's self-extracting bootloader unpacks Python and dependencies into `%TEMP%` at launch, a few heuristic antivirus engines on VirusTotal (such as **Bkav Pro** `W32.Malware.89A96B3` and **SecureAge** `Malicious`) may flag it as a false positive, and Windows Defender SmartScreen may show an "Unknown publisher" prompt (**More info → Run anyway**).
>
> All source code is open in this repository — if you prefer not to run the prebuilt binary, you can inspect the code and run it directly from source using the steps below.

---

## 🚀 Quick Start (Run from Source)

### 1. Install Python 3.10+
Download from [python.org](https://python.org) if not already installed.

### 2. Install Dependencies
```bat
pip install -r requirements.txt
```

### 3. Run the App
```bat
# Option A — double-click
launch.bat

# Option B — terminal
python app.py
```

---

## 🔵 Bluetooth Protocol

The app communicates via **BLE GATT** using the ELK-BLEDOM / LotusLamp X protocol:

| Property | Value |
|---|---|
| Service UUID | `0000fff0-0000-1000-8000-00805f9b34fb` |
| Write Characteristic | `0000fff3-0000-1000-8000-00805f9b34fb` |
| Fallback Service | `0000ffe0-0000-1000-8000-00805f9b34fb` |
| Fallback Write | `0000ffe1-0000-1000-8000-00805f9b34fb` |
| Frame format | 9-byte: `7E [cmd] [data…] EF` |

The app auto-detects which UUID pair your controller uses.

---

## 🛠 Troubleshooting

| Problem | Fix |
|---|---|
| Device not found | Make sure the LED strip is powered on and in range. Try toggling Bluetooth. |
| Connection fails | Try the scan again; some controllers need to be re-powered. |
| Commands don't work | Your controller may use an alternate protocol variant. Use `nRF Connect` to sniff UUIDs. |
| Bluetooth adapter missing | Ensure your PC has BT 4.0+ LE support (`winrt` backend requires Windows 10 1709+). |

---

## 📁 Project Structure

```
lotuslamp-controller/
├── app.py              # Main GUI (CustomTkinter)
├── ble_controller.py   # BLE logic (bleak)
├── requirements.txt    # Python dependencies
├── launch.bat          # Windows launcher
├── icon.ico            # Application icon
├── .gitignore
└── README.md
```


---

## 📸 Screenshots

- Image 1: https://ibb.co/8Vjn5wn
- Image 2: https://ibb.co/WWRqbz2m
