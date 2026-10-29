# Unified Multi Agent Assistant

This folder contains the single Chainlit app. General questions, specialist tasks, safe calculations, document summaries, and code previews all run through the same `app.py`.

## Install

Use Python 3.10 or newer. In PowerShell, from this folder, install the dependencies into the included virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Add your provider keys to `.env`. Gemini is used for math, writing, and research; Groq is used for general questions and Agent 1/Agent 2. `.env.example` lists the supported settings. The optional `list_models.py` utility also uses `OPENAI_API_KEY`.

## Run

From the MultiAgent folder, start the only app with this one PowerShell command:

```powershell
$env:DEBUG = "false"; .\.venv\Scripts\python.exe -m chainlit run app.py
```

Open the local address printed by Chainlit. Do not run an `app.py` from a backup folder.

## What it includes

- Automatic routing to general, math, writing, or research responses, with Agent 1 and Agent 2 available explicitly.
- Streaming, bounded request execution, a safe calculator, provider fallback, and response settings.
- A native function-calling loop for math tasks: the model can call registered tools, receive their results, and continue for up to 8 tool calls within the existing 90-second request limit.
- SQLite conversation history, saved preferences, search and archive commands, and supported text/PDF uploads.
- Generated documents and downloadable web projects with an isolated preview.

Use `/help` in the chat to see commands. Provider keys are loaded server-side from `.env` and are not shown in the interface.

The native tool loop is enabled only for model IDs verified for tool calling in the provider documentation: `gemini-3.8-flash`, `openai/gpt-oss-20b`, and `openai/gpt-oss-120b`. If a different model is configured, the app reports that it is unverified and names these fallbacks. The registry is in `tools.py`; new tool functions can be registered there with an input schema and short description.

## Optional model-list utility

To list models available to an OpenAI API key, put `OPENAI_API_KEY` in `.env` and run:

```powershell
.\.venv\Scripts\python.exe list_models.py
```

This is a utility script; it is not a second app.

## Tests

Unit tests use mocked providers and do not make live API calls:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
