import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import web_app
from generation import IncompleteResponseError, ProvidersUnavailableError, generate_with_fallback
from provider_router import current_request_id, provider_health
from storage import SQLiteStore


class _Answer:
    def __init__(self, text):
        self.content = text


class _AnswerModel:
    def __init__(self, answer):
        self.answer = answer

    async def ainvoke(self, _messages):
        await asyncio.sleep(0)
        return _Answer(self.answer)


class ConcurrentRequestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        provider_health.reset()

    async def asyncTearDown(self):
        provider_health.reset()

    async def run_generation(self, provider_order, create_model, *, messages=None):
        tokens = []

        async def emit(token):
            tokens.append(token)

        async def fallback(_provider):
            return None

        answer, provider = await generate_with_fallback(
            provider_order, create_model, messages or [], emit, fallback, streaming=False
        )
        return answer, provider, tokens

    async def test_two_independent_requests_receive_their_own_answer(self):
        gate = asyncio.Event()
        arrived = 0

        def make(answer):
            class Model:
                async def ainvoke(self, _messages):
                    nonlocal arrived
                    arrived += 1
                    if arrived == 2:
                        gate.set()
                    await gate.wait()
                    return _Answer(answer)
            return Model()

        results = await asyncio.gather(
            self.run_generation(["google"], lambda _: make("answer A")),
            self.run_generation(["google"], lambda _: make("answer B")),
        )
        self.assertEqual({result[0] for result in results}, {"answer A", "answer B"})

    async def test_five_requests_can_run_on_one_provider_at_once(self):
        started = 0
        peak = 0
        lock = asyncio.Lock()
        release = asyncio.Event()

        class Model:
            def __init__(self, answer):
                self.answer = answer

            async def ainvoke(self, _messages):
                nonlocal started, peak
                async with lock:
                    started += 1
                    peak = max(peak, started)
                    if started == 5:
                        release.set()
                await release.wait()
                async with lock:
                    started -= 1
                return _Answer(self.answer)

        results = await asyncio.gather(*[
            self.run_generation(["google"], lambda _, i=i: Model(f"request-{i}"))
            for i in range(5)
        ])
        self.assertEqual(peak, 5)
        self.assertEqual({row[0] for row in results}, {f"request-{i}" for i in range(5)})

    async def test_ten_requests_can_use_multiple_providers_independently(self):
        async def run(index):
            selected = "google" if index % 2 == 0 else "groq"
            result = await self.run_generation([selected], lambda _: _AnswerModel(f"r{index}"))
            return result[0]

        answers = await asyncio.gather(*(run(index) for index in range(10)))
        self.assertEqual(answers, [f"r{index}" for index in range(10)])
        snapshot = provider_health.snapshot()
        self.assertEqual(snapshot["Google Gemini"]["successes"], 5)
        self.assertEqual(snapshot["Groq"]["successes"], 5)

    async def test_one_provider_failure_does_not_interrupt_peer_request(self):
        peer_entered = asyncio.Event()
        release_peer = asyncio.Event()

        class Peer:
            async def ainvoke(self, _messages):
                peer_entered.set()
                await release_peer.wait()
                return _Answer("peer succeeded")

        class Failing:
            async def ainvoke(self, _messages):
                await peer_entered.wait()
                raise ConnectionError("isolated failure")

        peer_task = asyncio.create_task(self.run_generation(["google"], lambda _: Peer()))
        await peer_entered.wait()
        failed_task = asyncio.create_task(
            self.run_generation(["google", "groq"], lambda provider: Failing() if provider == "google" else _AnswerModel("fallback succeeded"))
        )
        failed_result = await failed_task
        release_peer.set()
        peer_result = await peer_task
        self.assertEqual(failed_result[0], "fallback succeeded")
        self.assertEqual(peer_result[0], "peer succeeded")

    async def test_429_cooldown_survives_a_concurrent_success(self):
        peer_entered = asyncio.Event()
        release_peer = asyncio.Event()

        class Peer:
            async def ainvoke(self, _messages):
                peer_entered.set()
                await release_peer.wait()
                return _Answer("peer survived rate limit")

        class RateLimited(Exception):
            status_code = 429
            headers = {"Retry-After": "30"}

            async def ainvoke(self, _messages):
                await peer_entered.wait()
                raise self

        peer = asyncio.create_task(self.run_generation(["google"], lambda _: Peer()))
        await peer_entered.wait()
        limited = await self.run_generation(["google", "groq"], lambda provider: RateLimited() if provider == "google" else _AnswerModel("fallback"))
        release_peer.set()
        self.assertEqual((await peer)[0], "peer survived rate limit")
        self.assertEqual(limited[0], "fallback")
        google = provider_health.snapshot()["Google Gemini"]
        self.assertGreaterEqual(google["cooldown_seconds"], 29)
        self.assertEqual(google["active_requests"], 0)

    async def test_rate_limit_error_preserves_retry_after_for_the_client(self):
        class RateLimited(Exception):
            status_code = 429
            headers = {"Retry-After": "12"}

            async def ainvoke(self, _messages):
                raise self

        with self.assertRaises(ProvidersUnavailableError) as raised:
            await self.run_generation(["google"], lambda _: RateLimited())
        self.assertEqual(raised.exception.provider, "google")
        self.assertEqual(raised.exception.status, 429)
        self.assertGreaterEqual(raised.exception.retry_after, 12)

    async def test_cancelling_one_attempt_does_not_count_as_provider_failure(self):
        started = asyncio.Event()
        never = asyncio.Event()

        class Blocking:
            async def astream(self, _messages):
                started.set()
                await never.wait()
                if False:
                    yield None

        async def emit(_token):
            return None

        async def fallback(_provider):
            return None

        task = asyncio.create_task(generate_with_fallback(["google"], lambda _: Blocking(), [], emit, fallback))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        status = provider_health.snapshot()["Google Gemini"]
        self.assertEqual(status["failures"], 0)
        self.assertEqual(status["active_requests"], 0)

    async def test_two_sse_responses_keep_request_and_conversation_ids_separate(self):
        ids = [uuid.uuid4().hex, uuid.uuid4().hex]
        request_ids = [uuid.uuid4().hex, uuid.uuid4().hex]
        for thread_id in ids:
            web_app.TEMP_CHATS[thread_id] = []
        route = web_app.orchestrator.plan("hello", default_agent="Auto").route
        plan = SimpleNamespace(route=route, prompt="hello", timeout_seconds=10, max_steps=1)

        async def planned(*_args):
            return plan

        async def fake_generate(_providers, _create, _messages, on_token, _fallback, streaming=True):
            rid = current_request_id.get()
            answer = f"answer:{rid}"
            await on_token(answer)
            return answer, "google"

        async def collect(response):
            chunks = []
            async for part in response.body_iterator:
                chunks.append(part.decode() if isinstance(part, bytes) else part)
            return [json.loads(line[6:]) for line in "".join(chunks).splitlines() if line.startswith("data: ")]

        settings = {"agent": "Auto", "provider": "Auto", "memory_enabled": False, "web_search_mode": "Off"}
        try:
            with patch("web_app._settings", return_value=settings), patch("web_app._plan_request", side_effect=planned), patch("web_app._provider_order", return_value=["google"]), patch("web_app._mcp_registry", return_value=web_app.tools), patch("web_app.search_if_needed", return_value=[]), patch.object(web_app.knowledge_base, "retrieve", return_value=[]), patch("web_app.generate_with_fallback", side_effect=fake_generate):
                responses = [await web_app.chat(web_app.ChatRequest(thread_id=thread_id, request_id=rid, message=f"prompt:{rid}")) for thread_id, rid in zip(ids, request_ids)]
                events = await asyncio.gather(*(collect(response) for response in responses))
            for thread_id, request_id, stream in zip(ids, request_ids, events):
                self.assertTrue(stream)
                self.assertTrue(all(event["request_id"] == request_id for event in stream))
                self.assertEqual(next(event["value"]["thread_id"] for event in stream if event["type"] == "completed"), thread_id)
                self.assertIn(f"answer:{request_id}", [event["value"] for event in stream if event["type"] == "delta"])
                self.assertEqual(stream[0]["state"], "thinking")
                self.assertEqual(stream[-1]["state"], "completed")
        finally:
            for thread_id in ids:
                web_app.TEMP_CHATS.pop(thread_id, None)

    async def test_incomplete_response_has_terminal_event_and_can_continue_from_history(self):
        thread_id = uuid.uuid4().hex
        web_app.TEMP_CHATS[thread_id] = []
        request_ids = [uuid.uuid4().hex, uuid.uuid4().hex]
        route = web_app.orchestrator.plan("hello", default_agent="Auto").route
        plan = SimpleNamespace(route=route, prompt="hello", timeout_seconds=10, max_steps=1)
        seen_history = []

        async def planned(*_args):
            return plan

        async def collect(response):
            chunks = []
            async for part in response.body_iterator:
                chunks.append(part.decode() if isinstance(part, bytes) else part)
            return [json.loads(line[6:]) for line in "".join(chunks).splitlines() if line.startswith("data: ")]

        async def incomplete(_providers, _create, _messages, on_token, _fallback, streaming=True):
            await on_token("partial output")
            raise IncompleteResponseError("partial output", "length")

        async def complete(_providers, _create, _messages, on_token, _fallback, streaming=True):
            await on_token("continued"); return "continued", "google"

        def build_messages(_route, _prompt, history, *_args):
            seen_history.extend(history)
            return []

        settings = {"agent": "Auto", "provider": "Auto", "memory_enabled": False, "web_search_mode": "Off"}
        try:
            patches = (
                patch("web_app._settings", return_value=settings),
                patch("web_app._plan_request", side_effect=planned),
                patch("web_app._provider_order", return_value=["google"]),
                patch("web_app._mcp_registry", return_value=web_app.tools),
                patch("web_app.search_if_needed", return_value=[]),
                patch.object(web_app.knowledge_base, "retrieve", return_value=[]),
                patch("web_app._messages", side_effect=build_messages),
                patch("web_app.generate_with_fallback", side_effect=incomplete),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
                first = await web_app.chat(web_app.ChatRequest(thread_id=thread_id, request_id=request_ids[0], message="question"))
                first_events = await collect(first)
                self.assertEqual(first_events[-1]["type"], "incomplete")
                self.assertEqual(web_app.TEMP_CHATS[thread_id][-1]["status"], "incomplete")
                with patch("web_app.generate_with_fallback", side_effect=complete):
                    second = await web_app.chat(web_app.ChatRequest(thread_id=thread_id, request_id=request_ids[1], message="Continue the previous answer"))
                    second_events = await collect(second)
                self.assertEqual(second_events[-1]["type"], "completed")
            self.assertIn(("assistant", "partial output"), seen_history)
            self.assertIn(("user", "question"), seen_history)
        finally:
            web_app.TEMP_CHATS.pop(thread_id, None)

    async def test_concurrent_sqlite_writes_keep_every_message_in_its_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "concurrency.db"
            store = SQLiteStore(path)
            thread_ids = [uuid.uuid4().hex for _ in range(10)]
            for thread_id in thread_ids:
                store.create_conversation("test", thread_id)

            def write(index):
                writer = SQLiteStore(path)
                for message_index in range(12):
                    writer.save_conversation_message(thread_ids[index], "test", "user", f"{index}:{message_index}", f"{index}:{message_index}")

            await asyncio.gather(*(asyncio.to_thread(write, index) for index in range(10)))
            for index, thread_id in enumerate(thread_ids):
                rows = store.get_conversation_messages(thread_id, "test")
                self.assertEqual(len(rows), 12)
                self.assertEqual({row["content"] for row in rows}, {f"{index}:{n}" for n in range(12)})

    async def test_explicit_cancel_stops_only_its_request_while_peer_continues(self):
        thread_ids = [uuid.uuid4().hex, uuid.uuid4().hex]
        request_ids = ["cancel-this-request", "keep-this-request"]
        for thread_id in thread_ids:
            web_app.TEMP_CHATS[thread_id] = []
        cancelled_started = asyncio.Event()
        peer_started = asyncio.Event()
        never = asyncio.Event()
        route = web_app.orchestrator.plan("hello", default_agent="Auto").route
        plan = SimpleNamespace(route=route, prompt="hello", timeout_seconds=30, max_steps=1)

        class Blocking:
            async def astream(self, _messages):
                request_id = current_request_id.get()
                if request_id == request_ids[0]:
                    yield SimpleNamespace(content="partial before cancel")
                    cancelled_started.set()
                    await never.wait()
                else:
                    peer_started.set()
                    yield SimpleNamespace(content=f"response:{request_id}")

        async def collect(response):
            chunks = []
            async for _part in response.body_iterator:
                part = _part.decode() if isinstance(_part, bytes) else _part
                chunks.append(part)
            return chunks

        async def planned(*_args):
            return plan

        settings = {"agent": "Auto", "provider": "Auto", "memory_enabled": False, "web_search_mode": "Off", "streaming": True}
        try:
            with patch("web_app._settings", return_value=settings), patch("web_app._plan_request", side_effect=planned), patch("web_app._provider_order", return_value=["google"]), patch("web_app._mcp_registry", return_value=web_app.tools), patch("web_app.search_if_needed", return_value=[]), patch.object(web_app.knowledge_base, "retrieve", return_value=[]), patch("web_app.factory.create", return_value=Blocking()):
                responses = [await web_app.chat(web_app.ChatRequest(thread_id=thread_id, request_id=request_id, message="disconnect test")) for thread_id, request_id in zip(thread_ids, request_ids)]
                cancelled_consumer = asyncio.create_task(collect(responses[0]))
                peer_consumer = asyncio.create_task(collect(responses[1]))
                await asyncio.gather(cancelled_started.wait(), peer_started.wait())
                self.assertTrue((await web_app.cancel_chat_request(request_ids[0]))["cancelled"])
                cancelled_chunks, peer_chunks = await asyncio.gather(cancelled_consumer, peer_consumer)
                cancelled_events = [json.loads(line[6:]) for line in "".join(cancelled_chunks).splitlines() if line.startswith("data: ")]
                peer_events = [json.loads(line[6:]) for line in "".join(peer_chunks).splitlines() if line.startswith("data: ")]
                self.assertTrue(any(event["type"] == "cancelled" for event in cancelled_events))
                self.assertTrue(any(event["type"] == "delta" and event["value"] == "partial before cancel" for event in cancelled_events))
                self.assertTrue(any(event["type"] == "completed" and event["request_id"] == request_ids[1] for event in peer_events))
                self.assertTrue(any(event["type"] == "delta" and event["value"] == f"response:{request_ids[1]}" for event in peer_events))
            status = provider_health.snapshot()["Google Gemini"]
            self.assertEqual(status["failures"], 0)
            self.assertEqual(status["active_requests"], 0)
            self.assertEqual(status["successes"], 1)
            self.assertEqual(web_app.TEMP_CHATS[thread_ids[0]][-1]["status"], "cancelled")
            self.assertEqual(web_app.TEMP_CHATS[thread_ids[0]][-1]["content"], "partial before cancel")
        finally:
            for thread_id in thread_ids:
                web_app.TEMP_CHATS.pop(thread_id, None)

    async def test_browser_refresh_disconnect_does_not_cancel_or_lose_request(self):
        thread_id = uuid.uuid4().hex
        request_id = "refresh-survives"
        web_app.TEMP_CHATS[thread_id] = []
        started = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()
        route = web_app.orchestrator.plan("hello", default_agent="Auto").route
        plan = SimpleNamespace(route=route, prompt="hello", timeout_seconds=30, max_steps=1)

        class Delayed:
            async def astream(self, _messages):
                started.set()
                await release.wait()
                yield SimpleNamespace(content="saved after refresh")
                finished.set()

        settings = {"agent": "Auto", "provider": "Auto", "memory_enabled": False, "web_search_mode": "Off", "streaming": True}
        try:
            with patch("web_app._settings", return_value=settings), patch("web_app._plan_request", return_value=plan), patch("web_app._provider_order", return_value=["google"]), patch("web_app._mcp_registry", return_value=web_app.tools), patch("web_app.search_if_needed", return_value=[]), patch.object(web_app.knowledge_base, "retrieve", return_value=[]), patch("web_app.factory.create", return_value=Delayed()):
                response = await web_app.chat(web_app.ChatRequest(thread_id=thread_id, request_id=request_id, message="refresh test"))
                async def consume():
                    async for _event in response.body_iterator:
                        pass
                consumer = asyncio.create_task(consume())
                await started.wait()
                active_status = await web_app.get_chat_request_status(request_id)
                self.assertEqual(active_status["state"], "generating")
                consumer.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await consumer
                self.assertIn(request_id, web_app.ACTIVE_CHAT_REQUESTS)
                release.set()
                await asyncio.wait_for(finished.wait(), timeout=2)
                for _ in range(20):
                    if request_id not in web_app.ACTIVE_CHAT_REQUESTS:
                        break
                    await asyncio.sleep(0)
                self.assertNotIn(request_id, web_app.ACTIVE_CHAT_REQUESTS)
                self.assertEqual(web_app.TEMP_CHATS[thread_id][-1]["content"], "saved after refresh")
                recovered = await web_app.get_chat_request_status(request_id)
                self.assertEqual(recovered["state"], "completed")
                self.assertEqual(recovered["partial"], "saved after refresh")
            self.assertEqual(provider_health.snapshot()["Google Gemini"]["successes"], 1)
        finally:
            web_app.ACTIVE_CHAT_REQUESTS.pop(request_id, None)
            web_app.TEMP_CHATS.pop(thread_id, None)

    async def test_concurrent_fallback_does_not_replace_a_peer_success(self):
        peer_entered = asyncio.Event()
        release_peer = asyncio.Event()

        class PeerGoogle:
            async def ainvoke(self, _messages):
                peer_entered.set()
                await release_peer.wait()
                return _Answer("google peer")

        class FailingGoogle:
            async def ainvoke(self, _messages):
                await peer_entered.wait()
                raise ConnectionError("google unavailable for this request")

        peer = asyncio.create_task(self.run_generation(["google"], lambda _: PeerGoogle()))
        await peer_entered.wait()
        fallback = asyncio.create_task(self.run_generation(["google", "groq"], lambda p: FailingGoogle() if p == "google" else _AnswerModel("groq fallback")))
        fallback_result = await fallback
        release_peer.set()
        peer_result = await peer
        self.assertEqual(peer_result[0], "google peer")
        self.assertEqual(fallback_result[0], "groq fallback")


if __name__ == "__main__":
    unittest.main()
