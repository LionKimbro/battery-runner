# Drop-Off Recipes

This article gives a few practical patterns for drop-offs you can place into `.batteryrunner/drop/`.

For the system overview, see [intro.md](./intro.md). For the raw bproc contract, see [bproc_code.md](./bproc_code.md). For the structure of installed bprocs, see [internals_bproc.md](./internals_bproc.md).

## Recipe 1: Single Python File

Best when:

- you want the fastest path to a runnable bproc
- the bproc does not need support files

Drop-off:

```text
hello_report.py
```

Example:

```python
name = "Hello Report"
interval_seconds = 60


def tick(context):
    context["log"]("hello from Battery Runner")
```

What happens:

- the file is installed as `code.py`
- a bproc folder is created
- default state/config files are created

## Recipe 2: Script Plus Local Data Files

Best when:

- the bproc needs templates, prompts, or small data files

Drop-off:

```text
message_bot/
  code.py
  template.txt
  names.json
```

Example `code.py`:

```python
name = "Message Bot"
interval_seconds = 300

import json


def tick(context):
    bproc_path = context["bproc_path"]
    template = (bproc_path / "template.txt").read_text(encoding="utf-8").strip()
    names = json.loads((bproc_path / "names.json").read_text(encoding="utf-8"))
    line = template.format(name=names[0], now=context["now"])
    (bproc_path / "message.txt").write_text(line + "\n", encoding="utf-8")
    context["log"]("message.txt updated")
```

Best use:

- self-contained local workers
- file-driven utilities
- prompt/template-driven jobs

## Recipe 3: Folder With `state.json`

Best when:

- you want a dropped bproc to arrive preconfigured
- you want to set schedule or lock behavior immediately

Drop-off:

```text
preconfigured_bot/
  code.py
  state.json
```

Example `state.json`:

```json
{
  "enabled": true,
  "lock_on_error": false,
  "schedule": {
    "mode": "interval",
    "seconds": 900,
    "label": "15 min"
  },
  "config": {
    "target": "daily-notes"
  }
}
```

This is a good pattern when the bproc has a preferred default schedule or important startup config.

## Recipe 4: Folder With `bproc.json` Metadata

Best when:

- you want to include descriptive metadata with the drop-off
- you want a more structured handoff package

Drop-off:

```text
reporter/
  code.py
  bproc.json
```

Example `bproc.json`:

```json
{
  "name": "Reporter",
  "entry": "code.py"
}
```

Battery Runner currently normalizes important fields like ID, short ID, folder, and installation timestamp, so this is best used for descriptive metadata rather than fixed identity.

## Recipe 5: Starter Bundle For Editing In The UI

Best when:

- you want to drop in a rough starting point and refine it afterward
- you expect to use the UI's `Edit` and `Conf` buttons

Drop-off:

```text
draft_worker/
  code.py
  state.json
  notes.md
```

Example `code.py`:

```python
name = "Draft Worker"
interval_seconds = 300


def tick(context):
    context["log"]("draft worker tick")
```

This pattern is useful when the drop-off is really a seed package rather than a finished bproc.

## Choosing A Pattern

Use this rough guide:

- choose Recipe 1 for the smallest runnable thing
- choose Recipe 2 when the bproc needs support files
- choose Recipe 3 when initial config matters
- choose Recipe 4 when metadata packaging matters
- choose Recipe 5 when the UI is part of the authoring workflow
