# Battery Runner Runtime Internals

This article describes the broader Battery Runner runtime layout and the files Battery Runner manages for the whole system.

For the internals of one installed bproc, see [internals_bproc.md](./internals_bproc.md).

## Runtime Root

Battery Runner operates inside a project-local runtime directory:

```text
.batteryrunner/
```

This directory is created automatically when Battery Runner starts working in a project.

## Top-Level Runtime Layout

Current layout:

```text
.batteryrunner/
  brprocs/
  brprocs-inventory.json
  drop/
  inbox/
  outbox/
```

## `brprocs/`

This directory contains the installed bprocs.

Each subdirectory is named:

```text
<name>__<shortid>
```

Example:

```text
message_reporter__abc123def456
```

## `brprocs-inventory.json`

This is the top-level inventory index of installed bprocs.

Current shape:

```json
{
  "version": "v1",
  "brprocs": {
    "abc123def456": {
      "uuid": "full-uuid-string",
      "name": "Message Reporter",
      "short_id": "abc123def456",
      "folder": "message_reporter__abc123def456",
      "entry": "code.py",
      "installed_at": "2026-04-18T20:00:00+00:00",
      "source": {
        "type": "drop"
      }
    }
  }
}
```

Important fields:

- `version`
  Format version for the inventory.

- `brprocs`
  Object keyed by short ID.

- `uuid`
  Canonical per-bproc UUID. Legacy `id` may still be accepted on import for compatibility, but authored/current data should use `uuid`.

- `short_id`
  A collision-resistant short identifier derived from the full UUID and used for inventory keys and folder suffixes.

- `source.type`
  Currently always `"drop"` in this implementation.

## `drop/`

This is the intake area for new bprocs.

Battery Runner scans this directory and installs every file or folder found there.

Accepted practical forms include:

- a single `.py` file
- a folder containing `code.py`
- a folder containing `code.py`, `state.json`, `bproc.json`, and support files
- a non-Python file or folder, in which case Battery Runner will still install it but may generate a starter `code.py` if needed

## `inbox/` and `outbox/`

These directories are created and reserved for future use.

Battery Runner does not currently implement routing, Patchboard handling, or other message transport behavior in them.

They are present as designated runtime surfaces only.

## System-Wide Behavior

The system currently works like this:

1. ensure runtime layout exists
2. process `drop/`
3. keep installed bprocs indexed in `brprocs-inventory.json`
4. run due bprocs by reading their individual `state.json` files
5. update runtime fields after each run

## Scheduler Behavior

The scheduler pass currently:

- processes the drop folder first
- loads the inventory
- loads each bproc state
- skips disabled bprocs
- skips bprocs already marked as running
- runs bprocs whose `next_run` is due
- records success or error
- computes a new `next_run`

## UI Relationship To Runtime Files

The UI is mostly a direct editor/controller for these runtime files.

The UI reads from and writes to:

- `brprocs-inventory.json`
- each installed bproc's `state.json`
- each installed bproc's `code.py`

This keeps the system human-legible and filesystem-driven.

## CLI Relationship To Runtime Files

The CLI commands operate on the same files:

- `scan` processes `drop/`
- `tick` processes `drop/` and runs due bprocs
- `list` reports current state
- default command / `ui` opens the Tk UI

CLI details are documented in [cli.md](./cli.md).
