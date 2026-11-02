"""Inspect the pinned LIBERO NumPy pickle format without loading robot libraries."""
from __future__ import annotations

import io
import pickle
from pathlib import Path
import zipfile


class _ArrayShape:
    def __setstate__(self, state):
        if not isinstance(state, tuple) or len(state) != 5:
            raise ValueError("Unsupported NumPy array pickle state")
        shape = state[1]
        if not isinstance(shape, tuple) or not shape or any(type(n) is not int or n < 0 for n in shape):
            raise ValueError("Invalid initial-state array shape")
        self.shape = shape


class _DtypePlaceholder:
    def __init__(self, *args):
        pass

    def __setstate__(self, state):
        pass


def _reconstruct_shape(*args):
    return _ArrayShape()


def _latin1_encode(value, encoding):
    if encoding != "latin1" or not isinstance(value, str):
        raise ValueError("Unsupported pickle encoding")
    return value.encode("latin1")


class _ShapeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        allowed = {
            ("numpy.core.multiarray", "_reconstruct"): _reconstruct_shape,
            ("numpy._core.multiarray", "_reconstruct"): _reconstruct_shape,
            ("numpy", "ndarray"): _ArrayShape,
            ("numpy", "dtype"): _DtypePlaceholder,
            ("_codecs", "encode"): _latin1_encode,
        }
        if (module, name) not in allowed:
            raise ValueError(f"Unsupported pickle global: {module}.{name}")
        return allowed[(module, name)]

    def persistent_load(self, pid):
        raise ValueError("Persistent pickle references are unsupported")


def initial_state_shape(path: Path) -> tuple[int, ...]:
    """Read array shape from this benchmark's Torch ZIP container.

    Only inert replacements for the known NumPy reconstruction globals are
    permitted. Unknown encodings fail closed; there is no torch.load fallback.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [info for info in archive.infolist() if info.filename == "data.pkl" or info.filename.endswith("/data.pkl")]
            if len(candidates) != 1:
                raise ValueError("Expected exactly one data.pkl")
            info = candidates[0]
            if info.file_size > 16 * 1024 * 1024:
                raise ValueError("Initial-state pickle exceeds the size limit")
            payload = archive.read(info)
        result = _ShapeUnpickler(io.BytesIO(payload), encoding="latin1").load()
    except (zipfile.BadZipFile, pickle.UnpicklingError, EOFError, TypeError) as exc:
        raise ValueError("Unsupported or corrupt initial-state container") from exc
    if not isinstance(result, _ArrayShape) or not hasattr(result, "shape"):
        raise ValueError("Initial states are not a supported NumPy array")
    return result.shape
