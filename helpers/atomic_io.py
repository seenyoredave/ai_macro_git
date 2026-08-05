from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Callable, Iterator

import pandas as pd

try:  # Unix deployment lock; the in-process lock remains the portable fallback.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_LOCK_ROOT = Path(tempfile.gettempdir()) / "ai_macro_file_locks"


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path.expanduser().resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _lock_file(path: Path) -> Path:
    digest = hashlib.sha256(str(path.expanduser().resolve()).encode("utf-8")).hexdigest()
    return _LOCK_ROOT / f"{digest}.lock"


@contextmanager
def synchronized_path(path: str | Path) -> Iterator[None]:
    """Serialize a complete file transaction across Streamlit sessions."""
    target = Path(path)
    lock = _thread_lock(target)
    with lock:
        _LOCK_ROOT.mkdir(parents=True, exist_ok=True)
        handle = _lock_file(target).open("a+")
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def _temporary_path(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    )
    path = Path(handle.name)
    handle.close()
    return path


def _commit(temp_path: Path, target: Path) -> None:
    with temp_path.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temp_path, target)


def atomic_write_bytes(data: bytes, path: str | Path, *, lock: bool = True) -> None:
    target = Path(path)

    def write() -> None:
        temporary = _temporary_path(target)
        try:
            temporary.write_bytes(data)
            _commit(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    if lock:
        with synchronized_path(target):
            write()
    else:
        write()


def atomic_write_json(payload: dict, path: str | Path, *, lock: bool = True) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(data, path, lock=lock)


def atomic_write_csv(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    lock: bool = True,
    validator: Callable[[Path], None] | None = None,
    **to_csv_kwargs,
) -> None:
    target = Path(path)

    def write() -> None:
        temporary = _temporary_path(target)
        try:
            frame.to_csv(temporary, index=False, **to_csv_kwargs)
            if validator is not None:
                validator(temporary)
            _commit(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    if lock:
        with synchronized_path(target):
            write()
    else:
        write()
