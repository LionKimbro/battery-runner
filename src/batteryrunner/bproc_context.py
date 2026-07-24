"""
Shared per-run context helpers for bproc code.
"""

from __future__ import annotations

import json
from pathlib import Path

from batteryrunner import util


g = {
    "shared": {},
}


class JsonLoadError(RuntimeError):
    """
    Raised when a JSON file cannot be decoded cleanly.
    """


def reset(d: dict) -> None:
    """
    Replace the active bproc context payload.
    """
    shared = g.get("shared", {})
    g.clear()
    g["shared"] = shared
    g.update(d)


def clear(reset_shared: bool = False) -> None:
    """
    Clear the active per-run payload, preserving shared memory by default.
    """
    shared = {} if reset_shared else g.get("shared", {})
    g.clear()
    g["shared"] = shared


def get_now() -> int:
    """
    Return the current run timestamp in epoch seconds.
    """
    return g["now"]


def get_uuid() -> str:
    """
    Return the current bproc UUID.
    """
    return g["record"]["uuid"]


def get_name() -> str:
    """
    Return the current bproc display name.
    """
    return g["record"]["name"]


def get_state() -> dict:
    """
    Return the transitional compatibility state object.
    """
    return g["state"]


def get_settings() -> dict:
    """
    Return durable user-controlled settings.
    """
    return g["settings"]


def get_config() -> dict:
    """
    Return the durable user-controlled bproc config object.
    """
    return g["settings"]["config"]


def get_data() -> dict:
    """
    Return durable bproc-controlled data for this bproc.

    Mutating the returned dictionary does not save by itself; call save_data().
    """
    return g["data"]


def save_data() -> None:
    """
    Persist the current bproc-controlled data dictionary.
    """
    g["save_data_fn"](g["data"])


def get_runtime() -> dict:
    """
    Return the runner-controlled runtime dictionary.
    """
    return g["runtime"]


def get_schedule() -> dict:
    """
    Return the schedule section of state.
    """
    return g["settings"]["schedule"]


def get_root_path() -> Path:
    """
    Return the Battery Runner runtime root.
    """
    return g["root_path"]


def get_bproc_path() -> Path:
    """
    Return the installed folder for the current bproc.
    """
    return g["bproc_path"]


def get_process_memory() -> dict:
    """
    Return temporary process memory visible until this runner process exits.
    """
    return g["shared"]


def get_shared() -> dict:
    """
    Compatibility alias for get_process_memory().
    """
    return get_process_memory()


def log(message) -> None:
    """
    Write one log message for the current bproc.
    """
    g["log_fn"](message)


def resolve_path(path) -> Path:
    """
    Resolve a path relative to the current bproc folder.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    return get_bproc_path() / p


def load_json(path):
    """
    Load JSON with a standardized malformed-file error.
    """
    resolved = resolve_path(path)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise JsonLoadError(
            f"JSON decode error in {resolved} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def save_json(path, obj) -> None:
    """
    Save JSON relative to the current bproc folder.
    """
    resolved = resolve_path(path)
    util.atomic_write_json(resolved, obj)
