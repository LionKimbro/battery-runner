# Battery Runner CLI

Battery Runner installs a console command named:

```text
battery-runner
```

This is the command currently implemented by the package.

If you were expecting `battery-proc`, note that the actual command in the current implementation is `battery-runner`.

## Commands

Battery Runner currently supports:

- `battery-runner`
- `battery-runner ui`
- `battery-runner scan`
- `battery-runner tick`
- `battery-runner list`

## `battery-runner`

Running `battery-runner` with no command opens the Tkinter UI.

This is the default command behavior.

## `battery-runner ui`

Also opens the Tkinter UI.

Use this when you want to be explicit.

## `battery-runner scan`

Scans `.batteryrunner/drop/`, installs any new dropped bprocs, and prints a JSON summary.

Example output shape:

```json
{
  "installed": 1,
  "brprocs": [
    {
      "short_id": "abc123def456",
      "name": "sample",
      "folder": "sample__abc123def456"
    }
  ]
}
```

## `battery-runner tick`

Runs one scheduler pass without opening the UI.

This does two things:

- processes the drop folder
- runs every installed bproc that is currently due

It then prints a JSON summary of what ran.

## `battery-runner list`

Prints the installed bprocs and their current runtime summary as JSON.

This includes fields such as:

- `enabled`
- `lock_on_error`
- `schedule_seconds`
- `schedule_label`
- `last_run`
- `next_run`
- `last_error`

## CLI Behavior Notes

The CLI is intentionally small right now. It does not currently provide commands for:

- deleting a bproc
- forcing a single named bproc to run from the CLI
- editing config from the CLI
- editing code from the CLI

Those operations are currently handled through the UI.

## `--execroot`

Because Battery Runner is built on `lionscliapp`, you can use `--execroot` to point the runtime at a different execution root.

Example:

```powershell
battery-runner --execroot F:\some\other\project list
```

That makes Battery Runner operate against:

```text
F:\some\other\project\.batteryrunner\
```

## Relationship To The UI

The CLI and UI operate on the same runtime files.

- `scan` installs drop-offs
- `tick` advances the scheduler
- `list` shows current state
- `ui` opens the graphical control surface

For the broader runtime structure, see [internals..md](./internals..md).
