"""Process-level concurrency lock for self-update operations."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from types import TracebackType

from watch_skill.errors import UpdateError

LOCK_STALE_SECONDS = 300.0  # 5 minutes max before considering a lock dead


def _get_lock_path() -> Path:
    try:
        from watch_skill.config import get_settings

        return get_settings().data_dir / "update.lock"
    except Exception:
        return Path.home() / ".watch-skill" / "update.lock"


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        # STILL_ACTIVE = 259
        return bool(exit_code.value == 259)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False



class UpdateLock:
    """Exclusive lock protecting self-update transactions."""

    def __init__(self, lock_path: Path | None = None, target_version: str = "unknown") -> None:
        self.lock_path = lock_path or _get_lock_path()
        self.target_version = target_version
        self.transaction_id = uuid.uuid4().hex[:12]
        self._acquired = False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Check existing lock
        if self.lock_path.is_file():
            try:
                data = json.loads(self.lock_path.read_text(encoding="utf-8"))
                owner_pid = int(data.get("owner_pid", 0))
                started_at = float(data.get("started_at", 0))
                is_stale = (time.time() - started_at) > LOCK_STALE_SECONDS
                is_dead = not _is_pid_alive(owner_pid)

                if is_stale or is_dead:
                    self.lock_path.unlink(missing_ok=True)
                else:
                    raise UpdateError(
                        f"Another update operation is currently running (PID {owner_pid}, tx {data.get('transaction_id')}).",
                        code="update.in_progress",
                        fix="Wait for the active update to complete, or delete ~/.watch-skill/update.lock if abandoned.",
                        details=data,
                    )
            except (json.JSONDecodeError, ValueError):
                # Malformed lock file — remove if stale by mtime
                try:
                    if (time.time() - self.lock_path.stat().st_mtime) > 60.0:
                        self.lock_path.unlink(missing_ok=True)
                except OSError:
                    pass

        # Atomic file creation
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = {
                "owner_pid": os.getpid(),
                "transaction_id": self.transaction_id,
                "started_at": time.time(),
                "target_version": self.target_version,
            }
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self._acquired = True
        except OSError as exc:
            raise UpdateError(
                "Failed to acquire update lock; another update may have started concurrently.",
                code="update.in_progress",
                fix="Wait for the active update to complete, or remove ~/.watch-skill/update.lock if stale.",
            ) from exc

    def release(self) -> None:
        if self._acquired:
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._acquired = False

    def __enter__(self) -> UpdateLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()
