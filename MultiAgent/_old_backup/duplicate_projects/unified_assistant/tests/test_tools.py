import asyncio
import unittest

from pydantic import BaseModel, ConfigDict, Field

from tools import ToolDefinition, ToolRegistry, calculate, expression_from_text, tools


class SlowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=10)


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def test_safe_calculator_and_natural_math_parsing(self):
        self.assertEqual(calculate("2 + 3 * 4")["value"], 14)
        self.assertEqual(calculate(expression_from_text("calculate 15% of 200"))["value"], 30)
        self.assertEqual(calculate(expression_from_text("what is 17 times 19"))["value"], 323)

    def test_calculator_rejects_code_and_unsafe_exponents(self):
        with self.assertRaises(ValueError):
            calculate("__import__('os').system('whoami')")
        with self.assertRaises(ValueError):
            calculate("2**99")
        self.assertIsNone(expression_from_text("open a file and read it"))

    async def test_registry_validates_schema_and_permissions(self):
        denied = await tools.execute("calculator", {"expression": "2+2"})
        self.assertFalse(denied.ok)
        self.assertIn("Permission", denied.error)
        extra = await tools.execute("calculator", {"expression": "2+2", "command": "whoami"}, {"math"})
        self.assertFalse(extra.ok)
        result = await tools.execute("calculator", {"expression": "2+2"}, {"math"})
        self.assertTrue(result.ok)
        self.assertEqual(result.data["value"], 4)

    async def test_registry_enforces_timeout_and_reports_failure(self):
        async def slow(arguments):
            await asyncio.sleep(0.1)
            return {"value": arguments.value}
        registry = ToolRegistry()
        registry.register(ToolDefinition("slow", "slow test tool", SlowInput, slow, timeout_seconds=0.01))
        result = await registry.execute("slow", {"value": "test"})
        self.assertFalse(result.ok)
        self.assertIn("timed out", result.error)


if __name__ == "__main__":
    unittest.main()
