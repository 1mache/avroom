# Trellis Module (image-to-3D)

`TrellisModule/` is a small Python package (`avroom_trellis`) that converts a segmented cutout image into a 3D GLB model by calling the public Hugging Face Space **`microsoft/TRELLIS.2`** via `gradio_client`.

> Status: **Not wired into the FastAPI service** (`fastApi-app/`) or the end-to-end `/images/*` flow. It is a standalone module + manual test.

## Where it lives

- Code: [`TrellisModule/`](../TrellisModule/)
- Python package metadata: [`TrellisModule/pyproject.toml`](../TrellisModule/pyproject.toml)
- Main implementation: [`TrellisModule/src/generator.py`](../TrellisModule/src/generator.py)

## Install

The repo root [`requirements.txt`](../requirements.txt) installs this package editable:

```80:80:requirements.txt
-e ./TrellisModule
```

The module also depends on `gradio_client>=1.4` (also present in `requirements.txt`) and lists its minimal deps in `TrellisModule/pyproject.toml`.

## Public API

`avroom_trellis` exports two public symbols:

```1:6:TrellisModule/src/__init__.py
from .generator import Trellis3DGenerator
from .quality import Quality

__all__ = ["Trellis3DGenerator", "Quality"]
```

### `Trellis3DGenerator.generate(...)`

The main entry point is `Trellis3DGenerator.generate(...)`:

```23:115:TrellisModule/src/generator.py
class Trellis3DGenerator:
    """Converts a segmented cutout image into a GLB 3D model via Trellis 2.
    ...
    """

    def generate(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        quality: Quality = Quality.FAST,
        output: str = "bytes",
        output_path: Path | None = None,
        seed: int = 0,
    ) -> bytes | Path | BinaryIO:
        """Generate a GLB 3D model from a cutout image.
        ...
        """
```

- **Inputs**: bytes (PNG/JPEG), numpy array (BGR/BGRA), `PIL.Image`, or a filesystem path. The numpy array case supports **(H,W,4) BGRA**, which matches the `cutout_bgra` returned by `ObjectRemover.remove_object(...)`.
- **Output modes**:
  - `output="bytes"` (default): return GLB `bytes`.
  - `output="path"`: write GLB to `output_path` (or a temporary file) and return a `Path`.
  - `output="file"`: return a seeked `BytesIO`.

## Quality presets

Quality is an enum with three presets:

```7:25:TrellisModule/src/quality.py
class Quality(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"
```

Each preset selects parameters such as resolution, sampling steps, decimation target, and texture size (see `PRESETS` in `quality.py`).

## Operational constraints

The generator calls the public Space using `gradio_client`, and the client is lazily connected on the first `generate()` call:

```23:79:TrellisModule/src/generator.py
class Trellis3DGenerator:
    _SPACE_ID_DEFAULT: str = "microsoft/TRELLIS.2"
    _API_IMAGE_TO_3D: str = "/image_to_3d"
    _API_EXTRACT_GLB: str = "/extract_glb"

    @property
    def _client(self):  # type: ignore[return]
        if self.__client is None:
            ...
            self.__client = Client(self._space_id, hf_token=self._hf_token)
```

Because the Space runs queued / rate-limited (Zero GPU), it is suitable for manual testing and MVP usage, but not for high-concurrency production workloads.

## Manual integration smoke test

There is a manual script that runs **ObjectRemover → Trellis** and writes a GLB file:

```1:15:TrellisModule/tests/test_smoke.py
"""Smoke test: ObjectRemover cutout -> Trellis3DGenerator -> GLB bytes.
...
Usage (from repo root):
    python TrellisModule/tests/test_smoke.py
...
"""
```

This script hits the live Space and may be slow due to model load + queue wait. It is not intended for CI.

