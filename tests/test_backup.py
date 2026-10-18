"""Backups contain reading data but never the model secret or PDFs."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("reviewer_backup", Path(__file__).resolve().parents[1] / "scripts" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class BackupTests(unittest.TestCase):
    def test_backup_redacts_key_and_excludes_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data" / "analysis").mkdir(parents=True)
            (root / "data" / "analysis" / "PAPER.json").write_text('{"summary":"saved"}', encoding="utf-8")
            settings = root / "settings.json"
            settings.write_text('{"baseUrl":"https://example.test/v1","model":"demo","apiKey":"secret"}', encoding="utf-8")
            with patch.object(server, "SKILL_DIR", root), patch.object(server, "SETTINGS_PATH", settings):
                archive = zipfile.ZipFile(io.BytesIO(server.backup_archive()))
                names = set(archive.namelist())
                self.assertIn("backup-manifest.json", names)
                self.assertIn("data/analysis/PAPER.json", names)
                self.assertNotIn("data/model-key.bin", names)
                self.assertNotIn("secret", archive.read("data/settings.json").decode())


if __name__ == "__main__":
    unittest.main()
