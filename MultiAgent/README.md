# Multi-Agent Chat System

<div align="center">
  <img src="https://img.shields.io/badge/python-3.7%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/LangChain-0.1%2B-orange" alt="LangChain">
  <img src="https://img.shields.io/badge/VS%20Code-1.85%2B-blueviolet" alt="VS Code">
</div>

## Table of Contents
- [Project Overview](#project-overview)
- [Features](#-features)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Agent Details](#-agent-details)
- [File Structure](#-file-structure)
- [Support](#-support)

## Project Overview
A sophisticated multi-agent chat system developed by **Muhammad Zuhair Zeb** that leverages:
- Google's Gemini-pro for specialized tasks (Math & Writing)
- Groq's Llama3 for general conversation
- Intelligent message routing between agents

## ✨ Features
- **Dual AI Architecture**: Gemini + Llama3 integration
- **Context-Aware**: Conversation memory management
- **Dynamic Routing**: Smart agent selection
- **Production-Ready**: Environment variable configuration
- **Verbose Logging**: Detailed conversation tracking

## 🛠 Installation
1. Clone repository:
   ```bash
   git clone https://github.com/your-repo/multi-agent-chat.git
   cd multi-agent-chat

## ⚙ Configuration
Create `.env` file with:
```ini
GOOGLE_API_KEY=your_actual_key
GROQ_API_KEY=your_actual_key
```

## 🚀 Usage
```bash
chainlit run app.py
```
Then interact via:
- `agent1`: Routes to Groq Agent 1
- `agent2`: Routes to Groq Agent 2
- Default: Uses Groq Agent 1

## 🤖 Agent Details

### Gemini Agents (agents.py)
| Agent | Model | Temperature | Use Case |
|-------|-------|-------------|----------|
| math_bot | gemini-pro | 0.7 | Mathematical operations |
| writer_bot | gemini-pro | 0.7 | Content creation |

### Groq Agents (app.py)
| Feature | Agent 1 | Agent 2 |
|---------|---------|---------|
| Model | llama3-8b-8192 | llama3-8b-8192 |
| Memory | ConversationBuffer | ConversationBuffer |

## 📂 File Structure
```text
multi-agent-chat/
├── agents.py        # Gemini agent configurations
├── app.py           # Main application logic
├── memory.py        # Memory management
├── README.md        # This document
└── .env.example     # Environment template
```

## 📞 Support
For assistance, contact:
- ✉ Email: zuhairzeb@yahoo.com
- 💬 Issues: GitHub Issues



<div align="center">
  <sub>Built with ❤️ by Muhammad Zuhair Zeb | VS Code Optimized</sub>
</div>

### Key Features:
1. **Consistent Formatting**: Uniform headers and sections
2. **Visual Hierarchy**: Clear information organization
3. **VS Code Optimized**:
   - Proper Markdown rendering
   - Clickable table of contents
   - Syntax highlighting for code blocks
4. **Responsive Design**: Renders well on GitHub/GitLab
5. **Complete Documentation**: All necessary sections included
6. **Badge Alignment**: Centered for visual appeal

This format maintains readability in VS Code's Markdown preview while ensuring compatibility with other platforms. The table of contents allows for easy navigation in VS Code's outline view.