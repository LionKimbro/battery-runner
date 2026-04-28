# Battery Runner Introduction

Battery Runner is a small local host for Python behavior processes, or "bprocs."

A bproc is just a folder with some files in it, especially a `code.py` file that defines a nullary `tick()` function and imports `batteryrunner.bproc_context`. Battery Runner installs these bprocs from a drop folder, keeps their state on disk, schedules them, and gives you a Tkinter UI to turn them on and off, edit them, run them immediately, and inspect errors.

For the full docs index, see [index.md](./index.md).

## What Battery Runner Does

Battery Runner currently provides:

- a `.batteryrunner/` project runtime directory
- a `drop/` folder where new bprocs can be placed
- a `brprocs/` folder where installed bprocs live
- a `brprocs-inventory.json` index of installed bprocs
- a scheduler that runs enabled bprocs when they are due
- a Tkinter UI for managing bprocs
- a CLI for scanning, ticking, listing, and opening the UI
- an active `inbox/` intake directory and a reserved `outbox/` directory

Battery Runner does not currently do Patchboard routing, Silk Road courier behavior, or distributed coordination. It only reserves space for those ideas.

## The Core Model

The system is simple:

1. Put a Python file or folder into `.batteryrunner/drop/`.
2. Battery Runner installs it as a new bproc under `.batteryrunner/brprocs/`.
3. The installed bproc gets its own folder, ID, state file, and config file.
4. Battery Runner resets `batteryrunner.bproc_context` and calls `tick()` whenever the bproc is due.
5. Errors are captured into the bproc's state instead of crashing the host.

## Main Runtime Folders

Inside `.batteryrunner/` you will see:

- `brprocs/`
- `brprocs-inventory.json`
- `drop/`
- `inbox/`
- `outbox/`

The broad runtime structure is documented in [internals..md](./internals..md). The structure of an individual installed bproc is documented in [internals_bproc.md](./internals_bproc.md).

## How You Work With It

There are two main ways to use Battery Runner:

- through the Tkinter UI, which is the default mode
- through the CLI, using commands like `battery-runner scan`, `battery-runner tick`, and `battery-runner list`

The CLI is documented in [cli.md](./cli.md).

## Writing Bproc Code

The only required code entrypoint is:

```python
from batteryrunner import bproc_context as ctx


def tick():
    ...
```

Battery Runner provides current time, logging, state/config, and path access through the shared `bproc_context` module. The coding surface for bprocs is documented in [bproc_code.md](./bproc_code.md).

## Where To Go Next

If you want to understand the system quickly:

1. Read [example.md](./example.md)
2. Read [bproc_code.md](./bproc_code.md)
3. Read [internals_bproc.md](./internals_bproc.md)
4. Read [cli.md](./cli.md)
