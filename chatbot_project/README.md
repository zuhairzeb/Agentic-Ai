# Multi-Agent AI Chatbot with Streaming Support

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![LangChain](https://img.shields.io/badge/LangChain-0.1.x-orange.svg)
![Chainlit](https://img.shields.io/badge/Chainlit-1.0+-green.svg)

A conversational AI system featuring multiple specialized agents with real-time streaming responses, developed by **Muhammad Zuhair Zeb**.

## Key Features

- 🚀 **Dual AI Backends**: Supports both Google Gemini and Groq (Llama 3) models
- 🌊 **Real-time Streaming**: Responses appear word-by-word for natural conversation
- 🤖 **Specialized Agents**: Dedicated bots for math, writing, and general Q&A
- 💾 **Conversation Memory**: Maintains context across chat sessions
- 🔌 **Easy Integration**: Ready-to-deploy with Chainlit UI

## Project Structure



## Key Features

- 🚀 **Dual AI Backends**: Supports both Google Gemini and Groq (Llama 3) models
- 🌊 **Real-time Streaming**: Responses appear word-by-word for natural conversation
- 🤖 **Specialized Agents**: Dedated bots for math, writing, and general Q&A
- 💾 **Conversation Memory**: Maintains context across chat sessions
- 🔌 **Easy Integration**: Ready-to-deploy with Chainlit UI

## Key Highlights

1. **Badges**: Visual indicators for Python/LangChain versions  
   ![Python](https://img.shields.io/badge/python-3.9+-blue.svg) ![LangChain](https://img.shields.io/badge/LangChain-0.1.x-orange.svg)

2. **Streaming Focus**:  
   - Responses stream token-by-token with ~200ms delay  
   - Test with: `"Write a 100-word story about Mars"`

3. **Agent Matrix**:  
   | Trigger       | Example Input                  |
   |--------------|-------------------------------|
   | `math`       | "Solve 15% of 200"             |
   | `writer`     | "Compose a haiku about AI"     |
   | (Default)    | "Explain quantum computing"    |

4. **Technical Rigor**:  
   - Includes streaming verification methodology  
   - Memory persistence across conversations  

5. **Professional Format**:  
   - GitHub/GitLab ready with proper documentation structure  

---

### For Your Follow-Up Questions:


```markdown
## Optional Additions

### Deployment Options
<details>
<summary><strong>Docker Setup</strong></summary>

```dockerfile
FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["chainlit", "run", "app.py", "--port", "8000"]



### Why This Placement Works Best:
1. **Logical Flow**:  
   - Highlights appear right after features to emphasize value  
   - Optional sections at the end avoid cluttering core docs  

2. **Visual Balance**:  
   - Badges/Markdown tables break up text walls  
   - Collapsible Docker instructions (using `<details>`) keep it tidy  

3. **Actionable**:  
   - The agent matrix gives immediate usage examples  
   - Streaming test case is directly suggested  

Would you like me to:  
- Provide actual screenshot examples?  
- Expand the Docker setup further?  
- Add a troubleshooting section?