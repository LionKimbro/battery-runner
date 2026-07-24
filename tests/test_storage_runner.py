from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from batteryrunner import bproc_context, runner, storage


class BatteryRunnerStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".batteryrunner"
        self.root_patch = mock.patch.object(storage, "get_runtime_root", lambda: self.root)
        self.root_patch.start()
        runner.g["module_cache"].clear()
        bproc_context.clear(reset_shared=True)
        storage.ensure_runtime_layout()

    def tearDown(self):
        bproc_context.clear(reset_shared=True)
        runner.g["module_cache"].clear()
        self.root_patch.stop()
        self.tmp.cleanup()

    def write_drop_file(self, name: str, text: str) -> Path:
        path = storage.get_drop_root() / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def test_installs_single_file_with_bproc_defaults(self):
        self.write_drop_file(
            "hello.py",
            """
from batteryrunner import bproc_context as ctx

bproc_defaults = {
    "name": "Hello Runner",
    "interval_seconds": 300,
    "config": {"subject": "battery"},
}

def tick():
    ctx.log("hello")
""".lstrip(),
        )

        installed = storage.process_intake()

        self.assertEqual(1, len(installed))
        record = installed[0]
        folder = record["folder_path"]
        self.assertTrue((folder / "settings.json").exists())
        self.assertTrue((folder / "data.json").exists())
        self.assertTrue((folder / "runtime.json").exists())
        self.assertEqual("Hello Runner", record["settings"]["name"])
        self.assertEqual(300, record["settings"]["schedule"]["seconds"])
        self.assertEqual({"subject": "battery"}, record["settings"]["config"])

    def test_source_default_edits_do_not_rewrite_installed_settings(self):
        self.write_drop_file(
            "hello.py",
            """
bproc_defaults = {"name": "Original", "interval_seconds": 300}

def tick():
    pass
""".lstrip(),
        )
        record = storage.process_intake()[0]
        code_path = record["folder_path"] / "code.py"
        code_path.write_text(
            """
bproc_defaults = {"name": "Changed", "interval_seconds": 1}

def tick():
    pass
""".lstrip(),
            encoding="utf-8",
            newline="\n",
        )

        refreshed = storage.load_bproc_record(record["short_id"])

        self.assertEqual("Original", refreshed["settings"]["name"])
        self.assertEqual(300, refreshed["settings"]["schedule"]["seconds"])

    def test_bproc_data_persists_when_saved(self):
        self.write_drop_file(
            "counter.py",
            """
from batteryrunner import bproc_context as ctx

bproc_defaults = {"name": "Counter", "interval_seconds": 60}

def tick():
    data = ctx.get_data()
    data["count"] = data.get("count", 0) + 1
    ctx.save_data()
""".lstrip(),
        )
        record = storage.process_intake()[0]

        runner.run_bproc_now(record["short_id"])
        runner.run_bproc_now(record["short_id"])
        refreshed = storage.load_bproc_record(record["short_id"])

        self.assertEqual({"count": 2}, refreshed["data"])

    def test_old_state_layout_loads_as_split_record(self):
        record = storage.create_bproc("Old Shape", 15, True)
        folder = record["folder_path"]
        (folder / "settings.json").unlink()
        (folder / "runtime.json").unlink()
        (folder / "data.json").unlink()

        refreshed = storage.load_bproc_record(record["short_id"])

        self.assertEqual("Old Shape", refreshed["settings"]["name"])
        self.assertEqual(15, refreshed["settings"]["schedule"]["seconds"])
        self.assertFalse(refreshed["settings"]["disable_on_error"])
        self.assertIn("last_run", refreshed["runtime"])
        self.assertEqual({}, refreshed["data"])


if __name__ == "__main__":
    unittest.main()
