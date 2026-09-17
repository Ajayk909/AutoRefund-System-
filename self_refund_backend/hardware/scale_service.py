import time
import hid

VENDOR_ID = 0x0922
PRODUCT_ID = 0x8003

device = None


def connect_scale():
    global device

    try:
        if device is not None:
            try:
                device.close()
            except Exception:
                pass

        device = hid.device()
        device.open(VENDOR_ID, PRODUCT_ID)
        device.set_nonblocking(0)  # blocking read works better for DYMO
        print("DYMO scale connected")
        return True
    except Exception as e:
        print("Scale connection failed:", e)
        device = None
        return False


def _read_packet():
    global device

    if device is None:
        if not connect_scale():
            return None

    try:
        data = device.read(6, timeout_ms=2000)
        if not data or len(data) < 6:
            return None
        return data
    except Exception as e:
        print("Scale read failed:", e)
        device = None
        return None


def _decode_dymo_packet(data):
    """
    Typical DYMO packet layout:
    data[2] = unit
    data[3] = exponent (signed)
    data[4] = low byte
    data[5] = high byte
    """
    try:
        unit_code = data[2]
        exponent = data[3]
        raw_weight = data[4] + (data[5] << 8)

        # convert exponent from unsigned byte to signed int
        if exponent > 128:
            exponent = exponent - 256

        value = raw_weight * (10 ** exponent)

        # DYMO commonly reports ounces or pounds depending on unit_code
        # 11 is usually ounces on many DYMO examples
        # convert to grams when needed
        if unit_code == 11:  # ounces
            grams = value * 28.3495
        elif unit_code == 12:  # pounds
            grams = value * 453.592
        else:
            # assume already grams if unit unknown
            grams = value

        return round(float(grams), 2)
    except Exception as e:
        print("Decode failed:", e, "data=", data)
        return 0.0


def get_weight_grams():
    data = _read_packet()
    if data is None:
        return 0.0

    print("RAW SCALE DATA:", data)
    return _decode_dymo_packet(data)


def get_live_weight_grams():
    """
    Average a few reads for a smoother live value.
    """
    readings = []

    for _ in range(3):
        weight = get_weight_grams()
        if weight > 0:
            readings.append(weight)
        time.sleep(0.15)

    if not readings:
        return 0.0

    return round(sum(readings) / len(readings), 2)
