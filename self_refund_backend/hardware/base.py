"""
Hardware interfaces used by the AutoRefund application.

The Flask routes only talk to these interfaces. Concrete implementations
(real USB devices or clearly labelled mocks) live in the sibling modules and
are chosen in ``hardware/__init__.py`` based on configuration, so a camera,
scale or barcode decoder can be swapped without touching business logic.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class HardwareError(RuntimeError):
    """Raised when a device is missing, disconnected or returns bad data."""


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------
@dataclass
class ScaleReading:
    weight_grams: float
    stable: bool
    connected: bool = True
    raw_unit: str = "g"
    message: str = ""
    raw: list = field(default_factory=list)


class ScaleDevice(ABC):
    #: human readable implementation name, reported by /api/hardware/status
    name = "scale"
    #: True for simulated devices so the UI/logs can never mistake them
    is_mock = False

    @abstractmethod
    def read(self) -> ScaleReading:
        """Return a single reading. Raises HardwareError when unavailable."""

    def read_live(self, samples=3, delay_s=0.15) -> ScaleReading:
        """Average a few non-zero readings for a smoother live value."""
        import time

        readings = []
        last = None
        for _ in range(samples):
            last = self.read()
            if last.weight_grams > 0:
                readings.append(last)
            time.sleep(delay_s)

        if not readings:
            return ScaleReading(0.0, False, True, message="No item on scale")

        avg = round(sum(r.weight_grams for r in readings) / len(readings), 2)
        stable = all(r.stable for r in readings)
        return ScaleReading(avg, stable, True, raw_unit=readings[-1].raw_unit)

    def status(self) -> dict:
        try:
            reading = self.read()
            return {"connected": True, "implementation": self.name,
                    "mock": self.is_mock, "weight_grams": reading.weight_grams}
        except HardwareError as exc:
            return {"connected": False, "implementation": self.name,
                    "mock": self.is_mock, "error": str(exc)}

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
class CameraDevice(ABC):
    name = "camera"
    is_mock = False

    @abstractmethod
    def ensure_camera(self) -> bool:
        """Open the camera if needed. Returns False when unavailable."""

    @abstractmethod
    def get_frame(self):
        """Return the latest BGR frame (numpy array) or None."""

    @abstractmethod
    def capture_image(self) -> dict:
        """Save a still image. Returns filename / relative_path / full_path."""

    @abstractmethod
    def generate_mjpeg_frames(self):
        """Yield multipart MJPEG chunks for the live preview."""

    @abstractmethod
    def release_camera(self):
        """Release the underlying device."""

    @property
    def current_source(self):
        return None

    def status(self) -> dict:
        ok = self.ensure_camera()
        return {"connected": bool(ok), "implementation": self.name,
                "mock": self.is_mock, "source": str(self.current_source)}
