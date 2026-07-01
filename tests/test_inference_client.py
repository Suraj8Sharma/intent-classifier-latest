from unittest.mock import patch

import httpx
import pytest

import backend.inference.client as client_module
from backend.inference.client import classify_call, generate_call, llm_call


class _FakeClientRaising:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, *args, **kwargs):
        raise self._exc


class _FakeClientOK:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json):
        class _Response:
            text = f"echo:{json['prompt']}"

        return _Response()


async def test_llm_call_raises_timeout_error_on_httpx_timeout():
    with patch(
        "backend.inference.client.httpx.AsyncClient",
        lambda *a, **kw: _FakeClientRaising(httpx.ConnectTimeout("simulated timeout")),
    ):
        with pytest.raises(TimeoutError):
            await llm_call("hi", timeout_ms=200)


async def test_llm_call_raises_connection_error_on_httpx_connect_error():
    with patch(
        "backend.inference.client.httpx.AsyncClient",
        lambda *a, **kw: _FakeClientRaising(httpx.ConnectError("simulated unreachable")),
    ):
        with pytest.raises(ConnectionError):
            await llm_call("hi", timeout_ms=800)


async def test_classify_and_generate_call_delegate_to_llm_call():
    with patch("backend.inference.client.httpx.AsyncClient", lambda *a, **kw: _FakeClientOK()):
        assert await classify_call("classify this") == "echo:classify this"
        assert await generate_call("generate this") == "echo:generate this"


def test_client_module_has_no_module_level_session_cache():
    for name, value in vars(client_module).items():
        assert not isinstance(value, httpx.AsyncClient), f"found module-level client: {name}"
