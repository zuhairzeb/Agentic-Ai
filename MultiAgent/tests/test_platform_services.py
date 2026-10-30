import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mcp_manager import decrypt_secret, encrypt_secret, validate_endpoint
from platform_services import build_skill, read_skill_archive, relevant_skills
from storage import SQLiteStore


class PlatformServiceTests(unittest.TestCase):
    def test_skill_metadata_and_relevance(self):
        skill = build_skill({"SKILL.md": "---\nname: Python Helper\ndescription: Write Python scripts\n---\nUse type hints."}, "manual")
        skill.update({"id": "py", "enabled": True})
        self.assertEqual(skill["name"], "Python Helper")
        self.assertEqual(relevant_skills([skill], "Write a Python script"), [skill])
        self.assertEqual(relevant_skills([skill], "Design a garden"), [])

    def test_skill_zip_reads_inert_skill_markdown_and_rejects_traversal(self):
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("demo/SKILL.md", "# Demo Skill\nUseful instructions")
            archive.writestr("demo/scripts/run.py", "raise SystemExit()")
        skill = read_skill_archive(archive_bytes.getvalue(), "demo.zip")
        self.assertEqual(skill["name"], "Demo Skill")
        self.assertIn("scripts/run.py", skill["resources"])
        unsafe = io.BytesIO()
        with zipfile.ZipFile(unsafe, "w") as archive:
            archive.writestr("../SKILL.md", "# Unsafe")
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            read_skill_archive(unsafe.getvalue(), "unsafe.zip")

    def test_platform_records_persist_and_enable_flags_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "platform.sqlite3")
            store.save_platform_item("local", "skill", "skill-1", {"name": "Test"}, enabled=False)
            reopened = SQLiteStore(Path(directory) / "platform.sqlite3")
            self.assertFalse(reopened.get_platform_item("local", "skill", "skill-1")["enabled"])
            self.assertTrue(reopened.set_platform_item_enabled("local", "skill", "skill-1", True))
            self.assertEqual(reopened.list_platform_items("local", "skill", include_disabled=False)[0]["name"], "Test")

    def test_mcp_credentials_are_encrypted_and_private_targets_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("mcp_manager.SECRET_KEY_PATH", Path(directory) / "secret.key"):
                encrypted = encrypt_secret("private-token")
                self.assertNotIn("private-token", encrypted)
                self.assertEqual(decrypt_secret(encrypted), "private-token")
        self.assertEqual(validate_endpoint("http://localhost:8000/mcp"), "http://localhost:8000/mcp")
        with self.assertRaisesRegex(ValueError, "Private network"):
            validate_endpoint("http://192.168.1.20:8080/mcp")


if __name__ == "__main__":
    unittest.main()
