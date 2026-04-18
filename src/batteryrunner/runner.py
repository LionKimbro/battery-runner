"""
Bproc execution and scheduler logic.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from datetime import timedelta

from batteryrunner import storage, util


g = {
    "module_cache": {},
}


def run_scheduler_pass() -> list[dict]:
    """
    Scan due bprocs and run what is ready.
    """
    storage.ensure_runtime_layout()
    storage.process_drop()

    ran = []
    for record in storage.list_bproc_entries():
        if should_run_record(record):
            ran.append(run_bproc_now(record["short_id"]))

    return ran


def should_run_record(record: dict) -> bool:
    """
    Decide whether a bproc should execute now.
    """
    state = record["state"]
    runtime = state["runtime"]

    if not state["enabled"]:
        return False

    if runtime["running"]:
        return False

    next_run = util.parse_iso(runtime["next_run"])
    if next_run is None:
        return True

    return util.parse_iso(util.now_iso()) >= next_run


def run_bproc_now(short_id: str) -> dict:
    """
    Run one bproc immediately.
    """
    record = storage.load_bproc_record(short_id)
    state = record["state"]
    runtime = state["runtime"]
    now = util.now_iso()

    runtime["running"] = True
    runtime["last_run"] = now
    storage.save_state(record["folder_path"], state)

    try:
        module = load_bproc_module(record)
        if not hasattr(module, "tick"):
            raise AttributeError("code.py must define tick(context)")

        context = build_context(record)
        module.tick(context)
        runtime["last_success"] = now
        runtime["last_error"] = {
            "timestamp": None,
            "message": None,
            "traceback": None,
        }
    except Exception as exc:
        runtime["last_error"] = {
            "timestamp": now,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        runtime["error_count"] += 1
        if not state["lock_on_error"]:
            state["enabled"] = False
    finally:
        runtime["running"] = False
        runtime["next_run"] = _compute_next_run(state["schedule"]["seconds"])
        storage.save_state(record["folder_path"], state)

    record["state"] = state
    return record


def build_context(record: dict) -> dict:
    """
    Build the runtime context passed to tick(context).
    """
    state = record["state"]
    config = state["config"]
    folder = record["folder_path"]

    return {
        "now": util.now_iso(),
        "log": lambda message: log_bproc_message(record, message),
        "state": state,
        "config": config,
        "root_path": storage.get_runtime_root(),
        "bproc_path": folder,
    }


def log_bproc_message(record: dict, message) -> None:
    """
    Log a bproc message to stdout.
    """
    print(f"[{record['short_id']}] {message}")


def load_bproc_module(record: dict):
    """
    Load or reload a bproc module from code.py.
    """
    code_path = record["folder_path"] / "code.py"
    cache_key = record["short_id"]
    stamp = code_path.stat().st_mtime_ns
    cached = g["module_cache"].get(cache_key)

    if cached is not None and cached["stamp"] == stamp:
        return cached["module"]

    module_name = f"batteryrunner_bproc_{record['short_id']}"
    spec = importlib.util.spec_from_file_location(module_name, code_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {code_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    g["module_cache"][cache_key] = {
        "stamp": stamp,
        "module": module,
    }
    return module


def _compute_next_run(seconds: int) -> str:
    """
    Compute the next due time from the current moment.
    """
    return (util.parse_iso(util.now_iso()) + timedelta(seconds=seconds)).isoformat()
