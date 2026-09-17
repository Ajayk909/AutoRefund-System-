"""
One-time helper for upgrading a Phase 0/1 kiosk PC.

Hardware settings (CAMERA_INDEX, SCALE_VENDOR_ID, ...) used to live in
self_refund_backend\\.env. The kiosk agent owns the hardware now, so copy any
of those settings that kiosk_agent\\.env does not define yet. Nothing else is
copied (no database password) and existing agent settings are never changed.

    python scripts\\import_backend_settings.py ..\\self_refund_backend\\.env .env
"""
import sys

HARDWARE_KEYS = ("HARDWARE_MODE", "CAMERA_MODE", "SCALE_MODE", "CAMERA_INDEX", "CAMERA_BACKEND",
                 "CAMERA_WIDTH", "CAMERA_HEIGHT", "SCALE_VENDOR_ID", "SCALE_PRODUCT_ID",
                 "SCALE_READ_TIMEOUT_MS", "MOCK_SCALE_GRAMS")


def read_env(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return values


# Values in .env.example: a setting still at its template value was never
# chosen by the user and may be replaced by the backend's value.
TEMPLATE_VALUES = {"HARDWARE_MODE": "real", "CAMERA_INDEX": "", "CAMERA_BACKEND": "auto",
                   "CAMERA_WIDTH": "640", "CAMERA_HEIGHT": "480", "SCALE_VENDOR_ID": "0x0922",
                   "SCALE_PRODUCT_ID": "0x8003", "SCALE_READ_TIMEOUT_MS": "2000",
                   "MOCK_SCALE_GRAMS": "250"}


def main(backend_env, agent_env):
    backend = read_env(backend_env)
    with open(agent_env, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    index = {line.split("=", 1)[0].strip(): i for i, line in enumerate(lines)
             if "=" in line and not line.lstrip().startswith("#")}
    copied = []
    for key in HARDWARE_KEYS:
        if key not in backend:
            continue
        if key not in index:
            lines.append(f"{key}={backend[key]}")
            copied.append(key)
            continue
        current = lines[index[key]].split("=", 1)[1].strip()
        if current != backend[key] and current in ("", TEMPLATE_VALUES.get(key)):
            lines[index[key]] = f"{key}={backend[key]}"
            copied.append(key)
    with open(agent_env, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("Copied hardware settings to the agent: " + (", ".join(copied) if copied else "none"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2]))
