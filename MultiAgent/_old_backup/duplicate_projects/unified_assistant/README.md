# Unified Multi Agent AI Assistant

One Chainlit application combines the Gemini math and writing agents, the Groq general agents, and the provider streaming feature found in the two source projects. The older source folders remain in the workspace as references; run this application from `unified_assistant`.

## Features and architecture

- **Math Agent (Gemini):** calculations and math explanations.
- **Writing Agent (Gemini):** writing, editing, summaries, emails, and creative content.
- **General Agent (Groq):** conversation, explanations, coding, and general questions.
- **Agent 1 / Agent 2 (Groq):** the original fast and detailed assistant choices.
- **Automatic routing:** small local keyword and expression rules select an agent; no extra model call is made.
- **Streaming:** streams model chunks through LangChain's `astream` where supported. Calls `ainvoke`/`invoke` without artificial delays only if the integration lacks streaming.
- **Session memory:** the last 20 user/assistant turns are shared across agents in the current Chainlit session. Memory is in process and is cleared at chat start; it is not persistent across restarts or workers.

Agent selection is available with a leading chat command: `math ...`, `writer ...`, `agent1 ...`, or `agent2 ...`. Without a command, math cues route to Math, writing cues route to Writing, and other messages route to General. A user can change topics on any turn; routing runs independently each time.

## Providers and models

- Gemini math and writing use `gemini-2.5-flash` by default.
- Groq general and Agent 1 use `openai/gpt-oss-20b`; Agent 2 uses `openai/gpt-oss-120b`.
- Model names can be overridden with `GOOGLE_MODEL`, `GROQ_FAST_MODEL`, and `GROQ_SMART_MODEL`.
- No automatic provider switching is performed. Each chosen agent requires its provider key.

Provider model catalogs change. These defaults were checked against the [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models) and [Groq supported models](https://console.groq.com/docs/models) on 2026-10-28. Availability can depend on the provider account.

## Requirements and setup

Python 3.10 or newer is required. From this directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set the keys for the providers you intend to use:

```env
GOOGLE_API_KEY=
GROQ_API_KEY=
GOOGLE_MODEL=gemini-2.5-flash
GROQ_FAST_MODEL=openai/gpt-oss-20b
GROQ_SMART_MODEL=openai/gpt-oss-120b
```

Run the Chainlit application from this directory:

```powershell
.venv\Scripts\python.exe -m chainlit run app.py
```

Use this project-local interpreter so global Python packages cannot introduce incompatible LangChain versions.

## Usage examples

- `Calculate 15% of 200` → Math Agent
- `Write a professional email asking to reschedule` → Writing Agent
- `Explain Python decorators` → General Agent
- `writer Tell a short story about Mars` → Writing Agent (manual command)
- `agent2 Explain recursion carefully` → detailed Groq agent

## Tests

The unit tests use Python's standard `unittest` library and do not call provider APIs:

```powershell
python -m unittest discover -s tests -v
```

Live provider checks require valid keys and may incur usage charges; they are not part of the unit suite.

## Troubleshooting and security

- **Missing key:** add `GOOGLE_API_KEY` for math/writing or `GROQ_API_KEY` for general/Agent 1/Agent 2.
- **Authentication, model, rate-limit, or network errors:** verify the key, account access, selected model identifier, quota, and connectivity with the provider. The app reports a generic safe message; logs contain the exception type, not prompt contents or credentials.
- **Missing integration:** reinstall dependencies with `python -m pip install -r requirements.txt`.
- **LangChain `AttributeError` during agent setup:** run with `.venv\Scripts\python.exe -m chainlit run app.py` from this folder. A globally installed LangChain bundle can conflict with the `langchain-core` version used by the app.
- Keep `.env` private and never commit real keys. `.env.example` contains placeholders only.

## Project layout

```text
unified_assistant/
├── app.py
├── core/
│   ├── config.py
│   ├── memory.py
│   ├── router.py
│   └── generation.py
├── tests/
├── .env.example
└── requirements.txt
```

## Source projects and author

The originals were found at the workspace root and in `chatbot_project/`. Useful provider choices, math/writing specialization, the `agent1`/`agent2` commands, Chainlit UI, and session conversation context were carried forward. The original streaming implementation generated the full response before emitting delayed chunks, so the unified app replaces that simulation with model streaming.

Author information in the existing README: Muhammad Zuhair Zeb (`zuhairzeb@yahoo.com`).
