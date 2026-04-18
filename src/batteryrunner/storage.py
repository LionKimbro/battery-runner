"""
Filesystem bootstrap, persistence, and drop-folder installation.
"""

from __future__ import annotations

import ast
import shutil
import uuid
from pathlib import Path

import lionscliapp as app

from batteryrunner import util


INVENTORY_FILENAME = "brprocs-inventory.json"


def ensure_runtime_layout() -> dict:
    """
    Ensure the Battery Runner filesystem layout exists.
    """
    root = get_runtime_root()
    root.mkdir(parents=True, exist_ok=True)

    for dirname in ["brprocs", "drop", "inbox", "outbox"]:
        (root / dirname).mkdir(exist_ok=True)

    if not get_inventory_path().exists():
        save_inventory({"version": "v1", "brprocs": {}})

    return load_inventory()


def get_runtime_root() -> Path:
    """
    Return the .batteryrunner runtime root.
    """
    return app.get_path(".", "p")


def get_inventory_path() -> Path:
    """
    Return the inventory file path.
    """
    return get_runtime_root() / INVENTORY_FILENAME


def get_brprocs_root() -> Path:
    """
    Return the root directory containing installed bprocs.
    """
    return get_runtime_root() / "brprocs"


def get_drop_root() -> Path:
    """
    Return the drop directory.
    """
    return get_runtime_root() / "drop"


def get_bproc_log_path(folder: Path) -> Path:
    """
    Return the per-bproc JSONL log path.
    """
    return folder / "log.jsonl"


def clear_bproc_log(folder: Path) -> None:
    """
    Clear a bproc's log.jsonl file.
    """
    log_path = get_bproc_log_path(folder)
    log_path.write_text("", encoding="utf-8", newline="\n")


def load_inventory() -> dict:
    """
    Load the bproc inventory.
    """
    return util.read_json(get_inventory_path(), {"version": "v1", "brprocs": {}})


def save_inventory(inventory: dict) -> None:
    """
    Save the bproc inventory.
    """
    util.atomic_write_json(get_inventory_path(), inventory)


def list_bproc_entries() -> list[dict]:
    """
    Return installed bprocs sorted by name.
    """
    inventory = load_inventory()
    entries = []

    for short_id, item in inventory["brprocs"].items():
        folder = get_brprocs_root() / item["folder"]
        state = load_state(folder)
        entry = dict(item)
        entry["short_id"] = short_id
        entry["folder_path"] = folder
        entry["state"] = state
        entries.append(entry)

    entries.sort(key=lambda item: (item["name"].lower(), item["short_id"]))
    return entries


def load_bproc_record(short_id: str) -> dict:
    """
    Load a single bproc record by short id.
    """
    inventory = load_inventory()
    item = inventory["brprocs"].get(short_id)
    if item is None:
        raise KeyError(f"Unknown bproc short id: {short_id}")

    folder = get_brprocs_root() / item["folder"]
    return {
        "short_id": short_id,
        **item,
        "folder_path": folder,
        "state": load_state(folder),
    }


def load_state(folder: Path) -> dict:
    """
    Load a bproc state file.
    """
    state = util.read_json(folder / "state.json", _default_state("missing"))
    _normalize_runtime_timestamps(state)
    return state


def save_state(folder: Path, state: dict) -> None:
    """
    Save a bproc state file.
    """
    util.atomic_write_json(folder / "state.json", state)


def load_config(folder: Path) -> dict:
    """
    Load bproc.json.
    """
    return util.read_json(folder / "bproc.json", {})


def save_config(folder: Path, data: dict) -> None:
    """
    Save bproc.json.
    """
    util.atomic_write_json(folder / "bproc.json", data)


def process_drop() -> list[dict]:
    """
    Install every item currently sitting in the drop directory.
    """
    ensure_runtime_layout()
    installed = []

    for item in sorted(get_drop_root().iterdir(), key=lambda path: path.name.lower()):
        installed.append(_install_drop_item(item))

    return installed


def create_bproc(name: str, seconds: int = 3600, lock_on_error: bool = True) -> dict:
    """
    Create a new starter bproc directly in brprocs/.
    """
    ensure_runtime_layout()

    inventory = load_inventory()
    proc_id = str(uuid.uuid4())
    short_id = proc_id[:12]
    base_name = util.slugify_name(name)
    folder_name = f"{base_name}__{short_id}"
    folder = get_brprocs_root() / folder_name
    folder.mkdir(parents=True, exist_ok=False)

    display_name = name.strip() or base_name
    code_path = folder / "code.py"
    code_path.write_text(_starter_code(display_name, seconds), encoding="utf-8", newline="\n")

    config = _build_bproc_config(proc_id, short_id, display_name, folder_name, folder)
    state = _default_state(proc_id)
    state["schedule"]["seconds"] = seconds
    state["schedule"]["label"] = util.get_schedule_label(seconds)
    state["lock_on_error"] = lock_on_error
    state["runtime"]["next_run"] = util.compute_next_run(seconds)

    save_config(folder, config)
    save_state(folder, state)

    inventory["brprocs"][short_id] = {
        "id": proc_id,
        "name": config["name"],
        "short_id": short_id,
        "folder": folder_name,
        "entry": "code.py",
        "installed_at": config["installed_at"],
        "source": {"type": "manual"},
    }
    save_inventory(inventory)

    return {
        "short_id": short_id,
        "id": proc_id,
        "name": config["name"],
        "folder": folder_name,
        "folder_path": folder,
        "state": state,
    }


def set_enabled(short_id: str, enabled: bool) -> dict:
    """
    Update enabled status and persist.
    """
    record = load_bproc_record(short_id)
    state = record["state"]
    state["enabled"] = enabled
    save_state(record["folder_path"], state)
    record["state"] = state
    return record


def set_lock_on_error(short_id: str, lock_on_error: bool) -> dict:
    """
    Update error-lock behavior and persist.
    """
    record = load_bproc_record(short_id)
    state = record["state"]
    state["lock_on_error"] = lock_on_error
    save_state(record["folder_path"], state)
    record["state"] = state
    return record


def set_schedule_seconds(short_id: str, seconds: int) -> dict:
    """
    Update a bproc's interval schedule.
    """
    record = load_bproc_record(short_id)
    state = record["state"]
    state["schedule"]["seconds"] = seconds
    state["schedule"]["label"] = util.get_schedule_label(seconds)
    state["runtime"]["next_run"] = util.compute_next_run(seconds, state["runtime"]["last_run"])
    save_state(record["folder_path"], state)
    record["state"] = state
    return record


def save_bproc_config_object(short_id: str, data: dict) -> dict:
    """
    Replace the user config object inside state.json.
    """
    record = load_bproc_record(short_id)
    state = record["state"]
    state["config"] = data
    save_state(record["folder_path"], state)
    record["state"] = state
    return record


def save_bproc_code_text(short_id: str, text: str) -> dict:
    """
    Replace code.py content.
    """
    record = load_bproc_record(short_id)
    code_path = record["folder_path"] / "code.py"
    code_path.write_text(text, encoding="utf-8", newline="\n")
    return record


def _install_drop_item(item: Path) -> dict:
    """
    Install one dropped file or directory as a bproc.
    """
    inventory = load_inventory()
    proc_id = str(uuid.uuid4())
    short_id = proc_id[:12]
    base_name = util.slugify_name(item.stem if item.is_file() else item.name)
    folder_name = f"{base_name}__{short_id}"
    folder = get_brprocs_root() / folder_name
    folder.mkdir(parents=True, exist_ok=False)

    if item.is_dir():
        _copy_drop_directory(item, folder)
    else:
        _copy_drop_file(item, folder)

    _ensure_code_file(folder, base_name)
    discovered = _read_bproc_module_metadata(folder / "code.py")
    display_name = discovered.get("name") or base_name
    config = _build_bproc_config(proc_id, short_id, display_name, folder_name, folder)
    state = _build_state_from_folder(proc_id, folder, discovered)

    save_config(folder, config)
    save_state(folder, state)

    inventory["brprocs"][short_id] = {
        "id": proc_id,
        "name": config["name"],
        "short_id": short_id,
        "folder": folder_name,
        "entry": "code.py",
        "installed_at": config["installed_at"],
        "source": {"type": "drop"},
    }
    save_inventory(inventory)

    _delete_drop_item(item)

    return {
        "short_id": short_id,
        "id": proc_id,
        "name": config["name"],
        "folder": folder_name,
        "folder_path": folder,
        "state": state,
    }


def _copy_drop_directory(src: Path, dest: Path) -> None:
    """
    Copy a dropped directory into the destination bproc folder.
    """
    for child in src.iterdir():
        target = dest / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _copy_drop_file(src: Path, dest: Path) -> None:
    """
    Copy a dropped file into the destination bproc folder.
    """
    target_name = "code.py" if src.suffix.lower() == ".py" else src.name
    shutil.copy2(src, dest / target_name)


def _ensure_code_file(folder: Path, base_name: str) -> None:
    """
    Ensure the bproc folder contains code.py.
    """
    code_path = folder / "code.py"
    if code_path.exists():
        return

    top_level_py = sorted(folder.glob("*.py"))
    if len(top_level_py) == 1:
        shutil.copy2(top_level_py[0], code_path)
        return

    code_path.write_text(_default_code(base_name), encoding="utf-8", newline="\n")


def _build_bproc_config(
    proc_id: str,
    short_id: str,
    display_name: str,
    folder_name: str,
    folder: Path,
) -> dict:
    """
    Build the base bproc.json payload, preserving any supplied metadata.
    """
    payload = {
        "id": proc_id,
        "short_id": short_id,
        "name": display_name,
        "folder": folder_name,
        "entry": "code.py",
        "installed_at": util.now_epoch(),
    }

    existing = util.read_json(folder / "bproc.json", {})
    if isinstance(existing, dict):
        payload = util.merge_defaults(payload, existing)
        payload["id"] = proc_id
        payload["short_id"] = short_id
        payload["name"] = payload.get("name") or display_name
        payload["folder"] = folder_name
        payload["entry"] = payload.get("entry") or "code.py"
        payload["installed_at"] = util.parse_timestamp(payload.get("installed_at")) or util.now_epoch()

    return payload


def _build_state_from_folder(proc_id: str, folder: Path, discovered: dict) -> dict:
    """
    Create default state and pick up obvious module metadata.
    """
    state = _default_state(proc_id)
    state_path = folder / "state.json"
    existing = util.read_json(state_path, {})
    if isinstance(existing, dict):
        state = util.merge_defaults(state, existing)

    interval_seconds = discovered.get("interval_seconds")
    if interval_seconds is not None and not state_path.exists():
        state["schedule"]["seconds"] = interval_seconds
        state["schedule"]["label"] = util.get_schedule_label(interval_seconds)
    elif not state["schedule"].get("label"):
        state["schedule"]["label"] = util.get_schedule_label(state["schedule"]["seconds"])

    return state


def _read_bproc_module_metadata(code_path: Path) -> dict:
    """
    Read a couple of optional top-level metadata assignments from code.py.
    """
    try:
        source = code_path.read_text(encoding="utf-8")
        module = ast.parse(source)
    except (OSError, SyntaxError):
        return {}

    found = {}
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue

        name = node.targets[0].id
        if name not in {"name", "interval_seconds"}:
            continue

        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue

        if name == "name" and isinstance(value, str):
            found[name] = value
        if name == "interval_seconds" and isinstance(value, int):
            found[name] = value

    return found


def _default_state(proc_id: str) -> dict:
    """
    Return a default runtime state object.
    """
    return {
        "id": proc_id,
        "enabled": True,
        "schedule": {
            "mode": "interval",
            "seconds": 3600,
            "label": "1 hour",
        },
        "lock_on_error": True,
        "runtime": {
            "running": False,
            "last_run": None,
            "next_run": util.now_epoch(),
            "last_success": None,
            "last_error": {
                "timestamp": None,
                "message": None,
                "traceback": None,
            },
            "error_count": 0,
        },
        "config": {},
    }


def _normalize_runtime_timestamps(state: dict) -> None:
    """
    Normalize runtime timestamps to integer epoch seconds in memory.
    """
    runtime = state.get("runtime")
    if not isinstance(runtime, dict):
        return

    for key in ["last_run", "next_run", "last_success"]:
        runtime[key] = util.parse_timestamp(runtime.get(key))

    last_error = runtime.get("last_error")
    if isinstance(last_error, dict):
        last_error["timestamp"] = util.parse_timestamp(last_error.get("timestamp"))


def _default_code(base_name: str) -> str:
    """
    Create a minimal starter bproc.
    """
    return f'''"""
Battery Runner starter bproc for {base_name}.
"""


def tick(context):
    context["log"]("tick")
'''


def _starter_code(display_name: str, seconds: int) -> str:
    """
    Create a starter code.py for a new manual bproc.
    """
    return f'''"""
Battery Runner bproc: {display_name}
"""

name = {display_name!r}
interval_seconds = {seconds}


def tick(context):
    pass
'''


def _delete_drop_item(item: Path) -> None:
    """
    Remove an item from the drop directory after successful install.
    """
    if item.is_dir():
        shutil.rmtree(item)
    else:
        item.unlink()
