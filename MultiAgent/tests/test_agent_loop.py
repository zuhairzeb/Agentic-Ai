import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from agent_loop import AgentResponseIncompleteError, ToolCallingNotSupportedError, run_agent_loop
from generation import generate_agent_with_fallback
from provider_router import provider_health
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
    async def test_provider_failure_after_tool_execution_does_not_repeat_side_effect(self):
        provider_health.reset()
        executions, providers = [], []
        class Model:
            def __init__(self): self.calls = 0
            def bind_tools(self, _schemas, tool_choice="auto"): return self
            async def ainvoke(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    return AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "2 + 2"}, "id": "once", "type": "tool_call"}])
                raise ConnectionError("stream failed after tool")
        async def execute(*_args, **_kwargs):
            executions.append("calculator")
            from tools import ToolResult
            return ToolResult(True, data={"value": 4})
        async def emit(_token): pass
        async def fallback(_provider): pass
        with patch.object(tools, "execute", side_effect=execute):
            with self.assertRaises(ConnectionError):
                await generate_agent_with_fallback(
                    ["google", "groq"],
                    lambda provider: (providers.append(provider) or Model()),
                    lambda provider: "gemini-3.8-flash" if provider == "google" else "openai/gpt-oss-20b",
                    [HumanMessage(content="Calculate 2 + 2")], emit, fallback, tools,
                    permissions={"math"},
                )
        self.assertEqual(providers, ["google"])
        self.assertEqual(executions, ["calculator"])
        provider_health.reset()

    async def test_tool_agent_streams_final_text_and_detects_output_limit(self):
        class StreamingModel:
            def bind_tools(self, _schemas, tool_choice="auto"):
                return self
            async def astream(self, _messages):
                yield AIMessageChunk(content="An answer ")
                yield AIMessageChunk(content="in progress", response_metadata={"finish_reason": "length"})

        chunks = []
        async def emit(text): chunks.append(text)
        with self.assertRaises(AgentResponseIncompleteError) as raised:
            await run_agent_loop(
                StreamingModel(), [HumanMessage(content="Calculate")], tools,
                provider="google", model_name="gemini-3.8-flash", permissions={"math"},
                on_token=emit,
            )
        self.assertEqual(raised.exception.partial, "An answer in progress")
        self.assertEqual("".join(chunks), raised.exception.partial)

    async def test_model_calls_calculator_and_uses_its_result(self):
        model = CalculatorThenAnswerModel()
        events = []
        async def on_tool_event(event): events.append(event)
        result = await run_agent_loop(
            model,
            [HumanMessage(content="Calculate 15% of 200")],
            tools,
            provider="google",
            model_name="gemini-3.8-flash",
            permissions={"math"},
            max_steps=3,
            on_tool_event=on_tool_event,
        )
        self.assertEqual(result.text, "15% of 200 is 30.")
        self.assertEqual(result.tool_steps, ("calculator",))
        self.assertEqual(model.assert_result["data"]["value"], 30)
        self.assertEqual(model.bound_schemas[0]["name"], "calculator")
        self.assertEqual(events, [{"name": "calculator", "state": "started"}, {"name": "calculator", "state": "completed"}])

    async def test_streaming_tool_call_chunks_are_assembled_before_execution(self):
        class StreamingToolModel:
            def __init__(self): self.calls = 0
            def bind_tools(self, _schemas, tool_choice="auto"): return self
            async def astream(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    yield AIMessageChunk(content="", tool_call_chunks=[{
                        "name": "calculator", "args": '{"expression":"2 + 2"}', "id": "calc-stream", "index": 0,
                    }])
                else:
                    yield AIMessageChunk(content="2 + 2 is 4.", response_metadata={"finish_reason": "stop"})

        streamed = []
        model = StreamingToolModel()
        async def collect(text): streamed.append(text)
        result = await run_agent_loop(
            model, [HumanMessage(content="Calculate 2 + 2")], tools,
            provider="google", model_name="gemini-3.8-flash", permissions={"math"},
            on_token=collect,
        )
        self.assertEqual(result.text, "2 + 2 is 4.")
        self.assertEqual("".join(streamed), result.text)
        self.assertEqual(result.tool_steps, ("calculator",))

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

    async def test_verified_free_cloudflare_and_openrouter_models_support_tool_loop(self):
        for provider, model_name in (
            ("cloudflare", "@cf/zai-org/glm-4.7-flash"),
            ("cloudflare", "@cf/google/gemma-4-26b-a4b-it"),
            ("openrouter", "openrouter/free"),
        ):
            with self.subTest(provider=provider, model=model_name):
                model = CalculatorThenAnswerModel()
                result = await run_agent_loop(
                    model,
                    [HumanMessage(content="Calculate 15% of 200")],
                    tools,
                    provider=provider,
                    model_name=model_name,
                    permissions={"math"},
                    max_steps=3,
                )
                self.assertEqual(result.text, "15% of 200 is 30.")
                self.assertEqual(result.tool_steps, ("calculator",))


if __name__ == "__main__":
    unittest.main()
