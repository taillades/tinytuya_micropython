# ESP32 Tuya Button Controller

Control multiple Tuya smart devices with a single physical button press on an ESP32.

## Features

- ✅ Control multiple Tuya devices simultaneously
- ✅ Smart toggle: syncs all devices to same state
- ✅ Uses tinytuya export format for easy configuration
- ✅ Tuya Protocol 3.4 support with session key negotiation
- ✅ Configurable button debouncing and press detection
- ✅ No external dependencies on ESP32 (manual HMAC implementation)

## Hardware Requirements

- ESP32 DevKit (any variant)
- Push button
- Optional: 100nF decoupling capacitor for button stability
- Breadboard and wires

## GPIO Connections

```
ESP32 GPIO 32 ----[Button]---- GND
                   |
                  [=] 100nF capacitor to GND (optional, for debouncing)
```

The button connects GPIO 32 to GND when pressed. Internal pull-up resistor is enabled.

---

## Quick Setup Guide

### Step 1: Get Device Information from Tinytuya

First, discover your Tuya devices and get their local keys:

```bash
# Install tinytuya
pip3 install tinytuya

# Run wizard to get API credentials
python3 -m tinytuya wizard

# Scan your local network for devices
python3 -m tinytuya scan
```

The scan will create a `snapshot.json` file with all discovered devices. It looks like this:

```json
{
  "timestamp": 1234567890,
  "devices": [
    {
      "id": "eb66d363a50aa9f52ek0r0",
      "ip": "10.0.0.33",
      "key": "jKLAO_#RVbv|hdz9",
      "ver": "3.4",
      "name": "Living Room Lamp",
      ...
    }
  ]
}
```

### Step 2: Create Configuration File

Create `config.json` in the `esp32/` directory:

```json
{
  "wifi": {
    "ssid": "YourWiFiName",
    "password": "YourWiFiPassword"
  },
  "button": {
    "pin": 32,
    "debounce_ms": 1000,
    "press_time_ms": 100
  },
  "devices": [
    // Paste the "devices" array from snapshot.json here
  ]
}
```

**Important**: Only devices with a `key` field will be used. Devices without keys are automatically skipped.

### Step 3: Test in Python (Recommended)

Before deploying to ESP32, test that the protocol works:

```bash
# Make sure you're in the esp32/ directory with config.json
cd esp32/

# Run the test script
python3 test_tuya_protocol.py
```

This lets you:
- Select a device from your config
- Test connection and status
- Toggle devices manually
- See detailed protocol debug output

### Step 4: Flash MicroPython to ESP32

Download firmware from https://micropython.org/download/esp32/

```bash
# Install esptool
pip3 install esptool

# Erase flash
esptool.py --chip esp32 --port /dev/cu.usbserial-0001 erase_flash

# Flash MicroPython
esptool.py --chip esp32 --port /dev/cu.usbserial-0001 --baud 460800 \
  write_flash -z 0x1000 ESP32_GENERIC-20250911-v1.26.1.bin
```

**Note**: Replace `/dev/cu.usbserial-0001` with your serial port:
- macOS: `/dev/cu.usbserial-*` or `/dev/cu.SLAB_USBtoUART`
- Linux: `/dev/ttyUSB0` or `/dev/ttyACM0`
- Windows: `COM3`, `COM4`, etc.

Find your port with:
```bash
# macOS/Linux
ls /dev/cu.* /dev/tty* | grep -i usb

# Or use the included script
./find_esp32.sh
```

### Step 5: Install Crypto Library on ESP32

Connect to the ESP32 REPL:

```bash
screen /dev/cu.usbserial-0001 115200
```

Then in the Python prompt:

```python
import network
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("YourWiFiName", "YourPassword")

# Wait for connection
import time
while not wlan.isconnected():
    time.sleep(1)
    print("Connecting...")

print("Connected:", wlan.ifconfig())

# Install crypto library
import mip
mip.install("micropython-ucryptolib")
```

Press `Ctrl+A` then `K` to exit screen.

### Step 6: Upload Files to ESP32

```bash
# Install ampy
pip3 install adafruit-ampy

# Upload config and main script
ampy --port /dev/cu.usbserial-0001 put config.json
ampy --port /dev/cu.usbserial-0001 put main.py
```

### Step 7: Test It!

Reset the ESP32 (press the EN/RST button or power cycle).

Monitor the output:
```bash
screen /dev/cu.usbserial-0001 115200
```

You should see:
```
==================================================
ESP32 Tuya Button Controller
==================================================
[*] Connecting to WiFi: YourWiFi
[*] WiFi connected: 10.0.0.x
[*] Loaded 3 device(s)
    - Living Room Lamp
    - Bedroom Lamp
    - Desk Lamp
[*] Ready! Press button on GPIO 32
[*] Button must be held for 100ms to trigger
[*] Waiting for button press...
```

Press your button and watch the magic! ✨

---

## How It Works

### Multi-Device Toggle Logic

When you press the button:

1. **Check all device states**
2. **If all devices are in the same state** (all ON or all OFF):
   - Toggle them all to the opposite state
3. **If devices are in mixed states** (some ON, some OFF):
   - Turn them all ON

This ensures devices stay synchronized!

### Button Detection

- Button must be held for **100ms** to register (configurable in `config.json`)
- Prevents accidental triggers from electrical noise
- Debounce time of **1000ms** between accepted presses

---

## Configuration Reference

### WiFi Section
```json
"wifi": {
  "ssid": "YourNetwork",      // Your WiFi name
  "password": "YourPassword"   // Your WiFi password
}
```

### Button Section
```json
"button": {
  "pin": 32,              // GPIO pin number
  "debounce_ms": 1000,    // Min time between presses
  "press_time_ms": 100    // How long to hold button
}
```

### Devices Section

Uses the exact format from `tinytuya scan` output. Only these fields are used:
- `id` - Device ID
- `ip` - Local IP address  
- `key` - Encryption key (required!)
- `ver` - Protocol version ("3.3" or "3.4")
- `name` - Display name (optional)

All other fields from tinytuya (mac, productKey, etc.) are preserved but ignored.

---

## Troubleshooting

### "No devices with keys found"

Some devices in your snapshot.json might not have the `key` field populated. This happens when:
- Device wasn't properly linked to tinytuya cloud API
- You need to run `python3 -m tinytuya wizard` first

Solution: Run the wizard to link your Tuya account, then scan again.

### WiFi Won't Connect

- ESP32 only supports **2.4GHz WiFi** (not 5GHz)
- Check SSID and password are correct
- Move ESP32 closer to router
- Some special characters in passwords might cause issues

### Button Triggers Multiple Times

- Add a physical decoupling capacitor (100nF) across the button
- Increase `press_time_ms` in config.json
- Increase `debounce_ms` in config.json

### Devices Not Responding

- Verify IP addresses are correct (they may change with DHCP)
- Check that devices have `key` field in config
- Ensure ESP32 and devices are on same network
- Try testing with `test_tuya_protocol.py` first

### "Connection refused" Error

- Device IP changed (re-run tinytuya scan)
- Device is turned off or unplugged
- Network firewall blocking ESP32

---

## File Structure

```
esp32/
├── main.py                  # Main ESP32 script
├── config.json              # Your configuration (create this)
├── test_tuya_protocol.py    # Test script for desktop Python
├── README.md                # This file
├── CONFIG_README.md         # Detailed config documentation
└── find_esp32.sh            # Helper to find ESP32 port
```

---

## Protocol Details

This implementation supports **Tuya Protocol 3.4** with:
- Full session key negotiation (3-step handshake)
- HMAC-SHA256 authentication
- AES-ECB encryption
- Manual HMAC implementation (no external libraries on ESP32)
- Proper handling of double-packet status responses

---

## Advanced: Choosing GPIO Pins

**Safe GPIOs for button:**
- ✅ GPIO 32 (default)
- ✅ GPIO 33
- ✅ GPIO 26
- ✅ GPIO 27
- ✅ GPIO 25
- ✅ GPIO 14

**Avoid these:**
- ❌ GPIO 0, 2, 5, 12, 15 (boot strapping pins)
- ❌ GPIO 6-11 (connected to internal flash)
- ❌ GPIO 34-39 (input only, no pull-up resistors)

---

## Credits

Built with love for home automation enthusiasts who want local control! 🏠✨

Based on reverse-engineered Tuya protocol and the excellent [tinytuya](https://github.com/jasonacox/tinytuya) library for device discovery.
