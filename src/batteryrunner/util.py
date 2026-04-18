"""
Shared utility helpers for Battery Runner.
"""

from __future__ import annotations

import json
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


SCHEDULE_CHOICES = [
    ("15 sec", 15),
    ("30 sec", 30),
    ("1 min", 60),
    ("5 min", 300),
    ("15 min", 900),
    ("1 hour", 3600),
]


def now_iso() -> str:
    """
    Return the current UTC timestamp in ISO-8601 form.
    """
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value):
    """
    Parse an ISO timestamp or return None when empty.
    """
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def format_timestamp(value: str | None) -> str:
    """
    Turn an ISO timestamp into a short display string.
    """
    dt = parse_iso(value)
    if dt is None:
        return "-"

    local_dt = dt.astimezone()
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


def atomic_write_json(path: Path, data, indent: int = 2) -> None:
    """
    Write JSON atomically with a trailing newline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        newline="\n",
    ) as handle:
        json.dump(data, handle, indent=indent, ensure_ascii=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    temp_path.replace(path)


def read_json(path: Path, default=None):
    """
    Read JSON or return a default when the file is missing.
    """
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def slugify_name(name: str) -> str:
    """
    Make a safe short folder-friendly name.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "bproc"


def get_schedule_label(seconds: int) -> str:
    """
    Return a friendly label for a schedule interval.
    """
    for label, choice_seconds in SCHEDULE_CHOICES:
        if choice_seconds == seconds:
            return label

    return f"{seconds} sec"


def merge_defaults(base: dict, override: dict) -> dict:
    """
    Deep-merge an override dict onto a default dict.
    """
    result = deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_defaults(result[key], value)
        else:
            result[key] = value

    return result
