# Bproc Code

Battery Runner runs Python bprocs by importing an installed `code.py` file, resetting the shared `batteryrunner.bproc_context` module for that run, and then calling a nullary `tick()` function.

## Required Shape

The preferred authored pattern is:

```python
from batteryrunner import bproc_context as ctx


def tick():
    ...
```

Battery Runner expects the module to define `tick`. There is no class requirement, no registration API, and no positional `context` argument.

## Optional Top-Level Metadata

Battery Runner currently looks for these optional top-level assignments in `code.py`:

```python
uuid = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
name = "Some Friendly Name"
interval_seconds = 300
```

Battery Runner accepts legacy `id = "..."` on import for compatibility, but `uuid` is the preferred authored name going forward.

### `name`

If present, `name` is used as the display name for the bproc.

Battery Runner rescans this dynamically when `code.py` changes, so editing the file can update the displayed bproc name without reinstalling the bproc.

### `interval_seconds`

If present, `interval_seconds` is used as the bproc interval schedule.

Battery Runner rescans this dynamically when `code.py` changes. If the value changes, Battery Runner updates:

- `state["schedule"]["seconds"]`
- `state["schedule"]["label"]`
- `state["runtime"]["next_run"]`

The new `next_run` is recalculated from `last_run` using the new interval.

## The `bproc_context` Module

Import it like this:

```python
from batteryrunner import bproc_context as ctx
```

Battery Runner resets this module before each run, loads the current bproc's data into it, and clears it again after the run.

One part of the module is intentionally not cleared between bproc runs: shared in-memory state returned by `ctx.get_shared()`. That shared dictionary lives for as long as the Battery Runner process stays alive, and it is reset only when Battery Runner exits, dies, or when code explicitly calls `ctx.clear(reset_shared=True)`.

Current API:

- `ctx.get_now()`
- `ctx.get_uuid()`
- `ctx.get_name()`
- `ctx.get_state()`
- `ctx.get_config()`
- `ctx.get_shared()`
- `ctx.get_runtime()`
- `ctx.get_schedule()`
- `ctx.get_root_path()`
- `ctx.get_bproc_path()`
- `ctx.log(message)`
- `ctx.resolve_path(path)`
- `ctx.load_json(path)`
- `ctx.save_json(path, obj)`
- `ctx.reset(d)`
- `ctx.clear(reset_shared=False)`

## `ctx.get_now()`

Returns the current timestamp as an integer number of seconds since the Unix epoch.

Example:

```python
from batteryrunner import bproc_context as ctx


def tick():
    print(ctx.get_now())
```

## `ctx.log(message)`

`ctx.log(message)` posts a log message to stdout and to the bproc's `log.jsonl`.

Example:

```python
from batteryrunner import bproc_context as ctx


def tick():
    ctx.log("starting work")
```

Current `log.jsonl` entry shape:

```json
{
  "timestamp": 1777357063,
  "bproc_uuid": "e6741066-2bb9-4adf-ab0c-8723cbe786c0",
  "bproc_name": "sign-maker",
  "message": "starting work"
}
```

`bproc_uuid` is the authoritative identity. `bproc_name` is included as a convenient projection for humans reading the file.

## `ctx.get_state()`

Returns the full persisted state object for the bproc.

Current top-level shape:

```python
{
    "uuid": str,
    "enabled": bool,
    "schedule": dict,
    "lock_on_error": bool,
    "runtime": dict,
    "config": dict,
}
```

### `ctx.get_state()` Top-Level Keys

- `uuid`
  Type: `str`
  The full UUID string for this bproc.

- `enabled`
  Type: `bool`
  Whether the scheduler should run this bproc.

- `schedule`
  Type: `dict`
  Scheduling configuration for the bproc.

- `lock_on_error`
  Type: `bool`
  If `True`, an error does not disable the bproc. If `False`, an error disables it.

- `runtime`
  Type: `dict`
  Runtime bookkeeping fields such as last run, next run, and error tracking.

- `config`
  Type: `dict`
  User-editable configuration object for the bproc.

## `ctx.get_schedule()`

This is the same object as:

```python
ctx.get_state()["schedule"]
```

Current keys:

- `mode`
  Type: `str`
  The schedule mode. In the current implementation this is `"interval"`.

- `seconds`
  Type: `int`
  The run interval in seconds.

- `label`
  Type: `str`
  A human-facing schedule label used in the UI, such as `"5 min"` or `"1 hour"`.

## `ctx.get_runtime()`

This is the same object as:

```python
ctx.get_state()["runtime"]
```

Current keys:

- `running`
  Type: `bool`
  Whether the bproc is currently marked as running.

- `last_run`
  Type: `int | None`
  Epoch-seconds timestamp of the last attempted run, or `None` if it has never run.

- `next_run`
  Type: `int | None`
  Epoch-seconds timestamp of the next scheduled run, or `None` if unset.

- `last_success`
  Type: `int | None`
  Epoch-seconds timestamp of the last successful run, or `None` if there has not been one yet.

- `last_error`
  Type: `dict`
  Information about the most recent error.

- `error_count`
  Type: `int`
  Count of how many failures have been recorded for this bproc.

### `ctx.get_runtime()["last_error"]`

Current keys:

- `timestamp`
  Type: `int | None`
  Epoch-seconds timestamp of the most recent error, or `None` if there is no recorded error.

- `message`
  Type: `str | None`
  The exception message from the most recent error, or `None`.

- `traceback`
  Type: `str | None`
  The stored traceback text from the most recent error, or `None`.

## `ctx.get_config()`

This is just:

```python
ctx.get_state()["config"]
```

It is provided as a convenience.

Example:

```python
from batteryrunner import bproc_context as ctx


def tick():
    city = ctx.get_config().get("city", "Portland")
    ctx.log(f"city={city}")
```

## `ctx.get_shared()`

Returns a plain dictionary shared across all bprocs in the current Battery Runner process.

This is process-memory only:

- it is not written to disk
- it is not cleared between bproc runs
- it is reset when Battery Runner exits or crashes
- it can also be cleared explicitly with `ctx.clear(reset_shared=True)`

Example:

```python
from batteryrunner import bproc_context as ctx


def tick():
    shared = ctx.get_shared()
    shared["run_count"] = shared.get("run_count", 0) + 1
    ctx.log(f"shared run_count={shared['run_count']}")
```

## `ctx.get_root_path()`

Returns a `pathlib.Path` pointing to the Battery Runner runtime root, usually:

```text
.batteryrunner/
```

## `ctx.get_bproc_path()`

Returns a `pathlib.Path` pointing to the installed folder for the current bproc.

This is the main place to read bproc-local files or write bproc-local outputs.

Example:

```python
from batteryrunner import bproc_context as ctx


def tick():
    path = ctx.get_bproc_path() / "data.txt"
    if path.exists():
        ctx.log(path.read_text(encoding="utf-8").strip())
```

## `ctx.resolve_path(path)`

Returns a `pathlib.Path`.

If the incoming path is absolute, it is returned as-is. If it is relative, it is resolved from the current bproc folder.

## `ctx.load_json(path)`

Loads JSON from either an absolute path or a path relative to the bproc folder.

When JSON is malformed, Battery Runner raises a standardized `JsonLoadError` that includes:

- the resolved path
- the decoder's line number
- the decoder's column number
- the decode error message

Example error shape:

```text
JSON decode error in F:\...\settings.json at line 12, column 7: Expecting ',' delimiter
```

Example:

```python
from batteryrunner import bproc_context as ctx


def tick():
    settings = ctx.load_json("settings.json")
    ctx.log(f"loaded {settings!r}")
```

## `ctx.save_json(path, obj)`

Saves JSON to either an absolute path or a path relative to the bproc folder.

Battery Runner writes UTF-8 JSON with a trailing newline.

Example:

```python
from batteryrunner import bproc_context as ctx


def tick():
    payload = {"now": ctx.get_now()}
    ctx.save_json("latest.json", payload)
    ctx.log("latest.json updated")
```

## `ctx.reset(d)` and `ctx.clear(...)`

Battery Runner itself uses these lifecycle helpers around each run.

- `ctx.reset(d)` replaces the active per-run payload and preserves shared memory
- `ctx.clear()` clears the active per-run payload and preserves shared memory
- `ctx.clear(reset_shared=True)` clears both the per-run payload and the shared dictionary

Ordinary bproc code will usually use the getter functions instead of calling these directly.

## Minimal Example

```python
from batteryrunner import bproc_context as ctx


def tick():
    ctx.log("tick")
```

## Slightly Richer Example

```python
from batteryrunner import bproc_context as ctx

name = "Counter"
interval_seconds = 60


def tick():
    config = ctx.get_config()
    value = config.get("value", 0)
    ctx.log(f"value={value}")
```

## Error Behavior

If `tick()` raises an exception:

- the traceback is captured
- the error message is stored in runtime state
- `error_count` is incremented
- if `lock_on_error` is `false`, the bproc is disabled
- if `lock_on_error` is `true`, the bproc stays enabled

For the bproc folder and state file structure, see [internals_bproc.md](./internals_bproc.md).
