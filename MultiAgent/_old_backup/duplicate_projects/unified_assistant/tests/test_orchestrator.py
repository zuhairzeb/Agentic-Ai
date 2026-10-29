import asyncio
import unittest

from orchestrator import AgentOrchestrator, TaskPlan, TaskRun
from router import AGENTS


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def test_routes_simple_work_and_selects_calculator_for_math(self):
        orchestrator = AgentOrchestrator()
        math_plan = orchestrator.plan("Calculate 15% of 200")
        self.assertEqual(math_plan.route.key, "math")
        self.assertEqual(math_plan.tool_name, "calculator")
        natural_math = orchestrator.plan("What is 17 times 19?")
        self.assertEqual(natural_math.tool_name, "calculator")
        self.assertEqual(orchestrator.plan("Draft a polite email", "write").route.key, "writing")
        self.assertEqual(orchestrator.plan("AI safety literature", "research").route.key, "research")
        self.assertEqual(orchestrator.plan("15% of 200", "analyze").route.key, "math")
        self.assertIsNone(orchestrator.plan("Explain photosynthesis").tool_name)

    def test_execution_state_stops_repeated_and_excess_steps(self):
        run = TaskRun(TaskPlan(route=AGENTS["general"], prompt="", max_steps=2))
        run.checkpoint("route")
        with self.assertRaisesRegex(RuntimeError, "Repeated"):
            run.checkpoint("route")
        run = TaskRun(TaskPlan(route=AGENTS["general"], prompt="", max_steps=1))
        run.checkpoint("route")
        with self.assertRaisesRegex(RuntimeError, "maximum step"):
            run.checkpoint("model")

    async def test_task_step_timeout_is_bounded(self):
        async def never_finishes():
            await asyncio.sleep(0.1)
        run = TaskRun(TaskPlan(route=AGENTS["general"], prompt=""))
        with self.assertRaises(asyncio.TimeoutError):
            await run.execute("slow-step", never_finishes, timeout=0.01)

    async def test_retries_are_bounded_by_plan(self):
        attempts = 0
        async def succeeds_after_one_failure():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient")
            return "done"
        run = TaskRun(TaskPlan(route=AGENTS["general"], prompt="", max_retries=1))
        self.assertEqual(await run.execute("retryable", succeeds_after_one_failure, retries=1), "done")
        self.assertEqual(attempts, 2)
        with self.assertRaisesRegex(ValueError, "retry limit"):
            await run.execute("too-many", succeeds_after_one_failure, retries=2)

    async def test_task_cancellation_is_reported(self):
        run = TaskRun(TaskPlan(route=AGENTS["general"], prompt=""))
        async def wait_forever():
            await asyncio.sleep(10)
        task = asyncio.create_task(run.execute("cancel-me", wait_forever))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(run.status, "cancelled")


if __name__ == "__main__":
    unittest.main()
