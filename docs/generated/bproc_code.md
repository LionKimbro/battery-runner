# Bproc Code

Battery Runner runs Python bprocs by importing an installed `code.py` file and calling its `tick(context)` function.

## Required Function

The required entrypoint is:

```python
def tick(context):
    ...
```

Battery Runner expects the module to define `tick`. If `tick` is missing, the run fails and the error is recorded in the bproc state.

There is no second required function, no class requirement, and no registration API.

## Optional Top-Level Metadata

Battery Runner currently looks for these optional top-level assignments in `code.py` when the bproc is installed:

```python
name = "Some Friendly Name"
interval_seconds = 300
```

### `name`

If present, `name` is used as the display name for the bproc.

Battery Runner now rescans this dynamically when `code.py` changes, so editing the file can update the displayed bproc name without reinstalling the bproc.

### `interval_seconds`

If present, `interval_seconds` is used as the bproc interval schedule.

Battery Runner now rescans this dynamically when `code.py` changes. If the value changes, Battery Runner updates:

- `state["schedule"]["seconds"]`
- `state["schedule"]["label"]`
- `state["runtime"]["next_run"]`

The new `next_run` is recalculated from `last_run` using the new interval.

## The `context` Passed To `tick`

Battery Runner passes a plain dictionary into `tick(context)`.

Current keys are:

- `context["now"]`
- `context["log"]`
- `context["state"]`
- `context["config"]`
- `context["root_path"]`
- `context["bproc_path"]`

## `context["now"]`

`context["now"]` is the current timestamp as an integer number of seconds since the Unix epoch.

Example:

```python
def tick(context):
    print(context["now"])
```

## `context["log"]`

`context["log"]` is a callable you can use like this:

```python
def tick(context):
    context["log"]("starting work")
```

Battery Runner currently implements it as a simple stdout logger. A call like:

```python
context["log"]("starting work")
```

produces something like:

```text
[abc123def456] starting work
```

Use `context["log"]` for progress notes, status messages, and simple diagnostics that should show up in the host output.

Battery Runner also appends each log call to the bproc's `log.jsonl` file as a JSON object with:

- `timestamp`
- `message`

## `context["state"]`

`context["state"]` is the full persisted state object for the bproc.

It includes:

- enable/disable state
- schedule info
- lock-on-error behavior
- runtime tracking such as last run and last error
- the `config` object

In practice, bproc code should usually treat this as readable state, not as a direct persistence API. Battery Runner currently persists state before and after runs, but it does not provide a special transactional write API for mutating arbitrary nested values during `tick`.

Current top-level shape:

```python
{
    "id": str,
    "enabled": bool,
    "schedule": dict,
    "lock_on_error": bool,
    "runtime": dict,
    "config": dict,
}
```

### `context["state"]` Top-Level Keys

- `id`
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

### `context["state"]["schedule"]`

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

### `context["state"]["runtime"]`

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

### `context["state"]["runtime"]["last_error"]`

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

## `context["config"]`

`context["config"]` is just:

```python
context["state"]["config"]
```

It is provided as a convenience.

This is the main place for user-editable bproc configuration. The UI's `Conf` button edits this object as JSON.

Example:

```python
def tick(context):
    city = context["config"].get("city", "Portland")
    context["log"](f"city={city}")
```

## `context["root_path"]`

`context["root_path"]` is a `pathlib.Path`.

It points to the Battery Runner runtime root, usually:

```text
.batteryrunner/
```

You can use it to reach shared runtime areas like `inbox/` or `outbox/`, though Battery Runner itself does not currently implement message routing behavior there.

## `context["bproc_path"]`

`context["bproc_path"]` is a `pathlib.Path`.

It is the installed folder for the current bproc.

This is the main place to read bproc-local files or write bproc-local outputs.

Example:

```python
def tick(context):
    path = context["bproc_path"] / "data.txt"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        context["log"](text.strip())
```

## Minimal Example

```python
def tick(context):
    context["log"]("tick")
```

## Slightly Richer Example

```python
name = "Counter"
interval_seconds = 60


def tick(context):
    config = context["config"]
    value = config.get("value", 0)
    context["log"](f"value={value}")
```

## Support Files

Your `code.py` can make use of other files in the bproc folder. For example:

- templates
- JSON data files
- prompt files
- small local caches

Battery Runner will copy these files during installation if they were in the dropped folder.

## Error Behavior

If `tick(context)` raises an exception:

- the traceback is captured
- the error message is stored in runtime state
- `error_count` is incremented
- if `lock_on_error` is `false`, the bproc is disabled
- if `lock_on_error` is `true`, the bproc stays enabled

For the bproc folder and state file structure, see [internals_bproc.md](./internals_bproc.md).
