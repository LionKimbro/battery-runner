"""
CLI entrypoint and command declarations for Battery Runner.
"""

from __future__ import annotations

import json

import lionscliapp as app

from batteryrunner import __version__, runner, storage, ui, util


def main() -> None:
    """
    Declare the application and enter lionscliapp.
    """
    app.declare_app("battery-runner", __version__)
    app.describe_app("Host and schedule small filesystem-backed bprocs.")
    app.declare_projectdir(".batteryrunner")
    app.set_flag("search_upwards_for_project_dir", True)

    app.declare_cmd("", cmd_ui)
    app.declare_cmd("ui", cmd_ui)
    app.declare_cmd("scan", cmd_scan)
    app.declare_cmd("tick", cmd_tick)
    app.declare_cmd("list", cmd_list)

    app.describe_cmd("ui", "Open the Battery Runner Tkinter UI.")
    app.describe_cmd("scan", "Install any dropped bprocs without opening the UI.")
    app.describe_cmd("tick", "Run one scheduler pass without opening the UI.")
    app.describe_cmd("list", "Print installed bprocs and current runtime summary.")

    app.main()


def cmd_ui() -> None:
    """
    Open the Battery Runner UI.
    """
    ui.launch_ui()


def cmd_scan() -> None:
    """
    Install intake bprocs and print a short summary.
    """
    storage.ensure_runtime_layout()
    installed = storage.process_intake()

    payload = {
        "installed": len(installed),
        "brprocs": [
            {
                "short_id": item["short_id"],
                "name": item["name"],
                "folder": item["folder"],
            }
            for item in installed
        ],
    }
    print(json.dumps(payload, indent=2))


def cmd_tick() -> None:
    """
    Run a scheduler pass and print what ran.
    """
    storage.ensure_runtime_layout()
    ran = runner.run_scheduler_pass()
    payload = {
        "ran": len(ran),
        "brprocs": [
            {
                "short_id": item["short_id"],
                "name": item["name"],
                "last_run": item["state"]["runtime"]["last_run"],
                "last_error": item["state"]["runtime"]["last_error"]["message"],
            }
            for item in ran
        ],
    }
    print(json.dumps(payload, indent=2))


def cmd_list() -> None:
    """
    Print installed bprocs with runtime summary.
    """
    storage.ensure_runtime_layout()
    rows = []
    for item in storage.list_bproc_entries():
        state = item["state"]
        runtime = state["runtime"]
        rows.append(
            {
                "short_id": item["short_id"],
                "name": item["name"],
                "enabled": state["enabled"],
                "lock_on_error": state["lock_on_error"],
                "schedule_seconds": state["schedule"]["seconds"],
                "schedule_label": util.get_schedule_label(state["schedule"]["seconds"]),
                "last_run": runtime["last_run"],
                "next_run": runtime["next_run"],
                "last_error": runtime["last_error"]["message"],
            }
        )

    print(json.dumps({"count": len(rows), "brprocs": rows}, indent=2))
