"""Atomic file writing: write to temp file, then rename for crash safety."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: str | Path, content: str | bytes, *, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically.

    Writes to a temporary file in the same directory, then uses ``os.replace``
    to atomically swap it into place. If the process crashes during the write,
    the original file remains intact.

    Args:
        path: Target file path.
        content: Content to write (str or bytes).
        encoding: Text encoding (ignored for bytes content).
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    is_bytes = isinstance(content, bytes)
    mode = "wb" if is_bytes else "w"
    kwargs = {} if is_bytes else {"encoding": encoding}

    fd, tmp_path = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, mode, **kwargs) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(target))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
