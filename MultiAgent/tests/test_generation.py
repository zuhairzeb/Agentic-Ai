import unittest

from generation import EmptyResponseError, generate, generate_with_fallback


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


if __name__ == "__main__":
    unittest.main()
