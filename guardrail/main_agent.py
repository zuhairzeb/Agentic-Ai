import os
import asyncio
from dotenv import load_dotenv
from pydantic import BaseModel

# Simulate imports from your agents framework
# (In real use, import from your actual library)
class InputGuardrailTripwireTriggered(Exception):
    pass

class OutputGuardrailTripwireTriggered(Exception):
    pass

def set_tracing_disabled(disabled: bool):
    print(f"Tracing disabled: {disabled}")

# Load environment variables from .env file
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set. Please define it in your .env file.")
if not GROQ_MODEL:
    raise ValueError("GROQ_MODEL is not set. Please define it in your .env file.")

set_tracing_disabled(disabled=True)

# Your Data Models
class UserInputModel(BaseModel):
    user_text: str

class AgentResponseModel(BaseModel):
    response_text: str

# Guardrail checker class
class Guardrails:
    SENSITIVE_KEYWORDS = [
        "hack", "cheat", "exploit", "bypass", "abuse", "cuss", "swear",
        "homework", "assignment", "exam", "test", "solution", "answers",
        "violence", "kill", "bomb", "shoot"
    ]
    SCHOOL_QUESTION_PHRASES = [
        "what is", "explain it", "write a", "rewrite",
        "can you", "can you solve it", "solve it", "problem", "discuss"
    ]
    MATH_CHARS = ['x', '=', '+', '-', '*', '/']

    @classmethod
    async def input_guardrail(cls, user_input: str):
        lower_input = user_input.lower()

        # Check sensitive keywords
        for kw in cls.SENSITIVE_KEYWORDS:
            if kw in lower_input:
                raise InputGuardrailTripwireTriggered(f"Input contains sensitive keyword '{kw}'.")

        # Check school question phrases
        for phrase in cls.SCHOOL_QUESTION_PHRASES:
            if phrase in lower_input:
                raise InputGuardrailTripwireTriggered(f"Input looks like a school question ('{phrase}').")

        # Check for math chars indicating homework
        if any(ch in user_input for ch in cls.MATH_CHARS):
            raise InputGuardrailTripwireTriggered("Input looks like math homework.")

    @classmethod
    async def output_guardrail(cls, agent_response: AgentResponseModel):
        if any(ch in agent_response.response_text for ch in cls.MATH_CHARS):
            raise OutputGuardrailTripwireTriggered("Agent output contains math content.")

# Your simulated Agent
class CustomerSupportAgent:
    @staticmethod
    async def respond(user_input: str) -> AgentResponseModel:
        lower_input = user_input.lower()

        if "problem" in lower_input or "issue" in lower_input:
            return AgentResponseModel(response_text="I understand your problem. How can I help you?")

        if any(ch in user_input for ch in ['x', '=', '+', '-', '*', '/']):
            return AgentResponseModel(response_text="To solve for x, isolate the variable on one side of the equation.")

        return AgentResponseModel(response_text="Thanks for contacting support! How else can I assist?")

# Main orchestrator function
async def main():
    user_text = input("User: ")

    # Input guardrail check
    try:
        await Guardrails.input_guardrail(user_text)
    except InputGuardrailTripwireTriggered as e:
        print(f"Input Guardrail triggered: {e}")
        return

    # Get agent response
    agent_response = await CustomerSupportAgent.respond(user_text)
    print(f"Agent: {agent_response.response_text}")

    # Output guardrail check
    try:
        await Guardrails.output_guardrail(agent_response)
    except OutputGuardrailTripwireTriggered as e:
        print(f"Output Guardrail triggered: {e}")
        return

    print("All guardrails passed. Conversation completed successfully.")

# Run the program
if __name__ == "__main__":
    asyncio.run(main())
