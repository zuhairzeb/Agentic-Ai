# Morrow — Multi-Agent AI Workspace

Morrow is a self-hosted AI workspace for chat, research, writing, and code projects. It routes requests to specialized agents and supports multiple hosted and local language model providers, with provider failover and optional free-only routing.

The application lives in [`MultiAgent/`](MultiAgent/). For the complete feature guide, configuration reference, API endpoints, and troubleshooting notes, see the [detailed README](MultiAgent/README.md).

## Features

- **Multiple model providers:** Gemini, Groq, Cloudflare Workers AI, OpenRouter, and local Ollama.
- **Specialized agents:** Routes tasks such as math, coding, research, and writing to purpose-built agents.
- **Web research:** Search with DuckDuckGo or configure Serper or Tavily; read public web pages with SSRF protections.
- **Local knowledge search:** Retrieve relevant passages from Markdown files using BM25, without a vector database.
- **Tools and workspaces:** Safe calculations, document uploads, MCP integrations, and conversation-scoped code artifacts.
- **Local data and privacy controls:** SQLite-backed storage, configurable memory, and temporary chats.

## Quick start

You need Python 3.10 or newer. From the repository root:

```powershell
cd MultiAgent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `MultiAgent/.env` and add credentials for the providers you plan to use. DuckDuckGo search and Ollama do not require hosted-provider API keys. Review the [configuration guide](MultiAgent/README.md#configuration-env) for provider options and free-only mode.

Start the web app from the `MultiAgent` directory:

```powershell
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Then open [http://localhost:8000](http://localhost:8000). To use the alternative Chainlit interface, run `python -m chainlit run app.py -w` from the same directory.

## Configuration and data

The app reads settings from `MultiAgent/.env`. Keep API credentials there and do not commit the file. The checked-in `.env.example` contains the supported variables. The optional local Markdown knowledge base defaults to `../sociapi_agent_knowledge_base`; set `SOCIAPI_KNOWLEDGE_DIR` to use another folder.

## Project layout

```text
MultiAgent/                     Application, web UI, and tests
sociapi_agent_knowledge_base/   Local Markdown knowledge base
chatbot_project/                Separate chatbot project
guardrail/                      Guardrail project
```

## Documentation

See [`MultiAgent/README.md`](MultiAgent/README.md) for architecture, agent roles, provider routing, tools, the knowledge base, MCP, tests, and API endpoints.

## License

See [LICENSE](LICENSE).
