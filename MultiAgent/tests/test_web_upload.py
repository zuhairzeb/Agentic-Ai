import asyncio
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from web_app import upload_document


class WebUploadTests(unittest.TestCase):
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
