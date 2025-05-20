import os
from memory import get_memory
from langchain.chains import ConversationChain
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr
import chainlit as cl  # ✅ make sure this is imported

# Load Google API key
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable is not set.")

# Set up the language model
llm = ChatGoogleGenerativeAI(
    model="gemini-pro",
    api_key=SecretStr(google_api_key),
    temperature=0.7
)

# Set up conversation memory and agents
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

def route_message_to_agent(message: str):
    msg = message.lower()
    if "math" in msg:
        return math_bot
    elif "write" in msg or "writer" in msg:
        return writer_bot
    else:
        return math_bot  # fallback

@cl.on_message
async def on_message(message: cl.Message):
    user_input = message.content.lower().strip()
    print("Received message:", user_input)  # ✅ Debug log

    # If user says hi or greetings, reply with nothing (no message sent)
    if user_input in ["hi", "hello", "hey", "me hi"]:
        return  # No reply at all

    # Otherwise, route the message and stream the response
    conversation = route_message_to_agent(message.content)
    
    msg = cl.Message(content="")
    await msg.send()

    async for chunk in conversation.astream({"input": message.content}):
        if "response" in chunk:
            await msg.stream_token(chunk["response"])
    await msg.update()
