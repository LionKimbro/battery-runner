```
document-id: battery-runner.reconstruction-implementation-plan.v1
title: Battery Runner Reconstruction Implementation Plan
date: 2026-07-16
document-type: implementation-plan
supersedes:
superseded-by:
```

# Battery Runner Reconstruction Implementation Plan

## Current Repository Map

Battery Runner is currently a small `src`-layout Python package named `batteryrunner`.

Important files:

- `src/batteryrunner/cli.py` declares the `battery-runner` command with `ui`, `scan`, `tick`, and `list`.
- `src/batteryrunner/storage.py` owns runtime folders, intake installation, inventory, `bproc.json`, and combined `state.json`.
- `src/batteryrunner/runner.py` owns due checks, in-process bproc imports, module caching, runtime updates, and error capture.
- `src/batteryrunner/bproc_context.py` exposes the active run context to bproc code.
- `src/batteryrunner/ui.py` owns the Tkinter management UI and currently runs a background scheduler worker.
- `src/batteryrunner/util.py` owns JSON, timestamp, slug, hash, and schedule helpers.

There is no `tests/` directory yet. The current runtime sample under `.batteryrunner/` shows the old installed layout:

```text
.batteryrunner/
  brprocs-inventory.json
  brprocs/
    test__3b8337895a2f/
      bproc.json
      code.py
      state.json
      log.jsonl
```

The old `state.json` combines user settings, bproc config, and runner runtime:

```json
{
  "uuid": "...",
  "enabled": true,
  "schedule": {"mode": "interval", "seconds": 15, "label": "15 sec"},
  "lock_on_error": true,
  "runtime": {"running": false, "last_run": 1784224871},
  "config": {}
}
```

## Current Behavior And Ownership

Current useful behavior to preserve:

- Drop-folder installation supports a `.py` file or a folder.
- `battery-runner scan`, `tick`, and `list` already run without opening Tkinter.
- The UI can create, edit, run, enable, disable, reschedule, inspect errors, and inspect logs.
- Bproc code has a simple nullary `tick()` contract.
- Per-bproc logs are JSONL.
- Atomic JSON writes are already used.

Current architecture to change:

- `state.json` mixes settings, bproc config, and runtime.
- Top-level source metadata `name` and `interval_seconds` can rewrite installed settings after source edits.
- The UI worker acts like the continuous scheduler.
- Bprocs are imported directly into the long-running runner process.
- `lock_on_error` has counterintuitive semantics.
- There is no formal migration path or tests.
- The UI imports core runner modules and runs scheduling in a worker thread instead of being only a control surface.

## Target File Model

Installed bprocs should move toward this shape:

```text
.batteryrunner/
  brprocs/
    message_reporter__abc123/
      code.py
      settings.json
      data.json
      runtime.json
      log.jsonl
      ...support files...
```

Ownership:

- `settings.json`: durable, user/UI controlled.
- `settings.json["config"]`: durable, user/UI controlled bproc configuration.
- `data.json`: durable, bproc controlled.
- `runtime.json`: durable, Battery Runner controlled.
- `log.jsonl`: durable append-only per-bproc log.
- other bproc-local files: durable and bproc controlled.
- process memory: in RAM only, explicitly temporary.
- active run context: in RAM for one invocation only.

## Staged Implementation

### Stage 1: Persistence Model And Compatibility Reads

Create storage helpers for `settings.json`, `data.json`, and `runtime.json`.

Keep old `state.json` reads as compatibility input. When new files are missing and `state.json` exists, expose a normalized in-memory record with:

- `record["settings"]`
- `record["data"]`
- `record["runtime"]`
- compatibility `record["state"]` only where old callers still need it during transition

Do not delete `state.json` in this stage.

### Stage 2: Explicit Migration

Add an explicit migration command. It should:

- create a backup before changing files,
- split old `state.json` into `settings.json`, `data.json`, and `runtime.json`,
- preserve unknown old keys in a migration compatibility section,
- be safe to run more than once,
- log migration actions.

### Stage 3: Installation Defaults

Replace authored `name` and `interval_seconds` as the preferred convention with:

```python
bproc_defaults = {
    "name": "Example",
    "interval_seconds": 300,
}
```

At install time only, normalize defaults into installed `settings.json`.

Keep `name`, `interval_seconds`, `uuid`, and `id` as compatibility metadata during import, but do not let source edits silently rewrite installed settings.

### Stage 4: Context API

Update `bproc_context` around the new persistence model:

- `get_settings()`
- `get_config()`
- `get_data()`
- `save_data()`
- `get_runtime()`
- `get_process_memory()`

Keep short compatibility aliases where useful:

- `get_state()` can return a compatibility object during transition.
- `get_shared()` can point to process memory but should be documented as temporary.

### Stage 5: CLI Shape

Add commands:

- `serve`
- `run <id-or-name>`
- `migrate`

Keep:

- default command opens UI,
- `ui`,
- `scan`,
- `tick`,
- `list`.

Use human-readable output for `list` by default later, but JSON output may remain during the early migration stage if it keeps the project runnable.

### Stage 6: Headless Runner

Move continuous scheduling into a headless `serve` command that imports no Tkinter UI code.

The UI should become an observer/control surface. It may still poll files and issue explicit run/control operations, but scheduled execution should not require the UI.

### Stage 7: Execution Boundary

Inspect and then replace direct in-process bproc execution with a simple child-process boundary.

Minimum desired behavior:

- exception containment,
- stdout/stderr capture,
- timeout path,
- host survives bproc hard exits,
- clear runtime result persisted in `runtime.json`.

If full subprocess execution is deferred, document the exact remaining limitation and keep the runner API shaped so execution can be swapped.

### Stage 8: UI Red-Carpet Surface

Rework the Tkinter UI around selected-bproc inspection:

- source,
- settings,
- data,
- runtime,
- files,
- log,
- process-memory lifetime note.

Use TkVillage for the rebuilt UI window structure, with reducer-owned state, queued semantic events, and projection.

### Stage 9: Documentation

Rewrite the README and generated docs around:

- minimal bproc,
- drop folder,
- `scan`, `tick`, `serve`, `ui`, `list`, `run`,
- persistence guide,
- authoring guide,
- migration guide,
- architecture guide.

### Stage 10: Tests

Add focused tests as each stage lands.

Start with:

- single `.py` install,
- folder install,
- `bproc_defaults`,
- defaults do not rewrite settings after install,
- split persistence files,
- context data persistence,
- manual run,
- due-time calculations,
- malformed defaults,
- migration from old `state.json`,
- core imports without Tkinter.

## First Code Changes To Make

The safest first implementation pass is:

1. Introduce new persistence helpers while preserving existing callers.
2. Change new installs and manual creation to write `settings.json`, `data.json`, and `runtime.json`.
3. Make `load_bproc_record()` normalize old and new layouts into one record shape.
4. Update runner and context to use the new shape.
5. Add `run` and `serve` CLI commands.
6. Add tests for install, defaults authority, data persistence, and manual run.

This pass should leave the existing UI usable through compatibility fields while preparing the later TkVillage rebuild.
