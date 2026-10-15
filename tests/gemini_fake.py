"""A stand-in Gemini client for tests. No test ever talks to the real API."""

import asyncio
from types import SimpleNamespace


class FakeInteractions:
    """Plays back a script: each item is a JSON string to return, an exception to raise,
    or a number of seconds to hang (to test the wall-clock deadline) before returning
    `hang_result`."""

    def __init__(self, script, hang_result="{}"):
        self.script = list(script)
        self.hang_result = hang_result
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, (int, float)):
            await asyncio.sleep(item)
            item = self.hang_result
        return SimpleNamespace(output_text=item)


def fake_client(*script, hang_result="{}"):
    return SimpleNamespace(aio=SimpleNamespace(interactions=FakeInteractions(script, hang_result)))


class FakeStatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
