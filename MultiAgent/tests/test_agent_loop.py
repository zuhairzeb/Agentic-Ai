import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_loop import ToolCallingNotSupportedError, run_agent_loop
from tools import tools


class CalculatorThenAnswerModel:
    def __init__(self):
        self.calls = 0
        self.bound_schemas = None

    def bind_tools(self, schemas, tool_choice="auto"):
        self.bound_schemas = schemas
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "calculator",
                "args": {"expression": "15 / 100 * 200"},
                "id": "calc-1",
                "type": "tool_call",
            }])
        result = next(message for message in messages if isinstance(message, ToolMessage))
        self.assert_result = json.loads(result.content)
        return AIMessage(content="15% of 200 is 30.")


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_calls_calculator_and_uses_its_result(self):
        model = CalculatorThenAnswerModel()
        result = await run_agent_loop(
            model,
            [HumanMessage(content="Calculate 15% of 200")],
            tools,
            provider="google",
            model_name="gemini-3.8-flash",
            permissions={"math"},
            max_steps=3,
        )
        self.assertEqual(result.text, "15% of 200 is 30.")
        self.assertEqual(result.tool_steps, ("calculator",))
        self.assertEqual(model.assert_result["data"]["value"], 30)
        self.assertEqual(model.bound_schemas[0]["name"], "calculator")

    async def test_unknown_model_is_rejected_with_verified_fallbacks(self):
        model = CalculatorThenAnswerModel()
        with self.assertRaisesRegex(ToolCallingNotSupportedError, "openai/gpt-oss"):
            await run_agent_loop(
                model,
                [HumanMessage(content="Calculate 1 + 1")],
                tools,
                provider="groq",
                model_name="unverified-model",
                permissions={"math"},
            )
        self.assertEqual(model.calls, 0)


if __name__ == "__main__":
    unittest.main()
