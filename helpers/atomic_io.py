from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Callable, Iterator, Mapping

import pandas as pd

from config.deployment import PUBLIC_RUNTIME_ROOT

try:  # Unix deployment lock; the in-process lock remains the portable fallback.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_LOCK_ROOT = PUBLIC_RUNTIME_ROOT / "locks"


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


def atomic_write_bundle(
    payloads: Mapping[str | Path, bytes],
    *,
    transaction_key: str | Path,
) -> None:
    """Commit several file replacements as one application transaction.

    All payloads are staged and fsynced before the transaction lock is taken.
    Existing targets are snapshotted in memory so an exception during commit can
    roll every already-replaced target back before the lock is released. Readers
    that use the same ``transaction_key`` therefore never observe an in-process
    partial commit.

    This is intentionally an application-level transaction rather than a claim
    that POSIX/Windows can atomically replace several independent directory
    entries in one filesystem operation. A host crash between ``os.replace``
    calls is outside that guarantee.
    """
    normalized = [(Path(path), bytes(data)) for path, data in payloads.items()]
    if not normalized:
        return

    staged: dict[Path, Path] = {}
    try:
        for target, data in normalized:
            temporary = _temporary_path(target)
            temporary.write_bytes(data)
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            staged[target] = temporary

        with synchronized_path(transaction_key):
            previous: dict[Path, bytes | None] = {
                target: target.read_bytes() if target.exists() else None
                for target, _ in normalized
            }
            committed: list[Path] = []
            try:
                for target, _ in normalized:
                    _commit(staged[target], target)
                    committed.append(target)
            except BaseException:
                rollback_errors: list[str] = []
                for target in reversed(committed):
                    try:
                        prior = previous[target]
                        if prior is None:
                            target.unlink(missing_ok=True)
                        else:
                            rollback_temp = _temporary_path(target)
                            try:
                                rollback_temp.write_bytes(prior)
                                _commit(rollback_temp, target)
                            finally:
                                rollback_temp.unlink(missing_ok=True)
                    except BaseException as rollback_exc:  # pragma: no cover - catastrophic filesystem failure
                        rollback_errors.append(f"{target}: {type(rollback_exc).__name__}: {rollback_exc}")
                if rollback_errors:
                    raise RuntimeError(
                        "Atomic bundle commit failed and rollback was incomplete: "
                        + "; ".join(rollback_errors)
                    )
                raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
