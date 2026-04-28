# Battery Runner Docs

This directory contains generated documentation for the current Battery Runner implementation.

If you are new to the project, start here:

1. [intro.md](./intro.md)
2. [example.md](./example.md)
3. [bproc_code.md](./bproc_code.md)
4. [cli.md](./cli.md)

## Main Articles

- [intro.md](./intro.md)
  General orientation to the system.

- [example.md](./example.md)
  A more realistic example bproc, including how it uses Battery Runner systems.

- [bproc_code.md](./bproc_code.md)
  The `tick()` contract, the `bproc_context` module, logging, JSON helpers, and optional metadata.

- [cli.md](./cli.md)
  The current CLI commands and how they relate to the runtime.

## Guides

- [writing_good_bprocs.md](./writing_good_bprocs.md)
  Practical guidance for writing bprocs that behave well inside Battery Runner.

- [dropoff_recipes.md](./dropoff_recipes.md)
  Several concrete drop-off patterns, from simple scripts to richer folder-based bprocs.

## Internal Reference

- [internals_bproc.md](./internals_bproc.md)
  The contents and file formats of an installed bproc.

- [internals..md](./internals..md)
  The broader runtime layout and top-level system files.
