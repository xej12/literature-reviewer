"""Demo mode remains isolated from Zotero and model configuration."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("reviewer_demo", Path(__file__).resolve().parents[1] / "scripts" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class DemoStoreTests(unittest.TestCase):
    def test_demo_library_uses_only_bundled_pdf(self):
        store = server.DemoStore()
        self.assertTrue(store.demo)
        self.assertIsNone(store.data_dir)
        result = store.library()
        self.assertEqual(result["demo"], True)
        self.assertEqual(result["itemCount"], 1)
        self.assertEqual(result["items"][0]["key"], "DEMO01")
        self.assertEqual(result["items"][0]["attachments"][0]["key"], "DEMOPDF")
        self.assertTrue(server.DemoStore().attachment_path("DEMOPDF").is_file())

    def test_demo_attachment_is_explicitly_unavailable(self):
        with self.assertRaisesRegex(FileNotFoundError, "示例模式没有这份 PDF"):
            server.DemoStore().attachment_path("DEMO-PDF")


if __name__ == "__main__":
    unittest.main()
