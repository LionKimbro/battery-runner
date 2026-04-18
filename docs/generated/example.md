# Example Bproc Walkthrough

This article walks through a somewhat richer example than "hello world." It shows a bproc that:

- runs every 5 minutes
- reads a template file from its own folder
- reads configuration from `state.json`
- writes a small report file into its own folder
- logs what it did through `context["log"]`

Along the way, it touches the main Battery Runner systems:

- drop installation
- `code.py` loading
- `state.json` config
- scheduler timing
- runtime logging
- bproc-local file access

For the general system overview, see [intro.md](./intro.md). For the full code contract, see [bproc_code.md](./bproc_code.md). For the internal folder structure, see [internals_bproc.md](./internals_bproc.md).

## Example Drop-Off

Drop this folder into `.batteryrunner/drop/`:

```text
message_reporter/
  code.py
  state.json
  template.txt
```

## `code.py`

```python
name = "Message Reporter"
interval_seconds = 300


def tick(context):
    config = context["config"]
    bproc_path = context["bproc_path"]

    template_path = bproc_path / "template.txt"
    report_path = bproc_path / "last-report.txt"

    template = template_path.read_text(encoding="utf-8").strip()
    subject = config.get("subject", "world")
    line = template.format(subject=subject, now=context["now"])

    report_path.write_text(line + "\n", encoding="utf-8")
    context["log"](f"wrote {report_path.name} for subject={subject!r}")
```

## `state.json`

```json
{
  "enabled": true,
  "lock_on_error": false,
  "schedule": {
    "mode": "interval",
    "seconds": 300,
    "label": "5 min"
  },
  "config": {
    "subject": "battery runner"
  }
}
```

## `template.txt`

```text
Report for {subject} at {now}
```

## What Happens When You Drop It Off

When Battery Runner scans the drop folder:

1. It creates a UUID and short ID for the new bproc.
2. It creates a folder under `.batteryrunner/brprocs/` named like `message_reporter__<shortid>`.
3. It copies the dropped files into that folder.
4. It preserves and normalizes `state.json`.
5. It preserves and normalizes `bproc.json` if one was supplied.
6. It adds the bproc to `brprocs-inventory.json`.
7. It removes the original dropped folder from `drop/`.

The installer details are described in [internals_bproc.md](./internals_bproc.md).

## What The Example Uses

This example relies on several parts of the runtime:

- `interval_seconds = 300`
  Battery Runner reads this at install time and uses it as the default schedule if `state.json` did not already define one.

- `context["config"]`
  This comes from `state.json`, specifically from the `config` object.

- `context["bproc_path"]`
  This is the installed folder for the bproc. The example uses it to read `template.txt` and write `last-report.txt`.

- `context["now"]`
  This is the current timestamp as epoch seconds for the current run.

- `context["log"]`
  This writes a line to Battery Runner's stdout in the form `[short_id] message`.

These runtime details are documented in [bproc_code.md](./bproc_code.md).

## Failure Behavior

This example sets:

```json
"lock_on_error": false
```

That means if `tick(context)` raises an exception, Battery Runner will:

- store the error message and traceback in runtime state
- increment `error_count`
- disable the bproc

If `lock_on_error` were `true`, Battery Runner would keep the bproc enabled after the error.

## How To Control It

You can:

- drop the folder in and let the UI pick it up
- run `battery-runner scan`
- run `battery-runner tick`
- open the UI and change enable/lock/schedule settings
- edit code and config through the UI

For command details, see [cli.md](./cli.md).
