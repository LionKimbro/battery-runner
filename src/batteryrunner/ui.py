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


def launch_ui() -> None:
    """
    Start the Tkinter UI.
    """
    storage.ensure_runtime_layout()
    storage.process_drop()

    root = tk.Tk()
    root.title("Battery Runner")
    root.geometry("1180x720")
    g["root"] = root
    g["command_queue"] = queue.Queue()
    g["event_queue"] = queue.Queue()
    g["worker_stop"] = threading.Event()

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
    ttk.Button(buttons, text="Scan Drop", command=_scan_drop_and_refresh).pack(
        side="left", padx=(8, 0)
    )
    ttk.Button(buttons, text="Tick Due", command=_tick_due_and_refresh).pack(
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
    for text, fn in [
        ("Folder", lambda sid=short_id: _open_folder(sid)),
        ("Edit", lambda sid=short_id: _open_code_editor(sid)),
        ("Conf", lambda sid=short_id: _open_config_editor(sid)),
        ("Run", lambda sid=short_id: _run_now(sid)),
        ("Errors", lambda sid=short_id: _open_error_window(sid)),
    ]:
        ttk.Button(actions, text=text, command=fn).pack(side="left", padx=(0, 2))

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


def _toggle_enabled(short_id: str, var) -> None:
    """
    Toggle enabled status.
    """
    storage.set_enabled(short_id, bool(var.get()))
    _refresh_rows()


def _toggle_lock(short_id: str, var) -> None:
    """
    Toggle lock-on-error behavior.
    """
    storage.set_lock_on_error(short_id, bool(var.get()))
    _refresh_rows()


def _change_schedule(short_id: str, label: str) -> None:
    """
    Change schedule from the dropdown.
    """
    mapping = dict(util.SCHEDULE_CHOICES)
    storage.set_schedule_seconds(short_id, mapping[label])
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
    ttk.Button(buttons, text="Cancel", command=top.destroy).pack(side="left")


def _clear_error_and_close(short_id: str, window) -> None:
    """
    Clear the stored last error.
    """
    record = storage.load_bproc_record(short_id)
    state = record["state"]
    state["runtime"]["last_error"] = {
        "timestamp": None,
        "message": None,
        "traceback": None,
    }
    storage.save_state(record["folder_path"], state)
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


def _open_text_editor(title: str, initial_text: str, on_save) -> None:
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
    ttk.Button(buttons, text="Cancel", command=top.destroy).pack(side="left")


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


def _save_code_and_refresh(short_id: str, value: str) -> None:
    """
    Save code.py after basic validation.
    """
    compile(value, f"{short_id}/code.py", "exec")
    storage.save_bproc_code_text(short_id, value)


def _save_config_and_refresh(short_id: str, value: str) -> None:
    """
    Save config after parsing JSON.
    """
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    storage.save_bproc_config_object(short_id, data)


def _copy_to_clipboard(value: str) -> None:
    """
    Copy text to the clipboard.
    """
    root = g["root"]
    root.clipboard_clear()
    root.clipboard_append(value)
    root.update()


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
