"""Provider-independent streaming with a real non-streaming fallback."""

import asyncio


async def generate(model, messages, on_token):
    parts = []
    stream = getattr(model, "astream", None)
    if callable(stream):
        async for chunk in stream(messages):
            content = getattr(chunk, "content", "")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if content:
                parts.append(content)
                await on_token(content)
        return "".join(parts)

    invoke = getattr(model, "ainvoke", None)
    result = await invoke(messages) if callable(invoke) else await asyncio.to_thread(model.invoke, messages)
    content = getattr(result, "content", str(result))
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if content:
        await on_token(content)
    return content
