import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from docx import Document
from pypdf import PdfReader

from artifacts import generate_artifacts, save_project, load_project
from app import _parse_project_files, _requested_artifact


class ArtifactTests(unittest.TestCase):
    def test_pdf_and_docx_are_real_nonempty_and_contain_resume_text(self):
        content = "# Alex Example\n\n## Experience\n- Built reliable Python services.\n\n## Education\nBSc Computer Science"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_ARTIFACT_DIR": directory}):
            files = generate_artifacts(content, "thread/../../private", "Alex Example Resume", ("pdf", "docx"))
            self.assertEqual([item.name.rsplit(".", 1)[-1] for item in files], ["pdf", "docx"])
            for item in files:
                self.assertTrue(item.path.is_file())
                self.assertGreater(item.path.stat().st_size, 100)
                self.assertEqual(item.path.parent.parent.resolve(), Path(directory).resolve())
            pdf_text = " ".join(page.extract_text() or "" for page in PdfReader(str(files[0].path)).pages)
            self.assertIn("Alex Example", pdf_text)
            self.assertIn("Python services", pdf_text)
            doc = Document(str(files[1].path))
            docx_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            self.assertIn("Alex Example", docx_text)
            self.assertIn("Python services", docx_text)

    def test_empty_content_does_not_create_an_artifact(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_ARTIFACT_DIR": directory}):
            with self.assertRaises(ValueError):
                generate_artifacts("  ", "thread", formats=("pdf",))
            self.assertEqual(list(Path(directory).rglob("*")), [])

    def test_artifact_detection_requires_a_real_html_code_block(self):
        self.assertEqual(_requested_artifact("Create a website", "```html\n<h1>Hello</h1>\n```"), ("project",))
        self.assertIsNone(_requested_artifact("Create a website", "Here is the preview."))
        self.assertEqual(_requested_artifact("Create my resume", "# Alex\n## Experience\nPython engineer."), ("pdf", "docx"))
        self.assertIsNone(_requested_artifact("Create a resume", "Please provide your work history?"))

    def test_existing_project_revisions_create_files_but_explanations_do_not(self):
        response = "```html filename=index.html\n<form><input required></form>\n```"
        self.assertEqual(_requested_artifact("Add a phone number field", response, has_project=True), ("project",))
        self.assertIsNone(_requested_artifact("How do I add a phone number field?", response, has_project=True))
        self.assertIsNone(_requested_artifact("Explain why this React validation fails", response))

    def test_website_output_is_saved_as_downloadable_html_not_executed(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_ARTIFACT_DIR": directory}):
            result = generate_artifacts("<!doctype html><h1>Generated</h1>", "thread", "website", ("html",))[0]
            self.assertEqual(result.mime, "text/html")
            self.assertEqual(result.path.read_text(encoding="utf-8"), "<!doctype html><h1>Generated</h1>")

    def test_preview_component_uses_an_opaque_sandbox_and_restricts_network(self):
        component = Path(__file__).parents[1] / "public" / "elements" / "CodePreview.jsx"
        source = component.read_text(encoding="utf-8")
        self.assertIn('sandbox="allow-scripts allow-forms"', source)
        self.assertNotIn("allow-same-origin", source)
        self.assertIn("connect-src 'none'", source)
        self.assertIn('role="tab"', source)
        self.assertIn("Refresh preview", source)
        self.assertRegex(source, re.compile(r"generated-preview-error"))

    def test_event_form_request_is_detected_and_named_files_are_parsed(self):
        response = """```html filename=index.html
<form><input name=attendee required><button>Register</button></form>
```\n```css filename=styles.css
form { display: grid; }
```\n```javascript filename=script.js
document.querySelector('form').addEventListener('submit', e => e.preventDefault());
```"""
        self.assertEqual(_requested_artifact("Create a modern Event Registration Form with validation", response), ("project",))
        files = _parse_project_files(response)
        self.assertEqual(set(files), {"index.html", "styles.css", "script.js"})
        self.assertIn("required", files["index.html"])

    def test_project_files_are_persisted_conversation_scoped_and_zipped(self):
        files = {"index.html": "<h1>Registration</h1>", "assets/styles.css": "body { color: teal; }"}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_ARTIFACT_DIR": directory}):
            generated = save_project(files, "thread/../../private", "Event Registration")
            self.assertEqual(load_project("thread/../../private")["files"], files)
            self.assertEqual({item.name for item in generated}, {"index.html", "assets/styles.css", "event-registration.zip"})
            archive = next(item for item in generated if item.mime == "application/zip")
            self.assertGreater(archive.path.stat().st_size, 0)
            with zipfile.ZipFile(archive.path) as project_zip:
                self.assertEqual(set(project_zip.namelist()), set(files))
                self.assertEqual(project_zip.read("index.html").decode(), files["index.html"])
            self.assertTrue(all(item.path.is_file() and item.path.stat().st_size for item in generated))
            with self.assertRaises(ValueError):
                save_project({"../../outside.txt": "no"}, "thread", "Unsafe")


if __name__ == "__main__":
    unittest.main()
