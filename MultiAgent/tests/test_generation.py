import unittest

from generation import EmptyResponseError, ProvidersUnavailableError, generate, generate_with_fallback
from provider_router import provider_health


class Chunk:
    def __init__(self, content):
        self.content = content


class StreamingModel:
    async def astream(self, messages):
        yield Chunk("Hello")
        yield Chunk(" there")


class InvokeModel:
    async def ainvoke(self, messages):
        return Chunk("Complete answer")


class FailingModel:
    async def astream(self, messages):
        raise RuntimeError("provider failure")
        yield


class EmptyModel:
    async def astream(self, messages):
        yield Chunk("")


class ClosingModel:
    def __init__(self):
        self.closed = False

    async def astream(self, messages):
        try:
            yield Chunk(" ")
        finally:
            self.closed = True


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        provider_health.reset()

    async def test_streams_chunks(self):
        received = []
        async def emit(token):
            received.append(token)
        self.assertEqual(await generate(StreamingModel(), [], emit), "Hello there")
        self.assertEqual(received, ["Hello", " there"])

    async def test_non_streaming_fallback(self):
        received = []
        async def emit(token):
            received.append(token)
        self.assertEqual(await generate(InvokeModel(), [], emit), "Complete answer")
        self.assertEqual(received, ["Complete answer"])

    async def test_provider_errors_are_propagated(self):
        async def emit(token):
            self.fail("No partial content expected")
        with self.assertRaisesRegex(RuntimeError, "provider failure"):
            await generate(FailingModel(), [], emit)

    async def test_empty_stream_is_an_error(self):
        async def emit(token):
            self.fail("Empty chunks must not be emitted")
        with self.assertRaises(EmptyResponseError):
            await generate(EmptyModel(), [], emit)

    async def test_empty_stream_closes_and_falls_back(self):
        created = []
        async def emit(token):
            return None
        async def notice(provider):
            return None
        def create(provider):
            model = EmptyModel() if provider == "google" else StreamingModel()
            created.append(model)
            return model
        response, provider = await generate_with_fallback(
            ["google", "groq"], create, [], emit, notice, streaming=True
        )
        self.assertEqual((response, provider), ("Hello there", "groq"))
        self.assertTrue(created[0].__class__ is EmptyModel)

    async def test_empty_stream_iterator_is_closed(self):
        model = ClosingModel()
        async def emit(token):
            return None
        with self.assertRaises(EmptyResponseError):
            await generate(model, [], emit)
        self.assertTrue(model.closed)

    async def test_falls_back_to_next_configured_provider(self):
        created = []
        notices = []
        received = []
        async def emit(token):
            received.append(token)
        async def notice(provider):
            notices.append(provider)
        def create(provider):
            created.append(provider)
            return FailingModel() if provider == "google" else StreamingModel()
        response, provider = await generate_with_fallback(
            ["google", "groq"], create, [], emit, notice, streaming=True
        )
        self.assertEqual((response, provider), ("Hello there", "groq"))
        self.assertEqual(created, ["google", "groq"])
        self.assertEqual(notices, ["groq"])
        self.assertEqual(received, ["Hello", " there"])

    async def test_quota_exhaustion_falls_through_multiple_providers_and_records_cooldown(self):
        class QuotaError(Exception):
            status_code = 429
            headers = {"Retry-After": "15"}
        created = []
        async def emit(_): pass
        async def notice(_): pass
        def create(provider):
            created.append(provider)
            if provider == "google":
                async def fail(self, _): raise QuotaError("private provider detail")
                return type("QuotaModel", (), {"ainvoke": fail})()
            if provider == "groq":
                return FailingModel()
            return StreamingModel()
        response, provider = await generate_with_fallback(
            ["google", "groq", "openrouter"], create, [], emit, notice, streaming=True
        )
        self.assertEqual((response, provider), ("Hello there", "openrouter"))
        self.assertEqual(created, ["google", "groq", "openrouter"])
        google = provider_health.snapshot()["Google Gemini"]
        self.assertEqual(google["quota_errors"], 1)
        self.assertGreaterEqual(google["cooldown_seconds"], 14)
        self.assertEqual(google["last_error_type"], "QuotaError")

    async def test_invalid_credentials_skip_provider_without_repeating_it(self):
        class AuthError(Exception):
            status_code = 401
        created = []
        async def emit(_): pass
        async def notice(_): pass
        def create(provider):
            created.append(provider)
            async def fail(self, _): raise AuthError()
            return type("AuthModel", (), {"ainvoke": fail})() if provider == "google" else StreamingModel()
        response, provider = await generate_with_fallback(["google", "google", "groq"], create, [], emit, notice, streaming=True)
        self.assertEqual((response, provider), ("Hello there", "groq"))
        self.assertEqual(created, ["google", "groq"])
        self.assertEqual(provider_health.snapshot()["Google Gemini"]["state"], "credentials")

    async def test_cooled_provider_is_skipped_and_all_cooled_returns_friendly_error(self):
        class RateLimit(Exception):
            status_code = 429
        started = provider_health.begin("google")
        provider_health.failure("google", started, RateLimit(), status=429)
        created = []
        async def emit(_): pass
        async def notice(_): pass
        def create(provider):
            created.append(provider)
            return StreamingModel()
        response, provider = await generate_with_fallback(["google", "groq"], create, [], emit, notice, streaming=True)
        self.assertEqual((response, provider), ("Hello there", "groq"))
        self.assertEqual(created, ["groq"])
        started = provider_health.begin("groq")
        provider_health.failure("groq", started, RateLimit(), status=429)
        with self.assertRaisesRegex(ProvidersUnavailableError, "try again shortly"):
            await generate_with_fallback(["google", "groq"], create, [], emit, notice, streaming=True)

    async def test_timeout_falls_back_and_all_failed_providers_return_friendly_error(self):
        created = []
        async def emit(_): pass
        async def notice(_): pass
        def create(provider):
            created.append(provider)
            if provider == "google":
                async def fail(self, _): raise TimeoutError()
                return type("TimeoutModel", (), {"ainvoke": fail})()
            async def fail(self, _): raise ConnectionError()
            return type("NetworkModel", (), {"ainvoke": fail})()
        with self.assertRaisesRegex(ProvidersUnavailableError, "All configured AI providers"):
            await generate_with_fallback(["google", "groq"], create, [], emit, notice, streaming=False)
        self.assertEqual(created, ["google", "groq"])

    async def test_ordinary_model_refusal_is_returned_without_failover(self):
        created = []
        async def emit(_): pass
        async def notice(_): pass
        def create(provider):
            created.append(provider)
            async def answer(self, _):
                return Chunk("I can't help with that request.")
            return type("RefusalModel", (), {"ainvoke": answer})()
        answer, provider = await generate_with_fallback(["google", "groq"], create, [], emit, notice, streaming=False)
        self.assertEqual((answer, provider), ("I can't help with that request.", "google"))
        self.assertEqual(created, ["google"])

    async def test_successful_usage_is_counted_without_prompt_logging(self):
        class UsageModel:
            async def ainvoke(self, _):
                result = Chunk("OK")
                result.usage_metadata = {"input_tokens": 10, "output_tokens": 3}
                return result
        async def emit(_): pass
        async def notice(_): pass
        await generate_with_fallback(["google"], lambda _: UsageModel(), [], emit, notice, streaming=False)
        status = provider_health.snapshot()["Google Gemini"]
        self.assertEqual((status["input_tokens"], status["output_tokens"], status["successes"]), (10, 3, 1))


if __name__ == "__main__":
    unittest.main()
