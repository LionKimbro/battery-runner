# Writing Good Bprocs

Battery Runner lets bprocs be very simple, but a little discipline goes a long way.

This guide is about writing bprocs that are easy to understand, easy to operate, and unlikely to cause trouble in a scheduler-driven host.

For the raw code contract, see [bproc_code.md](./bproc_code.md). For concrete packaged examples, see [dropoff_recipes.md](./dropoff_recipes.md).

## Start With A Small `tick(context)`

Try to keep `tick(context)` short and readable.

Good:

```python
def tick(context):
    data = load_data(context)
    result = build_report(data)
    write_report(context, result)
    context["log"]("report written")
```

Less good:

```python
def tick(context):
    # 150 lines of mixed file I/O, parsing, business logic, and output
    ...
```

Battery Runner does not force a particular style, but readable small functions will make your bprocs easier to debug in the UI.

## Keep Configuration In `config`

Use `state.json["config"]` for user-editable settings.

Good examples:

- names of things to process
- thresholds
- paths relative to the bproc folder
- mode flags
- prompts or templates when they are small

This makes it easy to change behavior through the UI's `Conf` editor without rewriting code.

## Use `bproc_path` For Local Files

If the bproc has support files, keep them in the bproc folder and access them through:

```python
context["bproc_path"]
```

Example:

```python
def tick(context):
    prompt_path = context["bproc_path"] / "prompt.txt"
    prompt = prompt_path.read_text(encoding="utf-8")
    context["log"](f"loaded {prompt_path.name}")
```

This keeps the bproc self-contained.

## Log Useful Things, Not Everything

`context["log"]` is best used for high-value status messages:

- what the bproc decided to do
- what file it wrote
- what important input it used
- whether it skipped work

Good:

```python
context["log"]("no input files found; skipping")
context["log"](f"wrote {output_path.name}")
```

Less good:

- logging every local variable
- logging the same line every few seconds without new information
- logging large blobs of data every run

## Be Friendly To Repeated Runs

Bprocs are scheduled. That means your code may run many times.

Try to make repeated runs harmless:

- overwrite known output files instead of endlessly appending
- check whether work is actually needed
- avoid creating unbounded junk files
- write deterministic outputs when possible

Good example:

```python
def tick(context):
    out_path = context["bproc_path"] / "latest.txt"
    out_path.write_text("fresh result\n", encoding="utf-8")
```

## Fail Clearly

If a bproc fails, Battery Runner captures the exception and traceback.

That means it is okay to raise real exceptions when something is wrong. Prefer failures that are clear and specific.

Good:

```python
def tick(context):
    template_path = context["bproc_path"] / "template.txt"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing template: {template_path.name}")
```

Less good:

- swallowing errors silently
- returning without explanation when something is badly wrong

## Keep External Effects Intentional

A good bproc is easy to reason about.

Prefer:

- reading local files from its own folder
- writing outputs into its own folder
- using `root_path` only when the broader runtime actually matters

Be cautious about:

- writing all over the filesystem
- depending on hidden ambient environment state
- making the meaning of a run depend on undocumented outside files

## Use `name` And `interval_seconds` For A Good First Install

If you provide:

```python
name = "My Bproc"
interval_seconds = 300
```

then the installed bproc starts with a clearer display name and a more sensible initial schedule.

This is especially useful for drop-offs that are meant to feel ready-to-use right away.

## A Good Basic Template

```python
name = "Useful Example"
interval_seconds = 300


def tick(context):
    config = context["config"]
    bproc_path = context["bproc_path"]

    input_path = bproc_path / "input.txt"
    output_path = bproc_path / "output.txt"

    if not input_path.exists():
        context["log"]("input.txt missing; skipping")
        return

    text = input_path.read_text(encoding="utf-8")
    prefix = config.get("prefix", "processed")
    output_path.write_text(f"{prefix}: {text}", encoding="utf-8")
    context["log"](f"wrote {output_path.name}")
```

## Keep The Mental Model Simple

The best bprocs are small local workers:

- they have a clear job
- they keep their important files together
- they log what they did
- they fail clearly when needed
- they remain understandable a month later
