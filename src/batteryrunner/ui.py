"""
Tkinter interface for Battery Runner.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import messagebox, ttk

from batteryrunner import runner, storage, util


g = {
    "root": None,
    "rows": {},
    "last_snapshot": None,
}


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

    _build_window(root)
    _refresh_rows()
    _schedule_refresh()
    _schedule_scheduler()
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

    ttk.Label(header, text="Battery Runner", font=("Segoe UI", 18, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Button(header, text="Scan Drop", command=_scan_drop_and_refresh).grid(
        row=0, column=1, padx=(8, 0)
    )
    ttk.Button(header, text="Tick Due", command=_tick_due_and_refresh).grid(
        row=0, column=2, padx=(8, 0)
    )

    columns = ttk.Frame(root, padding=(10, 0, 10, 10))
    columns.grid(row=1, column=0, sticky="nsew")
    columns.grid_rowconfigure(1, weight=1)
    columns.grid_columnconfigure(0, weight=1)

    labels = ttk.Frame(columns)
    labels.grid(row=0, column=0, sticky="ew")
    label_text = [
        "On",
        "Keep Going",
        "Schedule",
        "Bproc",
        "Actions",
        "Last Run",
        "Next Run",
        "Last Error",
    ]
    widths = [4, 10, 12, 22, 28, 20, 20, 36]

    for index, text in enumerate(label_text):
        ttk.Label(labels, text=text, width=widths[index]).grid(
            row=0, column=index, sticky="w", padx=4, pady=(0, 4)
        )

    canvas = tk.Canvas(columns, highlightthickness=0)
    scrollbar = ttk.Scrollbar(columns, orient="vertical", command=canvas.yview)
    body = ttk.Frame(canvas)
    body.bind(
        "<Configure>",
        lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
    )

    window_id = canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=1, column=0, sticky="nsew")
    scrollbar.grid(row=1, column=1, sticky="ns")

    columns.bind(
        "<Configure>",
        lambda event, item_id=window_id: canvas.itemconfigure(
            item_id,
            width=event.width - scrollbar.winfo_width(),
        ),
    )

    g["body"] = body


def _refresh_rows(force: bool = False) -> bool:
    """
    Rebuild the list of bprocs when the visible data changed.
    """
    records = storage.list_bproc_entries()
    snapshot = _build_display_snapshot(records)
    if not force and snapshot == g["last_snapshot"]:
        return False

    body = g["body"]
    for child in body.winfo_children():
        child.destroy()

    g["rows"].clear()
    g["last_snapshot"] = snapshot

    for row_index, record in enumerate(records):
        _build_row(body, row_index, record)

    return True


def _build_display_snapshot(records: list[dict]) -> list[dict]:
    """
    Capture the row data that is currently visible in the grid.
    """
    snapshot = []

    for record in records:
        state = record["state"]
        runtime = state["runtime"]
        snapshot.append(
            {
                "short_id": record["short_id"],
                "name": record["name"],
                "enabled": state["enabled"],
                "lock_on_error": state["lock_on_error"],
                "schedule_label": state["schedule"]["label"],
                "last_run": runtime["last_run"],
                "next_run": runtime["next_run"],
                "last_error_message": runtime["last_error"]["message"],
            }
        )

    return snapshot


def _build_row(parent, row_index: int, record: dict) -> None:
    """
    Create one row in the bproc grid.
    """
    state = record["state"]
    runtime = state["runtime"]
    short_id = record["short_id"]

    enabled_var = tk.BooleanVar(value=state["enabled"])
    lock_var = tk.BooleanVar(value=state["lock_on_error"])
    schedule_var = tk.StringVar(value=state["schedule"]["label"])

    ttk.Checkbutton(
        parent,
        variable=enabled_var,
        command=lambda sid=short_id, var=enabled_var: _toggle_enabled(sid, var),
    ).grid(row=row_index, column=0, sticky="w", padx=4, pady=4)

    ttk.Checkbutton(
        parent,
        variable=lock_var,
        command=lambda sid=short_id, var=lock_var: _toggle_lock(sid, var),
    ).grid(row=row_index, column=1, sticky="w", padx=4, pady=4)

    schedule_menu = ttk.OptionMenu(
        parent,
        schedule_var,
        state["schedule"]["label"],
        *[label for label, _ in util.SCHEDULE_CHOICES],
        command=lambda label, sid=short_id: _change_schedule(sid, label),
    )
    schedule_menu.grid(row=row_index, column=2, sticky="ew", padx=4, pady=4)

    ttk.Label(parent, text=f"{record['name']}  [{short_id}]").grid(
        row=row_index, column=3, sticky="w", padx=4, pady=4
    )

    actions = ttk.Frame(parent)
    actions.grid(row=row_index, column=4, sticky="w", padx=4, pady=4)
    for text, fn in [
        ("Folder", lambda sid=short_id: _open_folder(sid)),
        ("Edit", lambda sid=short_id: _open_code_editor(sid)),
        ("Conf", lambda sid=short_id: _open_config_editor(sid)),
        ("Run", lambda sid=short_id: _run_now(sid)),
        ("Errors", lambda sid=short_id: _open_error_window(sid)),
    ]:
        ttk.Button(actions, text=text, command=fn).pack(side="left", padx=(0, 4))

    ttk.Label(parent, text=util.format_timestamp(runtime["last_run"])).grid(
        row=row_index, column=5, sticky="w", padx=4, pady=4
    )
    ttk.Label(parent, text=util.format_timestamp(runtime["next_run"])).grid(
        row=row_index, column=6, sticky="w", padx=4, pady=4
    )

    last_error = runtime["last_error"]["message"] or "-"
    ttk.Label(parent, text=last_error).grid(
        row=row_index, column=7, sticky="w", padx=4, pady=4
    )

    g["rows"][short_id] = {
        "enabled_var": enabled_var,
        "lock_var": lock_var,
        "schedule_var": schedule_var,
    }


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
    runner.run_bproc_now(short_id)
    _refresh_rows()


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
    storage.process_drop()
    _refresh_rows()


def _tick_due_and_refresh() -> None:
    """
    Run one scheduler pass and redraw.
    """
    runner.run_scheduler_pass()
    _refresh_rows()


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


def _schedule_scheduler() -> None:
    """
    Periodically run due bprocs.
    """
    g["root"].after(500, _scheduler_loop)


def _scheduler_loop() -> None:
    """
    Run the scheduler and reschedule.
    """
    runner.run_scheduler_pass()
    _schedule_scheduler()
