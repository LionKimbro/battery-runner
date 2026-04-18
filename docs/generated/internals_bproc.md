# Bproc Folder Internals

This article describes the internal structure of one installed bproc folder.

An installed bproc lives under:

```text
.batteryrunner/brprocs/<name>__<shortid>/
```

Example:

```text
.batteryrunner/brprocs/message_reporter__abc123def456/
```

## Typical Files

A bproc folder typically contains:

- `code.py`
- `state.json`
- `bproc.json`
- any support files that were included in the drop-off

Examples of support files:

- `template.txt`
- `prompt.md`
- `data.json`
- image files
- local output files created by the bproc

## `code.py`

This is the runnable Python module for the bproc.

Battery Runner imports this file dynamically and calls:

```python
tick(context)
```

For the code contract, see [bproc_code.md](./bproc_code.md).

## `state.json`

This is the main runtime and configuration state file for the bproc.

Battery Runner writes and updates this file directly.

Current shape:

```json
{
  "id": "GUID",
  "enabled": true,
  "schedule": {
    "mode": "interval",
    "seconds": 3600,
    "label": "1 hour"
  },
  "lock_on_error": true,
  "runtime": {
    "running": false,
    "last_run": null,
    "next_run": 1776542400,
    "last_success": null,
    "last_error": {
      "timestamp": null,
      "message": null,
      "traceback": null
    },
    "error_count": 0
  },
  "config": {}
}
```

### Important `state.json` Fields

- `enabled`
  Whether the scheduler should consider this bproc.

- `schedule.seconds`
  Interval in seconds between runs.

- `schedule.label`
  Human-facing schedule label used by the UI.

- `lock_on_error`
  If `true`, the bproc remains enabled after errors.
  If `false`, an error disables the bproc.

- `runtime.last_run`
  Epoch-seconds timestamp of the last attempted run.

- `runtime.next_run`
  Next scheduled runtime, stored as epoch seconds.

- `runtime.last_success`
  Epoch-seconds timestamp of the last successful run.

- `runtime.last_error`
  Captured message and traceback from the most recent error.

- `runtime.error_count`
  Number of recorded failures.

- `config`
  User-editable JSON object for bproc-specific settings.

## `bproc.json`

This is the identity/config metadata file Battery Runner keeps for the bproc.

Current shape:

```json
{
  "id": "GUID",
  "short_id": "abc123def456",
  "name": "Message Reporter",
  "folder": "message_reporter__abc123def456",
  "entry": "code.py",
  "installed_at": "2026-04-18T20:00:00+00:00"
}
```

Battery Runner currently preserves a dropped `bproc.json` if one was supplied, then normalizes key fields like ID, short ID, folder, and entry.

## Installation Behavior

When a dropped item is installed:

- the new bproc gets a GUID
- the short ID is the first 12 characters of that GUID string
- the folder name becomes `<slug>__<shortid>`
- `code.py` is ensured to exist
- `state.json` is created or merged from defaults
- `bproc.json` is created or merged from defaults

## Where The UI Writes

The UI currently edits:

- `code.py`
- `state.json["config"]`
- `state.json["enabled"]`
- `state.json["lock_on_error"]`
- `state.json["schedule"]`
- `state.json["runtime"]["last_error"]` when clearing errors

## What Battery Runner Does Not Require

An installed bproc does not currently need:

- a package structure
- an `__init__.py`
- a class
- a manifest beyond the files above

The minimal runnable installation is just:

```text
<bproc>/
  code.py
  state.json
  bproc.json
```
