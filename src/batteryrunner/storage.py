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


def get_inbox_root() -> Path:
    """
    Return the inbox directory.
    """
    return get_runtime_root() / "inbox"


def get_project_log_path() -> Path:
    """
    Return the project-wide JSONL log path.
    """
    return get_runtime_root() / "project-log.jsonl"


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
    inventory = util.read_json(get_inventory_path(), {"version": "v1", "brprocs": {}})
    for item in inventory["brprocs"].values():
        _normalize_legacy_uuid_fields(item)
    return inventory


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
    inventory_changed = False

    for short_id, item in inventory["brprocs"].items():
        folder = get_brprocs_root() / item["folder"]
        state = load_state(folder)
        config = load_config(folder)
        entry = dict(item)
        entry["short_id"] = short_id
        entry["folder_path"] = folder
        entry["state"] = state
        changed = _sync_bproc_metadata(entry, config, state, inventory)
        if changed:
            inventory_changed = True
            state = load_state(folder)
            config = load_config(folder)
            entry = dict(inventory["brprocs"][short_id])
            entry["short_id"] = short_id
            entry["folder_path"] = folder
            entry["state"] = state
        entries.append(entry)

    if inventory_changed:
        save_inventory(inventory)

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
    state = load_state(folder)
    config = load_config(folder)
    record = {
        "short_id": short_id,
        **item,
        "folder_path": folder,
        "state": state,
    }
    if _sync_bproc_metadata(record, config, state, inventory):
        save_inventory(inventory)
        item = inventory["brprocs"][short_id]
        record = {
            "short_id": short_id,
            **item,
            "folder_path": folder,
            "state": load_state(folder),
        }

    return record


def load_state(folder: Path) -> dict:
    """
    Load a bproc state file.
    """
    state = util.read_json(folder / "state.json", _default_state("missing"))
    _normalize_legacy_uuid_fields(state)
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
    config = util.read_json(folder / "bproc.json", {})
    _normalize_legacy_uuid_fields(config)
    return config


def save_config(folder: Path, data: dict) -> None:
    """
    Save bproc.json.
    """
    util.atomic_write_json(folder / "bproc.json", data)


def process_drop() -> list[dict]:
    """
    Install every item currently sitting in the drop directory.
    """
    return _process_intake_root(get_drop_root(), "drop")


def process_inbox() -> list[dict]:
    """
    Install every item currently sitting in the inbox directory.
    """
    return _process_intake_root(get_inbox_root(), "inbox")


def process_intake() -> list[dict]:
    """
    Process all active intake directories.
    """
    installed = []
    installed.extend(process_drop())
    installed.extend(process_inbox())
    return installed


def create_bproc(name: str, seconds: int = 3600, lock_on_error: bool = True) -> dict:
    """
    Create a new starter bproc directly in brprocs/.
    """
    ensure_runtime_layout()

    inventory = load_inventory()
    proc_id = _generate_unique_proc_id(inventory)
    return _create_bproc_with_id(inventory, proc_id, name, seconds, lock_on_error)


def create_bproc_with_id(
    name: str,
    proc_id: str,
    seconds: int = 3600,
    lock_on_error: bool = True,
) -> dict:
    """
    Create a new starter bproc with an explicit GUID.
    """
    ensure_runtime_layout()

    inventory = load_inventory()
    proc_id = _normalize_requested_proc_id(proc_id)
    _ensure_proc_id_available(inventory, proc_id)
    return _create_bproc_with_id(inventory, proc_id, name, seconds, lock_on_error)


def _create_bproc_with_id(
    inventory: dict,
    proc_id: str,
    name: str,
    seconds: int,
    lock_on_error: bool,
) -> dict:
    """
    Create a new starter bproc using a chosen GUID.
    """
    short_id = _derive_short_id(inventory, proc_id)
    base_name = util.slugify_name(name)
    folder_name = f"{base_name}__{short_id}"
    folder = get_brprocs_root() / folder_name
    folder.mkdir(parents=True, exist_ok=False)

    display_name = name.strip() or base_name
    code_path = folder / "code.py"
    code_path.write_text(_starter_code(proc_id, display_name, seconds), encoding="utf-8", newline="\n")

    config = _build_bproc_config(proc_id, short_id, display_name, folder_name, folder)
    state = _default_state(proc_id)
    state["schedule"]["seconds"] = seconds
    state["schedule"]["label"] = util.get_schedule_label(seconds)
    state["lock_on_error"] = lock_on_error
    state["runtime"]["next_run"] = util.compute_next_run(seconds)

    save_config(folder, config)
    save_state(folder, state)

    inventory["brprocs"][short_id] = {
        "uuid": proc_id,
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
        "uuid": proc_id,
        "name": config["name"],
        "folder": folder_name,
        "folder_path": folder,
        "state": state,
    }


def delete_bproc(short_id: str, delete_folder: bool = False) -> None:
    """
    Remove a bproc from inventory, optionally deleting its folder too.
    """
    inventory = load_inventory()
    item = inventory["brprocs"].get(short_id)
    if item is None:
        raise KeyError(f"Unknown bproc short id: {short_id}")

    folder = get_brprocs_root() / item["folder"]
    del inventory["brprocs"][short_id]
    save_inventory(inventory)

    if delete_folder and folder.exists():
        shutil.rmtree(folder)


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
    _refresh_bproc_metadata(short_id)
    return load_bproc_record(short_id)


def _process_intake_root(root: Path, source_type: str) -> list[dict]:
    """
    Process one intake directory and return newly installed bprocs.
    """
    ensure_runtime_layout()
    installed = []

    for item in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        result = _install_intake_item(item, source_type)
        if result is not None:
            installed.append(result)

    return installed


def _install_intake_item(item: Path, source_type: str) -> dict | None:
    """
    Install one intake item, dropping duplicates with a project-wide log note.
    """
    inventory = load_inventory()
    proc_id = _find_requested_proc_id(item, inventory)
    if proc_id is not None:
        existing_short_id = _find_existing_short_id_by_uuid(inventory, proc_id)
        if existing_short_id is not None:
            _log_duplicate_intake(item, source_type, proc_id, existing_short_id, inventory)
            _delete_drop_item(item)
            return None
    else:
        proc_id = _generate_unique_proc_id(inventory)

    return _install_drop_item(item, source_type, proc_id, inventory)


def _install_drop_item(
    item: Path,
    source_type: str = "drop",
    proc_id: str | None = None,
    inventory: dict | None = None,
) -> dict:
    """
    Install one intake file or directory as a bproc.
    """
    if inventory is None:
        inventory = load_inventory()
    if proc_id is None:
        proc_id = _find_requested_proc_id(item, inventory) or _generate_unique_proc_id(inventory)

    short_id = _derive_short_id(inventory, proc_id)
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
        "uuid": proc_id,
        "name": config["name"],
        "short_id": short_id,
        "folder": folder_name,
        "entry": "code.py",
        "installed_at": config["installed_at"],
        "source": {"type": source_type},
    }
    save_inventory(inventory)

    _delete_drop_item(item)

    return {
        "short_id": short_id,
        "uuid": proc_id,
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
        "uuid": proc_id,
        "short_id": short_id,
        "name": display_name,
        "folder": folder_name,
        "entry": "code.py",
        "installed_at": util.now_epoch(),
        "code_hash": util.sha256_file(folder / "code.py"),
    }

    existing = util.read_json(folder / "bproc.json", {})
    if isinstance(existing, dict):
        payload = util.merge_defaults(payload, existing)
        payload["uuid"] = proc_id
        payload["short_id"] = short_id
        payload["name"] = payload.get("name") or display_name
        payload["folder"] = folder_name
        payload["entry"] = payload.get("entry") or "code.py"
        payload["installed_at"] = util.parse_timestamp(payload.get("installed_at")) or util.now_epoch()
        payload["code_hash"] = payload.get("code_hash") or util.sha256_file(folder / "code.py")

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
        if name not in {"name", "interval_seconds", "uuid", "id"}:
            continue

        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue

        if name == "name" and isinstance(value, str):
            found[name] = value
        if name == "interval_seconds" and isinstance(value, int):
            found[name] = value
        if name in {"uuid", "id"} and isinstance(value, str):
            found["uuid"] = value

    return found


def _default_state(proc_id: str) -> dict:
    """
    Return a default runtime state object.
    """
    return {
        "uuid": proc_id,
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

from batteryrunner import bproc_context as ctx


def tick():
    ctx.log("tick")
'''


def _starter_code(proc_id: str, display_name: str, seconds: int) -> str:
    """
    Create a starter code.py for a new manual bproc.
    """
    return f'''"""
Battery Runner bproc: {display_name}
"""

from batteryrunner import bproc_context as ctx

uuid = {proc_id!r}
name = {display_name!r}
interval_seconds = {seconds}


def tick():
    pass
'''


def _refresh_bproc_metadata(short_id: str) -> None:
    """
    Refresh stored metadata for one bproc from its code file.
    """
    inventory = load_inventory()
    item = inventory["brprocs"].get(short_id)
    if item is None:
        raise KeyError(f"Unknown bproc short id: {short_id}")

    folder = get_brprocs_root() / item["folder"]
    record = {
        "short_id": short_id,
        **item,
        "folder_path": folder,
        "state": load_state(folder),
    }
    config = load_config(folder)
    state = record["state"]
    if _sync_bproc_metadata(record, config, state, inventory):
        save_inventory(inventory)


def _generate_unique_proc_id(inventory: dict) -> str:
    """
    Generate a UUID that does not collide with current inventory.
    """
    while True:
        proc_id = str(uuid.uuid4())
        if not _inventory_has_full_id(inventory, proc_id):
            return proc_id


def _find_requested_proc_id(item: Path, inventory: dict) -> str | None:
    """
    Read a requested UUID from a dropped bproc directory if present and usable.
    """
    data = None
    code_path = None
    if item.is_dir():
        data = util.read_json(item / "bproc.json", None)
        code_path = item / "code.py"
    elif item.is_file() and item.suffix.lower() == ".py":
        code_path = item
    else:
        return None

    requested = None
    if isinstance(data, dict):
        requested = data.get("uuid")
        if requested in [None, ""]:
            # Compatibility shim: accept legacy "id" on import for now and recast to "uuid".
            # Future cleanup: remove legacy "id" support once authored surfaces have migrated.
            requested = data.get("id")
    if requested in [None, ""] and code_path is not None:
        requested = _read_bproc_module_metadata(code_path).get("uuid")
    if requested in [None, ""]:
        return None

    return _normalize_requested_proc_id(requested)


def _normalize_requested_proc_id(value) -> str:
    """
    Validate and normalize a requested UUID string.
    """
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid bproc UUID: {value!r}") from exc


def _ensure_proc_id_available(inventory: dict, proc_id: str) -> None:
    """
    Raise if the requested UUID is already in use.
    """
    if _inventory_has_full_id(inventory, proc_id):
        raise ValueError(f"Bproc UUID already exists: {proc_id}")


def _inventory_has_full_id(inventory: dict, proc_id: str) -> bool:
    """
    Return True when the full UUID already exists in inventory.
    """
    for item in inventory["brprocs"].values():
        if item["uuid"] == proc_id:
            return True
    return False


def _find_existing_short_id_by_uuid(inventory: dict, proc_id: str) -> str | None:
    """
    Return the short_id for an already-known UUID, if present.
    """
    for short_id, item in inventory["brprocs"].items():
        if item["uuid"] == proc_id:
            return short_id
    return None


def _derive_short_id(inventory: dict, proc_id: str) -> str:
    """
    Derive a collision-resistant short_id from the full UUID.
    """
    digest = uuid.uuid5(uuid.NAMESPACE_URL, proc_id).hex

    for length in range(12, len(digest) + 1):
        short_id = digest[:length]
        existing = inventory["brprocs"].get(short_id)
        if existing is None or existing["uuid"] == proc_id:
            return short_id

    raise ValueError(f"Could not derive unique short_id for UUID: {proc_id}")


def _sync_bproc_metadata(record: dict, config: dict, state: dict, inventory: dict) -> bool:
    """
    Refresh name and interval metadata when code.py changed.
    """
    folder = record["folder_path"]
    code_path = folder / "code.py"
    if not code_path.exists():
        return False

    current_hash = util.sha256_file(code_path)
    stored_hash = config.get("code_hash")
    if stored_hash == current_hash:
        return False

    discovered = _read_bproc_module_metadata(code_path)
    display_name = discovered.get("name") or record["name"]
    seconds = discovered.get("interval_seconds")

    config["name"] = display_name
    config["code_hash"] = current_hash
    save_config(folder, config)

    inventory["brprocs"][record["short_id"]]["name"] = display_name

    if seconds is not None:
        state["schedule"]["seconds"] = seconds
        state["schedule"]["label"] = util.get_schedule_label(seconds)
        state["runtime"]["next_run"] = util.compute_next_run(seconds, state["runtime"]["last_run"])
        save_state(folder, state)

    return True


def _normalize_legacy_uuid_fields(data: dict) -> None:
    """
    Recast legacy "id" fields to "uuid" on read for compatibility.
    """
    if not isinstance(data, dict):
        return

    # Compatibility shim: accept legacy "id" on import for now and recast to "uuid".
    # Future cleanup: remove legacy "id" support once authored surfaces have migrated.
    if "uuid" not in data and "id" in data:
        data["uuid"] = data["id"]


def _log_duplicate_intake(
    item: Path,
    source_type: str,
    proc_id: str,
    existing_short_id: str,
    inventory: dict,
) -> None:
    """
    Write a project-wide note explaining that a duplicate intake item was dropped.
    """
    existing = inventory["brprocs"][existing_short_id]
    util.append_jsonl(
        get_project_log_path(),
        {
            "timestamp": util.now_epoch(),
            "action": "drop_duplicate_intake",
            "why": "duplicate uuid",
            "source": source_type,
            "incoming_name": item.name,
            "incoming_path": str(item),
            "uuid": proc_id,
            "existing_short_id": existing_short_id,
            "existing_folder": existing["folder"],
        },
    )


def _delete_drop_item(item: Path) -> None:
    """
    Remove an item from the drop directory after successful install.
    """
    if item.is_dir():
        shutil.rmtree(item)
    else:
        item.unlink()
