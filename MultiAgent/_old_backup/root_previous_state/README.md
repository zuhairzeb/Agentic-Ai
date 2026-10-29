# Unified Multi-Agent AI Assistant

The unified multi-agent assistant workspace is located in `unified-multi-agent-assistant/` (and synchronized with `unified_assistant/`).

## Quick Start (Port 8011)

From the project root in PowerShell:

```powershell
cd unified-multi-agent-assistant
$env:DEBUG = "false"
.\.venv\Scripts\python.exe -m chainlit run app.py --port 8011
```

Once started, access the application in your browser at:
**http://localhost:8011**

## Features

- **5 Dedicated Primary Actions:** Write and Rewrite (`/write`), Research (`/research`), Code and Preview (`/code`), Analyze Data (`/analyze`), and Summarize Documents (`/summarize`).
- **Interactive Code Preview:** Two-tab workspace (Preview & Code) with sandboxed iframe, in-browser live source editing, error detection, and downloads (files & ZIP).
- **Verified Document Generation:** Generates real PDF, Microsoft Word (`.docx`), and Markdown documents for resumes and reports with working download buttons.
- **Provider Fallback & Reliability:** Graceful fallback between Gemini and Groq with strict retry limits and non-sensitive diagnostic messages.
- **Persistent SQLite Storage:** Remembers conversations, messages, pinned/archived states, and user memory across browser refreshes and server restarts.
- **Contextual Conversation Options:** Separate menu with Pin/Unpin, Archive/Restore, Rename, Export, and Delete.
