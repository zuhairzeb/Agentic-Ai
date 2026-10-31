import asyncio
import io
import unittest
from openpyxl import Workbook
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from web_app import transcribe_audio, upload_document


class WebUploadTests(unittest.TestCase):
    def test_transcription_uses_configured_whisper_and_language_hint(self):
        file = UploadFile(io.BytesIO(b"recorded audio"), filename="speech.webm", headers={"content-type": "audio/webm"})
        client = unittest.mock.AsyncMock()
        client.audio.transcriptions.create.return_value = SimpleNamespace(text="میں آج کام کر رہا ہوں")
        with patch("web_app.Config", return_value=SimpleNamespace(groq_api_key="test-key")), \
             patch("openai.AsyncOpenAI", return_value=client):
            result = asyncio.run(transcribe_audio(file, language="ur"))
        self.assertEqual(result["text"], "میں آج کام کر رہا ہوں")
        args = client.audio.transcriptions.create.call_args.kwargs
        self.assertEqual(args["model"], "whisper-large-v3")
        self.assertEqual(args["language"], "ur")
        self.assertEqual(args["temperature"], 0)
        client.close.assert_awaited_once()

    def test_transcription_rejects_missing_audio_and_invalid_language(self):
        with patch("web_app.Config", return_value=SimpleNamespace(groq_api_key="test-key")):
            empty = UploadFile(io.BytesIO(b""), filename="speech.webm", headers={"content-type": "audio/webm"})
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(transcribe_audio(empty, language="auto"))
            self.assertEqual(raised.exception.status_code, 400)
            file = UploadFile(io.BytesIO(b"audio"), filename="speech.webm", headers={"content-type": "audio/webm"})
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(transcribe_audio(file, language="fr"))
            self.assertEqual(raised.exception.status_code, 400)

    def test_transcription_requires_server_side_groq_key(self):
        file = UploadFile(io.BytesIO(b"audio"), filename="speech.webm", headers={"content-type": "audio/webm"})
        with patch("web_app.Config", return_value=SimpleNamespace(groq_api_key=None)):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(transcribe_audio(file, language="auto"))
        self.assertEqual(raised.exception.status_code, 503)

    def test_xlsx_upload_extracts_sheet_names_and_cell_values(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Forecast"
        sheet.append(["Quarter", "Revenue"])
        sheet.append(["Q1", 1250])
        content = io.BytesIO()
        workbook.save(content)
        file = UploadFile(io.BytesIO(content.getvalue()), filename="forecast.xlsx")
        result = asyncio.run(upload_document(file))
        self.assertIn("Sheet: Forecast", result["text"])
        self.assertIn("Quarter | Revenue", result["text"])
        self.assertIn("Q1 | 1250", result["text"])

    def test_upload_extracts_text_through_existing_document_tool(self):
        file = UploadFile(io.BytesIO(b"Sociapi meeting notes"), filename="notes.txt")
        tool_result = SimpleNamespace(ok=True, data={"name": "notes.txt", "text": "Sociapi meeting notes", "truncated": False})
        with patch("web_app.tools.execute", new=AsyncMock(return_value=tool_result)) as execute:
            result = asyncio.run(upload_document(file))
        self.assertEqual(result["text"], "Sociapi meeting notes")
        execute.assert_awaited_once()
        self.assertEqual(execute.await_args.args[0], "extract_document")

    def test_upload_rejects_unsupported_file_types(self):
        file = UploadFile(io.BytesIO(b"payload"), filename="payload.exe")
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(upload_document(file))
        self.assertEqual(raised.exception.status_code, 400)

    def test_upload_rejects_files_over_ten_megabytes(self):
        file = UploadFile(io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), filename="large.txt")
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(upload_document(file))
        self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
