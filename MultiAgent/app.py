import os
from dotenv import load_dotenv
import chainlit as cl
from pydantic import SecretStr
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain_groq import ChatGroq

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise ValueError("GROQ_API_KEY environment variable is not set.")

# Initialize two agents using Groq model
llm_agent1 = ChatGroq(
    api_key=SecretStr(groq_api_key),
    model="llama3-8b-8192"
)
llm_agent2 = ChatGroq(
    api_key=SecretStr(groq_api_key),
    model="llama3-8b-8192"
)

memory_agent1 = ConversationBufferMemory()
memory_agent2 = ConversationBufferMemory()

conversation_agent1 = ConversationChain(llm=llm_agent1, memory=memory_agent1, verbose=True)
conversation_agent2 = ConversationChain(llm=llm_agent2, memory=memory_agent2, verbose=True)

def route_message_to_agent(message: str):
    msg = message.lower()
    if "agent1" in msg:
        return conversation_agent1
    elif "agent2" in msg:
        return conversation_agent2
    else:
        return conversation_agent1  # default

@cl.on_message
async def on_message(message: cl.Message):
    conversation = route_message_to_agent(message.content)
    response = conversation.invoke(message.content)
    await cl.Message(content=response['response']).send()
