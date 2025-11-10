#!/bin/bash

echo "========================================="
echo "ESP32 Device Finder for macOS"
echo "========================================="
echo ""

echo "Step 1: Current USB serial devices:"
BEFORE=$(ls /dev/{tty,cu}.* 2>/dev/null | grep -E "(usb|SLAB|wch|serial)" | sort)
if [ -z "$BEFORE" ]; then
    echo "  No USB serial devices found"
else
    echo "$BEFORE"
fi
echo ""

echo "Step 2: Now UNPLUG your ESP32 if it's connected..."
read -p "Press Enter when unplugged..."
echo ""

sleep 1
UNPLUGGED=$(ls /dev/{tty,cu}.* 2>/dev/null | grep -E "(usb|SLAB|wch|serial)" | sort)

echo "Step 3: Now PLUG IN your ESP32..."
read -p "Press Enter when connected..."
echo ""

sleep 2
AFTER=$(ls /dev/{tty,cu}.* 2>/dev/null | grep -E "(usb|SLAB|wch|serial)" | sort)

echo "Devices after connecting:"
if [ -z "$AFTER" ]; then
    echo "  No USB serial devices found"
    echo ""
    echo "❌ ESP32 NOT DETECTED"
    echo ""
    echo "Possible issues:"
    echo "  1. USB drivers not installed (see TROUBLESHOOTING_CONNECTION.md)"
    echo "  2. USB cable is power-only (try a different cable)"
    echo "  3. ESP32 is faulty or not powered on"
    echo ""
    echo "To install drivers:"
    echo "  - For CP2102 chip: brew install --cask silicon-labs-vcp-driver"
    echo "  - For CH340 chip: brew install --cask wch-ch34x-usb-serial-driver"
    echo "  Then RESTART your Mac"
else
    echo "$AFTER"
    echo ""
    
    NEW_DEVICE=$(comm -13 <(echo "$BEFORE") <(echo "$AFTER") 2>/dev/null)
    
    if [ -n "$NEW_DEVICE" ]; then
        echo "✅ NEW DEVICE DETECTED:"
        echo "$NEW_DEVICE"
        echo ""
        
        CU_DEVICE=$(echo "$NEW_DEVICE" | grep "^/dev/cu\." | head -1)
        if [ -n "$CU_DEVICE" ]; then
            echo "Use this device: $CU_DEVICE"
            echo ""
            echo "To upload code:"
            echo "  ./upload.sh $CU_DEVICE"
            echo ""
            echo "To connect to REPL:"
            echo "  screen $CU_DEVICE 115200"
        fi
    else
        echo "⚠️  No new device detected"
        echo ""
        echo "The ESP32 may already be connected, or drivers are missing."
        echo "Check TROUBLESHOOTING_CONNECTION.md for help."
    fi
fi

echo ""
echo "System USB info:"
system_profiler SPUSBDataType 2>/dev/null | grep -A 5 -i "serial\|uart\|cp210\|ch340\|ftdi" | head -20

