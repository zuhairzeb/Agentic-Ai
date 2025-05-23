import os
from pydantic import SecretStr
from langchain.chains import ConversationChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from memory import get_memory

# Load API keys
groq_api_key = os.getenv("GROQ_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

# Create LLMs
llm_groq = ChatGroq(model="llama3-8b-8192", api_key=SecretStr(groq_api_key) if groq_api_key else None)
llm_google = ChatGoogleGenerativeAI(model="gemini-pro", api_key=SecretStr(google_api_key) if google_api_key else None)


# Define Agents
agents = {
    "agent1": ConversationChain(llm=llm_groq, memory=get_memory(), verbose=True),
    "agent2": ConversationChain(llm=llm_groq, memory=get_memory(), verbose=True),
    "math": ConversationChain(llm=llm_google, memory=get_memory(), verbose=True),
    "writer": ConversationChain(llm=llm_google, memory=get_memory(), verbose=True),
}

# Routing Logic
def get_agent(message: str) -> ConversationChain:
    msg = message.lower()
    if "agent1" in msg:
        return agents["agent1"]
    elif "agent2" in msg:
        return agents["agent2"]
    elif "math" in msg:
        return agents["math"]
    elif "write" in msg or "writer" in msg:
        return agents["writer"]
    else:
        return agents["agent1"]  # Default fallback
