# -*- coding: utf-8 -*-
"""Tests for ha4t.include() — the runtime case-reuse helper used by editor
include steps. Verifies file resolution, caller-globals sharing, boilerplate
stripping, missing-file errors, and circular-include detection."""

import os
import textwrap
import unittest

from ha4t import include


class TestInclude(unittest.TestCase):
    def setUp(self):
        self.tmpdir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "_include_fixtures")
        )
        os.makedirs(self.tmpdir, exist_ok=True)

    def tearDown(self):
        # remove all generated fixture files (but keep dir for next run)
        for name in os.listdir(self.tmpdir):
            try:
                os.remove(os.path.join(self.tmpdir, name))
            except OSError:
                pass

    def _write(self, name, body):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(body))
        return path

    def test_shares_caller_globals(self):
        """include()'d file sees the caller's `dev` symbol."""
        self._write("sub.py", """
            dev.click(text="hello")
        """)
        calls = []

        class FakeDev:
            def click(self, **kwargs):
                calls.append(kwargs)

        # caller's globals must contain `dev` and we cwd into fixture dir
        cwd = os.getcwd()
        os.chdir(self.tmpdir)
        try:
            dev = FakeDev()  # noqa: F841 — referenced by sub.py via globals
            include("sub.py")
        finally:
            os.chdir(cwd)

        self.assertEqual(calls, [{"text": "hello"}])

    def test_strips_boilerplate(self):
        """`dev = connect(...)` / ha4t imports inside the include are skipped
        so the caller's `dev` is reused (no fresh connection attempt)."""
        self._write("sub.py", """
            import os
            os.environ["FLAGS_use_mkldnn"] = "0"
            from ha4t import connect, include
            from time import sleep
            dev = connect(platform="android", device_serial="should-not-run")
            dev.press("home")
        """)
        calls = []

        class FakeDev:
            def press(self, key):
                calls.append(key)

        cwd = os.getcwd()
        os.chdir(self.tmpdir)
        try:
            dev = FakeDev()  # noqa: F841
            include("sub.py")
        finally:
            os.chdir(cwd)

        # If `dev = connect(...)` were NOT stripped, FakeDev would be replaced
        # and .press would fail or hit a real connect attempt.
        self.assertEqual(calls, ["home"])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            include("__definitely_does_not_exist__.py")

    def test_circular_include_detected(self):
        """a.py includes b.py which includes a.py → RuntimeError, not stack
        overflow."""
        self._write("a.py", """
            include("b.py")
        """)
        self._write("b.py", """
            include("a.py")
        """)
        cwd = os.getcwd()
        os.chdir(self.tmpdir)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                include("a.py")
            self.assertIn("循环引用", str(ctx.exception))
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
