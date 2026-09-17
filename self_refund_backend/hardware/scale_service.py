"""
USB HID postal scale (DYMO M-series) implementation.

How the original Raspberry Pi prototype talked to the scale, and how it works
on Windows:

* The DYMO scale is a standard USB HID "Point of Sale scale" device
  (vendor 0x0922, product 0x8003 by default). It is NOT a keyboard and NOT a
  serial/COM device, so no vendor driver is needed.
* We use the cross-platform ``hidapi`` Python package (``import hid``). On the
  Pi it used Linux hidraw; on Windows the same package uses the built-in
  Windows HID API, so the code path is identical. No admin rights are needed.
* Each input report is 6 bytes::

      [0] report id (3)
      [1] status   (2 = zero, 3 = in motion, 4 = stable weight,
                    5 = under zero, 6 = over weight, 7/8 = needs calibration)
      [2] unit     (2 = g, 3 = kg, 11 = oz, 12 = lb ...)
      [3] exponent (signed byte, power of ten)
      [4] weight low byte
      [5] weight high byte

The module-level ``get_weight_grams`` / ``get_live_weight_grams`` functions
are kept for backwards compatibility with ``test_scale.py``.
"""
import logging
import threading

from .base import HardwareError, ScaleDevice, ScaleReading

log = logging.getLogger("autorefund.hardware.scale")

try:  # hidapi is optional so the backend can still start in mock mode
    import hid  # type: ignore
except Exception as exc:  # pragma: no cover - depends on the machine
    hid = None
    _HID_IMPORT_ERROR = exc
else:
    _HID_IMPORT_ERROR = None


# HID POS "Weight Unit" usage values -> grams multiplier
UNIT_TO_GRAMS = {
    1: ("mg", 0.001),
    2: ("g", 1.0),
    3: ("kg", 1000.0),
    11: ("oz", 28.3495),
    12: ("lb", 453.592),
}

STATUS_ZERO = 2
STATUS_IN_MOTION = 3
STATUS_STABLE = 4
STATUS_UNDER_ZERO = 5
STATUS_OVER_WEIGHT = 6


def decode_dymo_packet(data):
    """Decode a 6-byte DYMO HID report into a ScaleReading.

    Pure function so it can be unit-tested without hardware.
    """
    if not data or len(data) < 6:
        raise HardwareError("Incomplete scale report")

    status = data[1]
    unit_code = data[2]
    exponent = data[3]
    raw_weight = data[4] + (data[5] << 8)

    if exponent >= 128:  # unsigned byte -> signed int
        exponent -= 256

    value = raw_weight * (10 ** exponent)

    unit_name, factor = UNIT_TO_GRAMS.get(unit_code, (None, None))
    if factor is None:
        # Same fallback as the Pi prototype: assume grams, but log it.
        log.warning("Unknown scale unit code %s, assuming grams (data=%s)",
                    unit_code, list(data))
        unit_name, factor = f"unknown({unit_code})", 1.0

    grams = round(float(value) * factor, 2)

    if status in (STATUS_ZERO, STATUS_UNDER_ZERO):
        grams = 0.0
    if status == STATUS_OVER_WEIGHT:
        raise HardwareError("Scale is over its maximum weight")
    if status in (7, 8):
        raise HardwareError("Scale needs to be re-zeroed / calibrated")

    stable = grams > 0 and status != STATUS_IN_MOTION
    return ScaleReading(grams, stable, True, raw_unit=unit_name, raw=list(data))


class HidPostalScale(ScaleDevice):
    """Real USB HID scale (DYMO M5/M10/M25 and compatible)."""

    name = "hid-postal-scale"

    def __init__(self, vendor_id=0x0922, product_id=0x8003, timeout_ms=2000):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.timeout_ms = timeout_ms
        self._device = None
        self._last_reading = None
        self._lock = threading.Lock()

    # -- connection ---------------------------------------------------------
    def _connect(self):
        if hid is None:
            raise HardwareError(
                f"hidapi package is not available: {_HID_IMPORT_ERROR}")

        self._close_no_lock()
        try:
            device = hid.device()
            device.open(self.vendor_id, self.product_id)
            device.set_nonblocking(0)  # blocking read works better for DYMO
        except Exception as exc:
            raise HardwareError(
                "Scale not found (VID=0x%04x PID=0x%04x): %s"
                % (self.vendor_id, self.product_id, exc)) from exc

        self._device = device
        log.info("Scale connected (VID=0x%04x PID=0x%04x)",
                 self.vendor_id, self.product_id)

    def _close_no_lock(self):
        self._last_reading = None
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def close(self):
        with self._lock:
            self._close_no_lock()

    # -- reading ------------------------------------------------------------
    def read(self) -> ScaleReading:
        with self._lock:
            if self._device is None:
                self._connect()
            try:
                data = self._device.read(6, timeout_ms=self.timeout_ms)
            except Exception as exc:
                self._close_no_lock()  # force reconnect next time
                raise HardwareError(f"Scale read failed: {exc}") from exc

            if not data or len(data) < 6:
                # No new report within the timeout. Some scales only send a
                # report when the weight changes, so re-use the last value
                # this connection produced. If we never got one, the scale is
                # most likely off / asleep.
                if self._last_reading is not None:
                    return self._last_reading
                raise HardwareError("No data received from scale (is it on?)")

            log.debug("RAW SCALE DATA: %s", list(data))
            reading = decode_dymo_packet(data)
            self._last_reading = reading
            return reading

    @staticmethod
    def list_hid_devices():
        """Helper for setup/troubleshooting: list all HID devices."""
        if hid is None:
            return []
        return [
            {
                "vendor_id": "0x%04x" % d["vendor_id"],
                "product_id": "0x%04x" % d["product_id"],
                "manufacturer": d.get("manufacturer_string"),
                "product": d.get("product_string"),
            }
            for d in hid.enumerate()
        ]


# ---------------------------------------------------------------------------
# Backwards compatible helpers (used by test_scale.py in the Pi prototype)
# ---------------------------------------------------------------------------
def get_weight_grams():
    from . import get_scale

    return get_scale().read().weight_grams


def get_live_weight_grams():
    from . import get_scale

    return get_scale().read_live().weight_grams
