"""
Manual hardware check for the USB scale (run on the kiosk PC):

    python test_scale.py            # read the configured scale 10 times
    python test_scale.py --list     # list every USB HID device (find VID/PID)
"""
import sys
import time

from hardware import HardwareError, get_scale
from hardware.scale_service import HidPostalScale

if "--list" in sys.argv:
    devices = HidPostalScale.list_hid_devices()
    if not devices:
        print("No HID devices found (or hidapi is not installed).")
    for d in devices:
        print(f"VID={d['vendor_id']} PID={d['product_id']}  "
              f"{d['manufacturer'] or ''} {d['product'] or ''}")
    sys.exit(0)

scale = get_scale()
print(f"Using scale implementation: {scale.name} (mock={scale.is_mock})")
for _ in range(10):
    try:
        r = scale.read()
        print(f"Weight: {r.weight_grams} g  stable={r.stable}  unit={r.raw_unit}  raw={r.raw}")
    except HardwareError as e:
        print("Error:", e)
    time.sleep(0.5)
