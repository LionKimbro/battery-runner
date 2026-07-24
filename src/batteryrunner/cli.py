"""
CLI entrypoint and command declarations for Battery Runner.
"""

from __future__ import annotations

import json
import sys
import time

import lionscliapp as app

from batteryrunner import __version__, runner, storage, util


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
    app.declare_cmd("serve", cmd_serve)
    app.declare_cmd("run", cmd_run)
    app.declare_key("serve.sleep_seconds", 5)
    app.declare_key("run.target", "")
    app.describe_key("serve.sleep_seconds", "Seconds to sleep between headless scheduler passes.")
    app.describe_key("run.target", "Short id or exact name for the bproc to run.")

    app.describe_cmd("ui", "Open the Battery Runner Tkinter UI.")
    app.describe_cmd("scan", "Install any dropped bprocs without opening the UI.")
    app.describe_cmd("tick", "Run one scheduler pass without opening the UI.")
    app.describe_cmd("list", "Print installed bprocs and current runtime summary.")
    app.describe_cmd("serve", "Run continuously without opening the UI.")
    app.describe_cmd("run", "Run one bproc immediately; set --run.target first.")

    normalize_run_command_argv()
    app.main()


def normalize_run_command_argv() -> None:
    """
    Let users type `battery-runner run <id-or-name>` with lionscliapp.
    """
    args = sys.argv[1:]
    for index, token in enumerate(args):
        if token != "run":
            continue
        target_index = index + 1
        if target_index >= len(args) or args[target_index].startswith("--"):
            return

        target = args[target_index]
        del sys.argv[target_index + 1]
        sys.argv[1:1] = ["--run.target", target]
        return


def cmd_ui() -> None:
    """
    Open the Battery Runner UI.
    """
    from batteryrunner import ui

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
                "last_run": item["runtime"]["last_run"],
                "last_error": item["runtime"]["last_error"]["message"],
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
        runtime = item["runtime"]
        rows.append(
            {
                "short_id": item["short_id"],
                "name": item["name"],
                "enabled": item["settings"]["enabled"],
                "disable_on_error": item["settings"]["disable_on_error"],
                "lock_on_error": state["lock_on_error"],
                "schedule_seconds": item["settings"]["schedule"]["seconds"],
                "schedule_label": util.get_schedule_label(item["settings"]["schedule"]["seconds"]),
                "last_run": runtime["last_run"],
                "next_run": runtime["next_run"],
                "last_error": runtime["last_error"]["message"],
            }
        )

    print(json.dumps({"count": len(rows), "brprocs": rows}, indent=2))


def cmd_serve() -> None:
    """
    Continuously run scheduler passes without importing the Tkinter UI.
    """
    storage.ensure_runtime_layout()
    sleep_seconds = int(app.ctx["serve.sleep_seconds"])
    print(f"Battery Runner headless service started. sleep_seconds={sleep_seconds}")

    try:
        while True:
            ran = runner.run_scheduler_pass()
            if ran:
                print(json.dumps({"ran": [item["short_id"] for item in ran]}, indent=2))
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("Battery Runner headless service stopped.")


def cmd_run() -> None:
    """
    Run one bproc immediately by short id or exact name.
    """
    storage.ensure_runtime_layout()
    target = app.ctx["run.target"].strip()
    if not target:
        raise ValueError("Usage: battery-runner --run.target <id-or-name> run")

    record = storage.resolve_bproc(target)
    result = runner.run_bproc_now(record["short_id"])
    runtime = result["runtime"]
    payload = {
        "short_id": result["short_id"],
        "name": result["name"],
        "last_run": runtime["last_run"],
        "last_success": runtime["last_success"],
        "last_error": runtime["last_error"]["message"],
    }
    print(json.dumps(payload, indent=2))
