"""Project-local PDF tools take precedence without altering user settings."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('poppler_runtime', Path(__file__).resolve().parents[1] / 'scripts/poppler_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class PopplerRuntimeTests(unittest.TestCase):
    def test_missing_or_incomplete_runtime_preserves_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PATH': 'existing'}):
            root = Path(tmp)
            self.assertIsNone(runtime.configure(root))
            directory = root / 'vendor/poppler/runtime/Library/bin'
            directory.mkdir(parents=True)
            (directory / 'pdfinfo.exe').touch()
            self.assertIsNone(runtime.configure(root))
            self.assertEqual(os.environ['PATH'], 'existing')

    def test_local_tools_are_preferred_and_added_only_once(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PATH': 'existing'}):
            root = Path(tmp)
            directory = root / 'vendor/poppler/runtime/poppler/Library/bin'
            directory.mkdir(parents=True)
            for name in ('pdfinfo.exe', 'pdftoppm.exe'):
                (directory / name).touch()
            self.assertEqual(runtime.configure(root), directory)
            runtime.configure(root)
            self.assertEqual(os.environ['PATH'].split(os.pathsep), [str(directory), 'existing'])


if __name__ == '__main__':
    unittest.main()
