"""
Backwards-compatibility shim.

The camera code of the Raspberry Pi prototype lived here. It now lives in
``hardware/camera_service.py`` behind the hardware abstraction layer; use
``hardware.get_camera()`` instead of importing this module.
"""
from hardware.camera_service import OpenCVCamera as USBCameraService  # noqa: F401

__all__ = ["USBCameraService"]
