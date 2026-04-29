from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Literal


def write_output(
    glb_source: Path,
    output: Literal["bytes", "path", "file"],
    output_path: Path | None,
) -> bytes | Path | BinaryIO:
    """Package the generated GLB for the caller.

    Args:
        glb_source: Path to the GLB file produced by the Trellis Space (lives
            inside gradio_client's temp cache; valid only for the duration of
            the call).
        output: Delivery mode — ``"bytes"`` returns raw file bytes in memory;
            ``"path"`` copies the file to *output_path* (or a caller-owned
            ``NamedTemporaryFile`` when *output_path* is None); ``"file"``
            returns a seeked ``BytesIO``.
        output_path: Destination path used only when *output* is ``"path"``.
            Ignored otherwise.

    Returns:
        ``bytes``, ``pathlib.Path``, or ``io.BytesIO`` depending on *output*.
    """

    if output == "bytes":
        return glb_source.read_bytes()

    if output == "file":
        buf = io.BytesIO(glb_source.read_bytes())
        buf.seek(0)
        return buf

    # output == "path"
    if output_path is not None:
        dest = Path(output_path)
        shutil.copy2(glb_source, dest)
        return dest

    # No output_path given — move to a caller-owned tempfile.
    tmp = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
    tmp.close()
    dest = Path(tmp.name)
    shutil.copy2(glb_source, dest)
    return dest
