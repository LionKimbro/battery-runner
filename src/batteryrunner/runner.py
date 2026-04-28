"""
Bproc execution and scheduler logic.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback

from batteryrunner import bproc_context, storage, util


g = {
    "module_cache": {},
}


def run_scheduler_pass() -> list[dict]:
    """
    Scan due bprocs and run what is ready.
    """
    storage.ensure_runtime_layout()
    storage.process_intake()

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

    next_run = util.parse_timestamp(runtime["next_run"])
    if next_run is None:
        return True

    return util.now_epoch() >= next_run


def run_bproc_now(short_id: str) -> dict:
    """
    Run one bproc immediately.
    """
    record = storage.load_bproc_record(short_id)
    state = record["state"]
    runtime = state["runtime"]
    now = util.now_epoch()

    runtime["running"] = True
    runtime["last_run"] = now
    storage.save_state(record["folder_path"], state)

    try:
        module = load_bproc_module(record)
        if not hasattr(module, "tick"):
            raise AttributeError("code.py must define tick()")

        bproc_context.reset({})
        bproc_context.reset(build_context_payload(record, now))
        module.tick()
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
        bproc_context.reset({})
        runtime["running"] = False
        runtime["next_run"] = _compute_next_run(
            state["schedule"]["seconds"],
            runtime["last_run"],
        )
        storage.save_state(record["folder_path"], state)

    record["state"] = state
    return record


def build_context_payload(record: dict, now: int) -> dict:
    """
    Build the runtime payload loaded into bproc_context.
    """
    state = record["state"]
    folder = record["folder_path"]

    return {
        "now": now,
        "log": lambda message: log_bproc_message(record, message),
        "state": state,
        "record": record,
        "root_path": storage.get_runtime_root(),
        "bproc_path": folder,
        "log_fn": lambda message: log_bproc_message(record, message),
    }


def log_bproc_message(record: dict, message) -> None:
    """
    Log a bproc message to stdout and the bproc log.jsonl file.
    """
    text = str(message)
    print(f"[{record['short_id']}] {text}")
    util.append_jsonl(
        storage.get_bproc_log_path(record["folder_path"]),
        {
            "timestamp": util.now_epoch(),
            "bproc_uuid": record["uuid"],
            "bproc_name": record["name"],
            "message": text,
        },
    )


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


def _compute_next_run(seconds: int, last_run=None) -> int:
    """
    Compute the next due time from the last run.
    """
    return util.compute_next_run(seconds, last_run)
