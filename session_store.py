from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path


class SessionStoreError(RuntimeError):
    pass


class SessionStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._assert_tmpfs()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._assert_tmpfs()
        os.chmod(self.directory, 0o700)

    def _assert_tmpfs(self) -> None:
        if platform.system() != "Linux":
            raise SessionStoreError("session storage requires Linux tmpfs")
        directory = self.directory
        existing = directory
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        mounts = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
        candidates = []
        for line in mounts:
            fields = line.split()
            if len(fields) >= 3 and fields[2] == "tmpfs":
                candidates.append(Path(fields[1]))
        if not any(existing == mount or mount in existing.parents for mount in candidates):
            raise SessionStoreError(f"session directory is not on tmpfs: {directory}")

    def put(self, token_id: str, record: dict[str, object]) -> None:
        path = self.directory / f"{token_id}.json"
        encoded = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
        except OSError as exc:
            raise SessionStoreError("unable to create session record") from exc

    def consume(self, token_id: str, now: float | None = None) -> dict[str, object] | None:
        path = self.directory / f"{token_id}.json"
        try:
            with path.open("r", encoding="utf-8") as handle:
                record = json.load(handle)
            path.unlink()
        except FileNotFoundError:
            return None
        if now is not None and float(record["expires_epoch"]) <= now:
            return None
        return record

    def purge_expired(self, now: float | None = None) -> int:
        current = time.time() if now is None else now
        removed = 0
        for path in self.directory.glob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    record = json.load(handle)
                if float(record["expires_epoch"]) <= current:
                    path.unlink(missing_ok=True)
                    removed += 1
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                path.unlink(missing_ok=True)
                removed += 1
        return removed
