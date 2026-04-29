"""
Tkinter interface for Battery Runner.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
import time
from tkinter import messagebox, ttk

from batteryrunner import runner, storage, util


g = {
    "root": None,
    "rows": {},
    "last_snapshot": {"order": [], "rows": {}},
    "command_queue": None,
    "event_queue": None,
    "worker_stop": None,
    "worker_thread": None,
    "worker_gate": None,
    "clock_label": None,
}


COLUMN_SPECS = [
    {"title": "On", "minsize": 28},
    {"title": "Lock", "minsize": 34},
    {"title": "Schedule", "minsize": 84},
    {"title": "Bproc", "minsize": 250},
    {"title": "Actions", "minsize": 250},
    {"title": "Last Run", "minsize": 165},
    {"title": "Next Run", "minsize": 165},
    {"title": "Last Error", "minsize": 220},
]


BPROC_CODE_HELP_TEXT = """from batteryrunner import bproc_context as ctx

Required function:
def tick():
    pass

Primary context helpers:
ctx.get_now() -- int -- seconds since epoch
ctx.log(msg) -- fn(msg) -- post a log message to stdout and log.jsonl
ctx.get_state() -- {"uuid": str, "enabled": bool, "schedule": dict, "lock_on_error": bool, "runtime": dict, "config": dict}
ctx.get_config() -- dict -- short-cut to ctx.get_state()["config"]
ctx.get_shared() -- dict -- shared in-memory dictionary visible to all bprocs until Battery Runner exits
ctx.get_runtime() -- {"running": bool, "last_run": int|None, "next_run": int|None, "last_success": int|None, "last_error": dict, "error_count": int}
ctx.get_schedule() -- {"mode": str, "seconds": int, "label": str}
ctx.get_uuid() -- str -- full UUID string for the bproc
ctx.get_name() -- str -- display name for the bproc
ctx.get_root_path() -- pathlib.Path -- path to .batteryrunner/
ctx.get_bproc_path() -- pathlib.Path -- path to this bproc's installed folder

State details:
ctx.get_state()["uuid"] -- str -- full UUID string for the bproc
ctx.get_state()["enabled"] -- bool -- whether the bproc is enabled
ctx.get_state()["schedule"] -- {"mode": str, "seconds": int, "label": str}
ctx.get_state()["schedule"]["mode"] -- str -- current schedule mode, presently "interval"
ctx.get_state()["schedule"]["seconds"] -- int -- run interval in seconds
ctx.get_state()["schedule"]["label"] -- str -- UI label for the schedule
ctx.get_state()["lock_on_error"] -- bool -- if false, an error disables the bproc
ctx.get_state()["runtime"] -- {"running": bool, "last_run": int|None, "next_run": int|None, "last_success": int|None, "last_error": dict, "error_count": int}
ctx.get_state()["runtime"]["running"] -- bool -- whether the bproc is currently marked running
ctx.get_state()["runtime"]["last_run"] -- int|None -- epoch seconds of the last attempted run
ctx.get_state()["runtime"]["next_run"] -- int|None -- epoch seconds of the next scheduled run
ctx.get_state()["runtime"]["last_success"] -- int|None -- epoch seconds of the last successful run
ctx.get_state()["runtime"]["last_error"] -- {"timestamp": int|None, "message": str|None, "traceback": str|None}
ctx.get_state()["runtime"]["error_count"] -- int -- number of recorded failures

JSON helpers:
ctx.load_json(path) -- object -- resolves relative paths from the bproc folder and reports malformed JSON with path, line, and column
ctx.save_json(path, obj) -- None -- writes JSON relative to the bproc folder

Context lifecycle:
ctx.reset(d) -- replace the active per-run payload while preserving shared memory
ctx.clear() -- clear the active per-run payload while preserving shared memory
ctx.clear(reset_shared=True) -- also clear shared memory

Optional top-level metadata:
uuid = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
name = "Friendly Name"
interval_seconds = 300
"""


def launch_ui() -> None:
    """
    Start the Tkinter UI.
    """
    storage.ensure_runtime_layout()
    storage.process_intake()

    root = tk.Tk()
    root.title("Battery Runner")
    root.geometry("1180x720")
    g["root"] = root
    g["command_queue"] = queue.Queue()
    g["event_queue"] = queue.Queue()
    g["worker_stop"] = threading.Event()
    g["worker_gate"] = threading.RLock()

    _build_window(root)
    _refresh_rows(force=True)
    _start_worker()
    _update_clock()
    root.protocol("WM_DELETE_WINDOW", _on_close)
    _schedule_refresh()
    _schedule_event_poll()
    root.mainloop()


def _build_window(root) -> None:
    """
    Build the main window layout.
    """
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=1)

    header = ttk.Frame(root, padding=10)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_columnconfigure(0, weight=1)
    header.grid_columnconfigure(1, weight=1)
    header.grid_columnconfigure(2, weight=1)

    ttk.Label(header, text="Battery Runner", font=("Segoe UI", 18, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    clock_label = ttk.Label(header, text="", font=("Consolas", 12))
    clock_label.grid(row=0, column=1, sticky="n")
    g["clock_label"] = clock_label

    buttons = ttk.Frame(header)
    buttons.grid(row=0, column=2, sticky="e")
    ttk.Button(buttons, text="Create Bproc", command=_open_create_bproc_dialog).pack(
        side="left", padx=(8, 0)
    )

    columns = ttk.Frame(root, padding=(10, 0, 10, 10))
    columns.grid(row=1, column=0, sticky="nsew")
    columns.grid_rowconfigure(0, weight=1)
    columns.grid_columnconfigure(0, weight=1)

    canvas = tk.Canvas(columns, highlightthickness=0)
    scrollbar = ttk.Scrollbar(columns, orient="vertical", command=canvas.yview)
    body = ttk.Frame(canvas)
    body.bind(
        "<Configure>",
        lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
    )

    window_id = canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    columns.bind(
        "<Configure>",
        lambda event, item_id=window_id: canvas.itemconfigure(
            item_id,
            width=event.width - scrollbar.winfo_width(),
        ),
    )

    g["body"] = body
    _configure_grid_columns(body)
    _build_header_row(body)


def _update_clock() -> None:
    """
    Update the header clock once per second.
    """
    label = g["clock_label"]
    if label is None:
        return

    label.configure(text=time.strftime("%Y-%m-%d %H:%M:%S"))
    if not g["worker_stop"].is_set():
        g["root"].after(1000, _update_clock)


def _configure_grid_columns(frame) -> None:
    """
    Apply the shared column geometry used by headers and row data.
    """
    for index, spec in enumerate(COLUMN_SPECS):
        frame.grid_columnconfigure(index, minsize=spec["minsize"])


def _build_header_row(parent) -> None:
    """
    Build the header labels inside the same grid as the row data.
    """
    for index, spec in enumerate(COLUMN_SPECS):
        padx = (1 if index < 3 else 3)
        ttk.Label(parent, text=spec["title"]).grid(
            row=0, column=index, sticky="w", padx=padx, pady=(0, 4)
        )


def _refresh_rows(force: bool = False) -> bool:
    """
    Update the list of bprocs when the visible data changed.
    """
    records = storage.list_bproc_entries()
    plan = _build_display_plan(records)
    if not force and plan == g["last_snapshot"]:
        return False

    _remove_deleted_rows(plan)
    _create_missing_rows(plan, records)
    _update_existing_rows(plan)
    _regrid_rows(plan)
    g["last_snapshot"] = plan

    return True


def _build_display_plan(records: list[dict]) -> dict:
    """
    Capture the row data that is currently visible in the grid.
    """
    plan = {
        "order": [],
        "rows": {},
    }

    for record in records:
        state = record["state"]
        runtime = state["runtime"]
        short_id = record["short_id"]
        plan["order"].append(short_id)
        plan["rows"][short_id] = {
            "short_id": short_id,
            "name": record["name"],
            "enabled": state["enabled"],
            "lock_on_error": state["lock_on_error"],
            "schedule_label": state["schedule"]["label"],
            "last_run": runtime["last_run"],
            "next_run": runtime["next_run"],
            "last_error_message": runtime["last_error"]["message"] or "-",
            "has_logs": _bproc_has_logs(record),
        }

    return plan


def _remove_deleted_rows(plan: dict) -> None:
    """
    Remove any rows that no longer exist.
    """
    keep_ids = set(plan["rows"])
    for short_id in list(g["rows"]):
        if short_id in keep_ids:
            continue

        row = g["rows"].pop(short_id)
        for widget in row["widgets"]:
            widget.destroy()


def _create_missing_rows(plan: dict, records: list[dict]) -> None:
    """
    Create row widgets for any newly visible bprocs.
    """
    records_by_id = {record["short_id"]: record for record in records}

    for short_id in plan["order"]:
        if short_id in g["rows"]:
            continue

        _create_row_widgets(records_by_id[short_id])


def _update_existing_rows(plan: dict) -> None:
    """
    Update row widgets whose visible values changed.
    """
    old_rows = g["last_snapshot"]["rows"]

    for short_id in plan["order"]:
        row_plan = plan["rows"][short_id]
        if old_rows.get(short_id) == row_plan:
            continue

        _apply_row_plan(short_id, row_plan)


def _regrid_rows(plan: dict) -> None:
    """
    Place each row at the correct grid position.
    """
    for row_index, short_id in enumerate(plan["order"], start=1):
        row = g["rows"][short_id]
        row["enabled_widget"].grid_configure(row=row_index)
        row["lock_widget"].grid_configure(row=row_index)
        row["schedule_widget"].grid_configure(row=row_index)
        row["name_widget"].grid_configure(row=row_index)
        row["actions_widget"].grid_configure(row=row_index)
        row["last_run_widget"].grid_configure(row=row_index)
        row["next_run_widget"].grid_configure(row=row_index)
        row["error_widget"].grid_configure(row=row_index)


def _create_row_widgets(record: dict) -> None:
    """
    Create one row in the bproc grid.
    """
    parent = g["body"]
    state = record["state"]
    short_id = record["short_id"]

    enabled_var = tk.BooleanVar(value=state["enabled"])
    lock_var = tk.BooleanVar(value=state["lock_on_error"])
    schedule_var = tk.StringVar(value=state["schedule"]["label"])

    enabled_widget = ttk.Checkbutton(
        parent,
        variable=enabled_var,
        command=lambda sid=short_id, var=enabled_var: _toggle_enabled(sid, var),
    )
    enabled_widget.grid(column=0, sticky="w", padx=1, pady=3)

    lock_widget = ttk.Checkbutton(
        parent,
        variable=lock_var,
        command=lambda sid=short_id, var=lock_var: _toggle_lock(sid, var),
    )
    lock_widget.grid(column=1, sticky="w", padx=1, pady=3)

    schedule_menu = ttk.OptionMenu(
        parent,
        schedule_var,
        state["schedule"]["label"],
        *[label for label, _ in util.SCHEDULE_CHOICES],
        command=lambda label, sid=short_id: _change_schedule(sid, label),
    )
    schedule_menu.configure(width=8)
    schedule_menu.grid(column=2, sticky="w", padx=1, pady=3)

    name_widget = ttk.Label(parent)
    name_widget.grid(column=3, sticky="w", padx=3, pady=3)

    actions = ttk.Frame(parent)
    actions.grid(column=4, sticky="w", padx=3, pady=3)
    buttons = {}
    for text, fn in [
        ("Folder", lambda sid=short_id: _open_folder(sid)),
        ("Edit", lambda sid=short_id: _open_code_editor(sid)),
        ("Conf", lambda sid=short_id: _open_config_editor(sid)),
        ("Run", lambda sid=short_id: _run_now(sid)),
        ("Logs", lambda sid=short_id: _open_log_window(sid)),
        ("Errors", lambda sid=short_id: _open_error_window(sid)),
        ("Delete", lambda sid=short_id: _open_delete_dialog(sid)),
    ]:
        button = ttk.Button(actions, text=text, command=fn)
        button.pack(side="left", padx=(0, 2))
        buttons[text] = button

    last_run_widget = ttk.Label(parent)
    last_run_widget.grid(column=5, sticky="w", padx=3, pady=3)
    next_run_widget = ttk.Label(parent)
    next_run_widget.grid(column=6, sticky="w", padx=3, pady=3)
    error_widget = ttk.Label(parent)
    error_widget.grid(column=7, sticky="w", padx=3, pady=3)

    g["rows"][short_id] = {
        "enabled_var": enabled_var,
        "lock_var": lock_var,
        "schedule_var": schedule_var,
        "enabled_widget": enabled_widget,
        "lock_widget": lock_widget,
        "schedule_widget": schedule_menu,
        "name_widget": name_widget,
        "actions_widget": actions,
        "action_buttons": buttons,
        "last_run_widget": last_run_widget,
        "next_run_widget": next_run_widget,
        "error_widget": error_widget,
        "widgets": [
            enabled_widget,
            lock_widget,
            schedule_menu,
            name_widget,
            actions,
            last_run_widget,
            next_run_widget,
            error_widget,
        ],
    }
    _apply_row_plan(short_id, _build_display_plan([record])["rows"][short_id])


def _apply_row_plan(short_id: str, row_plan: dict) -> None:
    """
    Apply visible row data to existing widgets.
    """
    row = g["rows"][short_id]
    row["enabled_var"].set(row_plan["enabled"])
    row["lock_var"].set(row_plan["lock_on_error"])
    row["schedule_var"].set(row_plan["schedule_label"])
    row["name_widget"].configure(text=f"{row_plan['name']}  [{short_id}]")
    row["last_run_widget"].configure(text=util.format_timestamp(row_plan["last_run"]))
    row["next_run_widget"].configure(text=util.format_timestamp(row_plan["next_run"]))
    row["error_widget"].configure(text=row_plan["last_error_message"])
    has_error = row_plan["last_error_message"] != "-"
    has_logs = row_plan["has_logs"]
    row["action_buttons"]["Logs"].configure(state=("normal" if has_logs else "disabled"))
    row["action_buttons"]["Errors"].configure(state=("normal" if has_error else "disabled"))


def _toggle_enabled(short_id: str, var) -> None:
    """
    Toggle enabled status.
    """
    _run_with_worker_paused(storage.set_enabled, short_id, bool(var.get()))
    _refresh_rows()


def _toggle_lock(short_id: str, var) -> None:
    """
    Toggle lock-on-error behavior.
    """
    _run_with_worker_paused(storage.set_lock_on_error, short_id, bool(var.get()))
    _refresh_rows()


def _change_schedule(short_id: str, label: str) -> None:
    """
    Change schedule from the dropdown.
    """
    mapping = dict(util.SCHEDULE_CHOICES)
    _run_with_worker_paused(storage.set_schedule_seconds, short_id, mapping[label])
    _refresh_rows()


def _open_folder(short_id: str) -> None:
    """
    Open the bproc folder in Explorer.
    """
    record = storage.load_bproc_record(short_id)
    os.startfile(record["folder_path"])


def _run_now(short_id: str) -> None:
    """
    Run one bproc now.
    """
    _enqueue_worker_command("run_now", short_id)


def _open_error_window(short_id: str) -> None:
    """
    Show the last traceback.
    """
    record = storage.load_bproc_record(short_id)
    error = record["state"]["runtime"]["last_error"]

    top = tk.Toplevel(g["root"])
    top.title(f"Errors: {record['name']} [{short_id}]")
    top.geometry("900x480")
    top.grid_columnconfigure(0, weight=1)
    top.grid_rowconfigure(0, weight=1)

    text = tk.Text(top, wrap="none")
    text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    text.insert(
        "1.0",
        error["traceback"] or error["message"] or "No error captured.",
    )

    buttons = ttk.Frame(top, padding=(10, 0, 10, 10))
    buttons.grid(row=1, column=0, sticky="e")
    ttk.Button(
        buttons,
        text="Clear",
        command=lambda sid=short_id, win=top: _clear_error_and_close(sid, win),
    ).pack(side="left", padx=(0, 6))
    ttk.Button(
        buttons,
        text="Copy",
        command=lambda value=text.get("1.0", "end-1c"): _copy_to_clipboard(value),
    ).pack(side="left", padx=(0, 6))


def _open_log_window(short_id: str) -> None:
    """
    Show the per-bproc log.jsonl contents.
    """
    record = storage.load_bproc_record(short_id)
    log_path = storage.get_bproc_log_path(record["folder_path"])

    top = tk.Toplevel(g["root"])
    top.title(f"Logs: {record['name']} [{short_id}]")
    top.geometry("900x480")
    top.grid_columnconfigure(0, weight=1)
    top.grid_rowconfigure(0, weight=1)

    text = tk.Text(top, wrap="none")
    text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    if log_path.exists():
        text.insert("1.0", log_path.read_text(encoding="utf-8"))
    else:
        text.insert("1.0", "No logs yet.\n")

    buttons = ttk.Frame(top, padding=(10, 0, 10, 10))
    buttons.grid(row=1, column=0, sticky="e")
    ttk.Button(
        buttons,
        text="Clear",
        command=lambda sid=short_id, path=log_path, widget=text: _clear_log_and_refresh(sid, path, widget),
    ).pack(side="left", padx=(0, 6))
    ttk.Button(
        buttons,
        text="Refresh",
        command=lambda path=log_path, widget=text: _reload_log_text(path, widget),
    ).pack(side="left", padx=(0, 6))
    ttk.Button(
        buttons,
        text="Copy",
        command=lambda value=text.get("1.0", "end-1c"): _copy_to_clipboard(value),
    ).pack(side="left", padx=(0, 6))


def _reload_log_text(path, text_widget) -> None:
    """
    Reload log.jsonl into an open text widget.
    """
    text_widget.delete("1.0", "end")
    if path.exists():
        text_widget.insert("1.0", path.read_text(encoding="utf-8"))
    else:
        text_widget.insert("1.0", "No logs yet.\n")


def _clear_log_and_refresh(short_id: str, path, text_widget) -> None:
    """
    Clear the per-bproc log file and refresh both views.
    """
    record = _run_with_worker_paused(storage.load_bproc_record, short_id)
    _run_with_worker_paused(storage.clear_bproc_log, record["folder_path"])
    _reload_log_text(path, text_widget)
    _refresh_rows()


def _open_delete_dialog(short_id: str) -> None:
    """
    Prompt for bproc deletion behavior.
    """
    record = storage.load_bproc_record(short_id)
    top = tk.Toplevel(g["root"])
    top.title("Delete Bproc")
    top.geometry("420x150")
    top.resizable(False, False)
    top.grid_columnconfigure(0, weight=1)

    frame = ttk.Frame(top, padding=12)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.grid_columnconfigure(0, weight=1)

    ttk.Label(
        frame,
        text=f"Delete Request: {record['name']} [{short_id}]",
    ).grid(row=0, column=0, sticky="w", pady=(0, 10))

    delete_folder_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        frame,
        text="Delete bproc folder as well",
        variable=delete_folder_var,
    ).grid(row=1, column=0, sticky="w", pady=(0, 12))

    buttons = ttk.Frame(frame)
    buttons.grid(row=2, column=0, sticky="e")
    ttk.Button(
        buttons,
        text="Confirm",
        command=lambda sid=short_id, var=delete_folder_var, win=top: _confirm_delete_bproc(
            sid,
            bool(var.get()),
            win,
        ),
    ).pack(side="left", padx=(0, 6))
    ttk.Button(buttons, text="Cancel", command=top.destroy).pack(side="left")


def _confirm_delete_bproc(short_id: str, delete_folder: bool, window) -> None:
    """
    Delete a bproc per the chosen confirmation options.
    """
    try:
        _run_with_worker_paused(storage.delete_bproc, short_id, delete_folder)
    except Exception as exc:
        messagebox.showerror("Delete Bproc", str(exc), parent=window)
        return

    window.destroy()
    _refresh_rows(force=True)


def _bproc_has_logs(record: dict) -> bool:
    """
    Return True when a bproc has a non-empty log.jsonl file.
    """
    log_path = storage.get_bproc_log_path(record["folder_path"])
    return log_path.exists() and log_path.stat().st_size > 0


def _clear_error_and_close(short_id: str, window) -> None:
    """
    Clear the stored last error.
    """
    record = _run_with_worker_paused(storage.load_bproc_record, short_id)
    state = record["state"]
    state["runtime"]["last_error"] = {
        "timestamp": None,
        "message": None,
        "traceback": None,
    }
    _run_with_worker_paused(storage.save_state, record["folder_path"], state)
    window.destroy()
    _refresh_rows()


def _open_code_editor(short_id: str) -> None:
    """
    Open a code.py editor window.
    """
    record = storage.load_bproc_record(short_id)
    code_path = record["folder_path"] / "code.py"
    text = code_path.read_text(encoding="utf-8")

    _open_text_editor(
        title=f"Edit Code: {record['name']} [{short_id}]",
        initial_text=text,
        on_save=lambda value, sid=short_id: _save_code_and_refresh(sid, value),
        help_text=BPROC_CODE_HELP_TEXT,
    )


def _open_config_editor(short_id: str) -> None:
    """
    Open the config editor window.
    """
    record = storage.load_bproc_record(short_id)
    text = json.dumps(record["state"]["config"], indent=2)

    _open_text_editor(
        title=f"Edit Config: {record['name']} [{short_id}]",
        initial_text=text,
        on_save=lambda value, sid=short_id: _save_config_and_refresh(sid, value),
    )


def _open_create_bproc_dialog() -> None:
    """
    Prompt for metadata and create a new starter bproc.
    """
    top = tk.Toplevel(g["root"])
    top.title("Create Bproc")
    top.resizable(False, False)
    top.grid_columnconfigure(1, weight=1)

    name_var = tk.StringVar(value="New Bproc")
    uuid_var = tk.StringVar(value="")
    schedule_var = tk.StringVar(value="1 hour")
    lock_var = tk.BooleanVar(value=True)

    ttk.Label(top, text="Name").grid(row=0, column=0, sticky="w", padx=10, pady=(12, 6))
    name_entry = ttk.Entry(top, textvariable=name_var)
    name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(12, 6))

    ttk.Label(top, text="UUID").grid(row=1, column=0, sticky="w", padx=10, pady=6)
    uuid_entry = ttk.Entry(top, textvariable=uuid_var)
    uuid_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=6)

    ttk.Label(top, text="Schedule").grid(row=2, column=0, sticky="w", padx=10, pady=6)
    schedule_menu = ttk.OptionMenu(
        top,
        schedule_var,
        "1 hour",
        *[label for label, _ in util.SCHEDULE_CHOICES],
    )
    schedule_menu.configure(width=10)
    schedule_menu.grid(row=2, column=1, sticky="w", padx=(0, 10), pady=6)

    ttk.Label(top, text="Lock").grid(row=3, column=0, sticky="w", padx=10, pady=6)
    ttk.Checkbutton(top, variable=lock_var).grid(row=3, column=1, sticky="w", padx=(0, 10), pady=6)

    note = (
        "Creates a starter bproc with code.py,\n"
        "bproc.json, and state.json.\n"
        "Leave UUID blank to auto-generate one."
    )
    ttk.Label(top, text=note).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 10))

    buttons = ttk.Frame(top)
    buttons.grid(row=5, column=0, columnspan=2, sticky="e", padx=10, pady=(0, 10))
    ttk.Button(
        buttons,
        text="Create",
        command=lambda: _create_bproc_from_dialog(top, name_var, uuid_var, schedule_var, lock_var),
    ).pack(side="left", padx=(0, 6))
    ttk.Button(buttons, text="Cancel", command=top.destroy).pack(side="left")

    name_entry.focus_set()
    name_entry.selection_range(0, "end")
    top.update_idletasks()
    top.minsize(420, top.winfo_reqheight())


def _open_text_editor(title: str, initial_text: str, on_save, help_text: str | None = None) -> None:
    """
    Open a generic text editor window.
    """
    top = tk.Toplevel(g["root"])
    top.title(title)
    top.geometry("980x640")
    top.grid_columnconfigure(0, weight=1)
    top.grid_rowconfigure(0, weight=1)

    text = tk.Text(top, wrap="none", undo=True)
    text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    text.insert("1.0", initial_text)

    buttons = ttk.Frame(top, padding=(10, 0, 10, 10))
    buttons.grid(row=1, column=0, sticky="e")
    ttk.Button(
        buttons,
        text="Save",
        command=lambda: _handle_editor_save(top, text, on_save),
    ).pack(side="left", padx=(0, 6))
    if help_text is not None:
        ttk.Button(
            buttons,
            text="Help",
            command=lambda value=help_text, parent=top: _open_help_window("Bproc Code Help", value, parent),
        ).pack(side="left", padx=(0, 6))


def _handle_editor_save(window, text_widget, on_save) -> None:
    """
    Run editor save logic with friendly error handling.
    """
    try:
        on_save(text_widget.get("1.0", "end-1c"))
    except Exception as exc:
        messagebox.showerror("Save failed", str(exc), parent=window)
        return

    window.destroy()
    _refresh_rows()


def _create_bproc_from_dialog(window, name_var, uuid_var, schedule_var, lock_var) -> None:
    """
    Validate create-bproc form data and create the new bproc.
    """
    name = name_var.get().strip()
    if not name:
        messagebox.showerror("Create Bproc", "Name is required.", parent=window)
        return

    mapping = dict(util.SCHEDULE_CHOICES)
    try:
        seconds = mapping[schedule_var.get()]
    except KeyError:
        messagebox.showerror("Create Bproc", "Choose a valid schedule.", parent=window)
        return

    try:
        proc_uuid = uuid_var.get().strip()
        if proc_uuid:
            _run_with_worker_paused(
                storage.create_bproc_with_id,
                name,
                proc_uuid,
                seconds,
                bool(lock_var.get()),
            )
        else:
            _run_with_worker_paused(storage.create_bproc, name, seconds, bool(lock_var.get()))
    except Exception as exc:
        messagebox.showerror("Create Bproc", str(exc), parent=window)
        return

    window.destroy()
    _refresh_rows(force=True)


def _save_code_and_refresh(short_id: str, value: str) -> None:
    """
    Save code.py after basic validation.
    """
    compile(value, f"{short_id}/code.py", "exec")
    _run_with_worker_paused(storage.save_bproc_code_text, short_id, value)


def _save_config_and_refresh(short_id: str, value: str) -> None:
    """
    Save config after parsing JSON.
    """
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    _run_with_worker_paused(storage.save_bproc_config_object, short_id, data)


def _copy_to_clipboard(value: str) -> None:
    """
    Copy text to the clipboard.
    """
    root = g["root"]
    root.clipboard_clear()
    root.clipboard_append(value)
    root.update()


def _open_help_window(title: str, help_text: str, parent) -> None:
    """
    Open a simple help window containing reference text.
    """
    top = tk.Toplevel(parent)
    top.title(title)
    top.geometry("980x520")
    top.grid_columnconfigure(0, weight=1)
    top.grid_rowconfigure(0, weight=1)

    frame = ttk.Frame(top, padding=10)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(0, weight=1)

    text = tk.Text(frame, wrap="none")
    text.grid(row=0, column=0, sticky="nsew")
    text.insert("1.0", help_text)

    buttons = ttk.Frame(top, padding=(10, 0, 10, 10))
    buttons.grid(row=1, column=0, sticky="e")
    ttk.Button(
        buttons,
        text="Copy",
        command=lambda value=text.get("1.0", "end-1c"): _copy_to_clipboard(value),
    ).pack(side="left", padx=(0, 6))
    ttk.Button(buttons, text="Cancel", command=top.destroy).pack(side="left")


def _scan_drop_and_refresh() -> None:
    """
    Install dropped items and redraw the UI.
    """
    _enqueue_worker_command("scan")


def _tick_due_and_refresh() -> None:
    """
    Run one scheduler pass and redraw.
    """
    _enqueue_worker_command("tick_due")


def _schedule_refresh() -> None:
    """
    Periodically refresh the display.
    """
    g["root"].after(1000, _refresh_loop)


def _refresh_loop() -> None:
    """
    Refresh rows and reschedule.
    """
    _refresh_rows()
    _schedule_refresh()


def _schedule_event_poll() -> None:
    """
    Poll the worker event queue.
    """
    g["root"].after(200, _process_worker_events)


def _process_worker_events() -> None:
    """
    Drain worker events and reschedule.
    """
    while True:
        try:
            event_type, payload = g["event_queue"].get_nowait()
        except queue.Empty:
            break

        if event_type == "refresh":
            _refresh_rows(force=bool(payload))
        elif event_type == "error":
            messagebox.showerror("Battery Runner Worker Error", str(payload), parent=g["root"])

    if not g["worker_stop"].is_set():
        _schedule_event_poll()


def _enqueue_worker_command(command: str, payload=None) -> None:
    """
    Queue work for the background worker.
    """
    g["command_queue"].put((command, payload))


def _start_worker() -> None:
    """
    Start the scheduler worker thread.
    """
    worker = threading.Thread(
        target=_worker_main,
        name="battery-runner-worker",
        daemon=True,
    )
    g["worker_thread"] = worker
    worker.start()


def _worker_main() -> None:
    """
    Run scheduler and explicit commands off the Tk thread.
    """
    next_scheduler_at = time.monotonic() + 1.0

    while not g["worker_stop"].is_set():
        timeout = max(0.0, next_scheduler_at - time.monotonic())
        try:
            command, payload = g["command_queue"].get(timeout=timeout)
        except queue.Empty:
            command = "scheduler"
            payload = None

        try:
            force_refresh = _handle_worker_command(command, payload)
        except Exception as exc:
            g["event_queue"].put(("error", exc))
            force_refresh = False

        if force_refresh:
            g["event_queue"].put(("refresh", False))

        if command != "scheduler" and time.monotonic() >= next_scheduler_at:
            try:
                if _handle_worker_command("scheduler", None):
                    g["event_queue"].put(("refresh", False))
            except Exception as exc:
                g["event_queue"].put(("error", exc))

        if command == "scheduler" or time.monotonic() >= next_scheduler_at:
            next_scheduler_at = time.monotonic() + 1.0


def _handle_worker_command(command: str, payload) -> bool:
    """
    Execute one worker command and report whether the UI should refresh.
    """
    with g["worker_gate"]:
        if command == "scan":
            storage.process_drop()
            return True

        if command == "tick_due":
            runner.run_scheduler_pass()
            return True

        if command == "run_now":
            runner.run_bproc_now(payload)
            return True

        if command == "scheduler":
            runner.run_scheduler_pass()
            return True

    raise ValueError(f"Unknown worker command: {command}")


def _on_close() -> None:
    """
    Stop the worker thread and close the window.
    """
    g["worker_stop"].set()
    g["root"].destroy()


def _run_with_worker_paused(fn, *args, **kwargs):
    """
    Run a UI-side storage mutation while excluding worker activity.
    """
    with g["worker_gate"]:
        return fn(*args, **kwargs)
