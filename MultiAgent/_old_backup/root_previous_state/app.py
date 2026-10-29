import os
from dotenv import load_dotenv
import chainlit as cl
from pydantic import SecretStr
from langchain_core.prompts import PromptTemplate
from langchain_classic.memory import ConversationBufferMemory
from langchain_classic.chains import ConversationChain
from langchain_groq import ChatGroq

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise ValueError("GROQ_API_KEY environment variable is not set.")

# Change the model names here only. One place to fix when Groq retires a model.
FAST_MODEL = "openai/gpt-oss-20b"    # small and quick
SMART_MODEL = "openai/gpt-oss-120b"  # bigger and smarter


def make_agent(model: str, role: str) -> ConversationChain:
    """Build one agent with its own model, memory and personality."""
    llm = ChatGroq(api_key=SecretStr(groq_api_key), model=model)
    prompt = PromptTemplate(
        input_variables=["history", "input"],
        template=(
            role
            + "\n\nConversation so far:\n{history}\n\nHuman: {input}\nAI:"
        ),
    )
    return ConversationChain(
        llm=llm,
        memory=ConversationBufferMemory(),
        prompt=prompt,
        verbose=False,
    )


# Agent 1 is quick and friendly. Agent 2 is slower but thinks harder.
agent1 = make_agent(
    FAST_MODEL,
    "You are Agent 1, a quick and friendly helper. "
    "Keep answers short, simple and easy to read.",
)
agent2 = make_agent(
    SMART_MODEL,
    "You are Agent 2, a careful thinker. "
    "Give deeper, well thought out answers and explain your reasoning in simple words.",
)


def route_message_to_agent(message: str):
    msg = message.lower()
    if "agent2" in msg:
        return agent2, "Agent 2"
    return agent1, "Agent 1"  # default


@cl.on_message
async def on_message(message: cl.Message):
    conversation, agent_name = route_message_to_agent(message.content)
    # make_async stops the app from freezing while the model thinks
    response = await cl.make_async(conversation.invoke)(message.content)
    await cl.Message(content=response["response"], author=agent_name).send()