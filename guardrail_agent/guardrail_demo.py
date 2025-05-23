import asyncio
from pydantic import BaseModel

# Classes to represent guardrail results
class GuardrailResult:
    def __init__(self, data, triggered):
        self.data = data
        self.triggered = triggered

class InputGuardrailTriggered(Exception):
    pass

class OutputGuardrailTriggered(Exception):
    pass

# Models for input check
class MathInputCheck(BaseModel):
    is_math_homework: bool
    reason: str

# Model for agent response
class AgentResponse(BaseModel):
    text: str

# Models for output check
class MathOutputCheck(BaseModel):
    contains_math: bool
    explanation: str

# Customer support agent simulation
async def customer_support_agent(user_input: str) -> AgentResponse:
    if "problem" in user_input.lower() or "issue" in user_input.lower():
        return AgentResponse(text="I understand your problem. How can I help you?")
    # Simple fallback if math chars in input, agent tries to help with math
    if any(ch in user_input for ch in ['x', '=', '+', '-', '*', '/']):
        return AgentResponse(text="To solve for x, isolate the variable on one side of the equation.")
    return AgentResponse(text="Thanks for contacting support! How else can I assist?")

# Input guardrail check function
async def input_guardrail_check(user_input: str) -> GuardrailResult:
    math_chars = ['x', '=', '+', '-', '*', '/']
    if any(ch in user_input for ch in math_chars):
        return GuardrailResult(
            data=MathInputCheck(is_math_homework=True, reason="Input looks like math homework."),
            triggered=True
        )
    return GuardrailResult(
        data=MathInputCheck(is_math_homework=False, reason="Input passed guardrail."),
        triggered=False
    )

# Output guardrail check function
async def output_guardrail_check(agent_output: AgentResponse) -> GuardrailResult:
    math_chars = ['x', '=', '+', '-', '*', '/']
    if any(ch in agent_output.text for ch in math_chars):
        return GuardrailResult(
            data=MathOutputCheck(contains_math=True, explanation="Agent output contains math."),
            triggered=True
        )
    return GuardrailResult(
        data=MathOutputCheck(contains_math=False, explanation="Agent output passed guardrail."),
        triggered=False
    )

# Main function to run the full check and agent interaction
async def main():
    user_input = input("User: ")

    # Check input guardrail
    input_result = await input_guardrail_check(user_input)
    if input_result.triggered:
        print(" Input Guardrail triggered: math homework detected. Cannot process request.")
        return

    # Run agent response
    agent_response = await customer_support_agent(user_input)
    print(f"Agent: {agent_response.text}")

    # Check output guardrail
    output_result = await output_guardrail_check(agent_response)
    if output_result.triggered:
        print(" utput Guardrail triggered: response contains math. Request denied.")
        return

    print("All guardrails passed. Conversation completed successfully.")

# Run program
if __name__ == "__main__":
    asyncio.run(main())
