import os
from memory import get_memory
from langchain.chains import ConversationChain
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable is not set.")

llm = ChatGoogleGenerativeAI(
    model="gemini-pro",
    api_key=SecretStr(google_api_key),
    temperature=0.7
)

math_bot = ConversationChain(
    llm=llm,
    memory=get_memory(),
    verbose=True
)

writer_bot = ConversationChain(
    llm=llm,
    memory=get_memory(),
    verbose=True
)
