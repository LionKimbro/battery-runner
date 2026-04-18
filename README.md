# battery-runner

Battery Runner is a small Tkinter host for filesystem-backed Python bprocs.

Documentation entry point:

- [docs/generated/index.md](F:/lion/github/battery-runner/docs/generated/index.md)

Install for local development with:

```powershell
python -m pip install -e .
```

Run it with:

```powershell
battery-runner
```

Useful commands:

```powershell
python -m batteryrunner list
python -m batteryrunner scan
python -m batteryrunner tick
```

Runtime files live under `.batteryrunner/`:

- `brprocs/` installed bprocs
- `brprocs-inventory.json` installed inventory
- `drop/` files or folders to install
- `inbox/` reserved future message surface
- `outbox/` reserved future message surface
