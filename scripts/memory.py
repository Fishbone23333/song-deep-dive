#!/usr/bin/env python3
"""Local preference storage for song-deep-dive; Python 3.10+, standard library."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unicodedata


SCHEMA_VERSION = 1
RETENTION_DAYS = 90
STATE_KEYS = {"schema_version", "onboarding_status", "favorite_artists", "recent_recommendations"}


class StoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def track_id(title: str, artist: str) -> str:
    if not normalized(title) or not normalized(artist):
        raise StoreError("invalid_input", "Track title and artist must be non-empty.")
    return json.dumps([normalized(artist), normalized(title)], ensure_ascii=False, separators=(",", ":"))


def parse_day(value: str) -> date:
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError
        return result
    except (TypeError, ValueError) as exc:
        raise StoreError("invalid_date", "Use a calendar date in YYYY-MM-DD format.") from exc


def data_directory(env=None, platform=None, home=None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    override = env.get("SONG_DEEP_DIVE_DATA_DIR")
    if override:
        result = Path(override).expanduser()
        if not result.is_absolute():
            raise StoreError("invalid_path", "SONG_DEEP_DIVE_DATA_DIR must be an absolute directory.")
        return result
    if platform == "win32":
        base = Path(env["LOCALAPPDATA"]) if env.get("LOCALAPPDATA") else home / "AppData" / "Local"
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else home / ".local" / "share"
    if not base.is_absolute():
        raise StoreError("invalid_path", "The operating-system data directory must be absolute.")
    return base / "song-deep-dive"


def empty_state() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "onboarding_status": "not_started",
        "favorite_artists": [],
        "recent_recommendations": [],
    }


def validate_state(state: object) -> dict:
    if not isinstance(state, dict):
        raise StoreError("invalid_state", "Memory must be a JSON object; the original file was not changed.")
    if type(state.get("schema_version")) is not int or state["schema_version"] != SCHEMA_VERSION:
        raise StoreError("unsupported_schema", "Unknown memory schema; the original file was not changed.")
    if set(state) != STATE_KEYS:
        raise StoreError("invalid_state", "Memory fields do not match schema 1; the original file was not changed.")
    if state["onboarding_status"] not in ("not_started", "completed", "skipped"):
        raise StoreError("invalid_state", "Invalid onboarding status.")
    artists = state["favorite_artists"]
    if not isinstance(artists, list) or any(not isinstance(item, str) or not normalized(item) for item in artists):
        raise StoreError("invalid_state", "Favorite artists must be non-empty strings.")
    records = state["recent_recommendations"]
    if not isinstance(records, list):
        raise StoreError("invalid_state", "Recommendations must be an array.")
    for record in records:
        if not isinstance(record, dict) or set(record) != {"track_id", "recommended_on"}:
            raise StoreError("invalid_state", "Invalid recommendation record.")
        if not isinstance(record["track_id"], str) or not record["track_id"].strip():
            raise StoreError("invalid_state", "Invalid track identifier.")
        parse_day(record["recommended_on"])
    return state


def artist_names(items) -> list[str]:
    result = []
    seen = set()
    for item in items:
        label = " ".join(item.split())
        key = normalized(label)
        if not key:
            raise StoreError("invalid_input", "Artist names must be non-empty.")
        if key not in seen:
            seen.add(key)
            result.append(label)
    return result


def recent_records(records: list, today: date) -> list[dict]:
    cutoff = today - timedelta(days=RETENTION_DAYS - 1)
    latest = {}
    for record in records:
        day = parse_day(record["recommended_on"])
        key = record["track_id"]
        if day >= cutoff and (key not in latest or day > parse_day(latest[key]["recommended_on"])):
            latest[key] = dict(record)
    return sorted(latest.values(), key=lambda item: (item["recommended_on"], item["track_id"]))


@contextmanager
def exclusive_lock(path: Path, timeout: float = 5.0):
    """OS locks release on process exit; the lock file deliberately stays in place."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + timeout
        locked = False
        try:
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except (BlockingIOError, PermissionError):
                    if time.monotonic() >= deadline:
                        raise StoreError("lock_timeout", "Another writer is using memory; retry later.")
                    time.sleep(0.025)
            yield
        finally:
            if locked:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class MemoryStore:
    def __init__(self, directory: Path, today: date, lock_timeout: float = 5.0):
        self.directory = Path(directory).resolve()
        skill_root = Path(__file__).resolve().parent.parent
        if self.directory == skill_root or skill_root in self.directory.parents:
            raise StoreError("invalid_path", "Keep personal memory outside the Skill installation directory.")
        self.path = self.directory / "preferences.json"
        self.today = today
        self.lock_timeout = lock_timeout

    def read(self) -> tuple[dict, bool]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except FileNotFoundError:
            return empty_state(), False
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise StoreError("corrupt_memory", "Memory is not valid UTF-8 JSON; the original file was not changed.") from exc
        validate_state(state)
        state["recent_recommendations"] = recent_records(state["recent_recommendations"], self.today)
        return state, True

    def write_atomic(self, state: dict):
        validate_state(state)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix=".preferences-", suffix=".tmp", dir=self.directory, delete=False) as handle:
                temp_path = Path(handle.name)
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def mutate(self, operation) -> dict:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with exclusive_lock(self.directory / "preferences.json.lock", self.lock_timeout):
            state, _ = self.read()
            operation(state)
            state["favorite_artists"] = artist_names(state["favorite_artists"])
            state["recent_recommendations"] = recent_records(state["recent_recommendations"], self.today)
            self.write_atomic(state)
            return state


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--today", help="User's local date, YYYY-MM-DD (default: execution host date).")
    result.add_argument("--lock-timeout", type=float, default=5.0)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("show", help="Read memory without creating it.")
    onboard = commands.add_parser("onboard")
    choice = onboard.add_mutually_exclusive_group(required=True)
    choice.add_argument("--skip", action="store_true")
    choice.add_argument("--artist", action="append")
    artists = commands.add_parser("artists")
    artists.add_argument("action", choices=("add", "remove", "set"))
    artists.add_argument("--artist", action="append", required=True)
    for name in ("filter", "record"):
        command = commands.add_parser(name)
        command.add_argument("--track", nargs=2, action="append", required=True, metavar=("TITLE", "ARTIST"))
        if name == "record":
            command.add_argument("--if-new", action="store_true", help="Atomically skip tracks already in the recent list.")
    clear = commands.add_parser("clear")
    clear.add_argument("--scope", choices=("artists", "recommendations", "all"), required=True)
    return result


def execute(args) -> dict:
    today = parse_day(args.today) if args.today else date.today()
    if not 0 <= args.lock_timeout <= 60:
        raise StoreError("invalid_input", "Lock timeout must be between 0 and 60 seconds.")
    store = MemoryStore(data_directory(), today, args.lock_timeout)
    if args.command in ("show", "filter"):
        state, exists = store.read()
        output = {"ok": True, "path": str(store.path), "exists": exists, "saved": False, "today": today.isoformat(), "state": state}
        if args.command == "filter":
            known = {item["track_id"] for item in state["recent_recommendations"]}
            available, excluded, seen = [], [], set()
            for title, artist in args.track:
                key = track_id(title, artist)
                item = {"title": title, "artist": artist, "track_id": key}
                if key in seen or key in known:
                    excluded.append(item)
                else:
                    available.append(item)
                seen.add(key)
            output.update(available=available, excluded=excluded)
        return output

    recorded, already_recent = [], []

    def operation(state):
        if args.command == "onboard":
            state["onboarding_status"] = "skipped" if args.skip else "completed"
            if args.artist:
                state["favorite_artists"] = artist_names(state["favorite_artists"] + args.artist)
        elif args.command == "artists":
            names = artist_names(args.artist)
            if args.action == "set":
                state["favorite_artists"] = names
            elif args.action == "add":
                state["favorite_artists"] = artist_names(state["favorite_artists"] + names)
            else:
                removed = {normalized(name) for name in names}
                state["favorite_artists"] = [name for name in state["favorite_artists"] if normalized(name) not in removed]
            if args.action in ("add", "set"):
                state["onboarding_status"] = "completed"
        elif args.command == "record":
            records = {item["track_id"]: item for item in state["recent_recommendations"]}
            for title, artist in args.track:
                key = track_id(title, artist)
                old = records.get(key)
                if args.if_new and old is not None:
                    already_recent.append(key)
                    continue
                day = max(today, parse_day(old["recommended_on"])) if old else today
                records[key] = {"track_id": key, "recommended_on": day.isoformat()}
                if key not in recorded:
                    recorded.append(key)
            state["recent_recommendations"] = list(records.values())
        elif args.command == "clear":
            if args.scope == "all":
                state.clear()
                state.update(empty_state())
            elif args.scope == "artists":
                state["favorite_artists"] = []
            else:
                state["recent_recommendations"] = []

    state = store.mutate(operation)
    output = {"ok": True, "saved": True, "path": str(store.path), "today": today.isoformat(), "state": state}
    if args.command == "record":
        output.update(recorded=recorded, already_recent=already_recent)
    return output


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        output = execute(args)
    except StoreError as exc:
        output = {"ok": False, "saved": False, "error": {"code": exc.code, "message": str(exc)}}
    except PermissionError:
        output = {"ok": False, "saved": False, "error": {"code": "permission_denied", "message": "Memory access was denied; existing data was not replaced."}}
    except OSError as exc:
        output = {"ok": False, "saved": False, "error": {"code": "io_error", "message": str(exc)}}
    print(json.dumps(output, ensure_ascii=False))
    return 0 if output["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
