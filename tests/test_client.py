import io
import json
from unittest.mock import patch

import pytest

from explain import client as client_mod
from explain.client import ChatRequest, OpenRouterError, complete, stream


def _req():
    return ChatRequest(
        model="deepseek/deepseek-chat-v3-0324:free",
        messages=[{"role": "user", "content": "hi"}],
    )


def test_to_body_includes_web_plugin():
    body = _req().to_body(stream=False)
    assert body["stream"] is False
    assert body["plugins"] == [{"id": "web", "max_results": 5}]
    assert "tools" not in body


def test_to_body_skip_plugin_when_disabled():
    req = ChatRequest(model="m", messages=[], web_search=False)
    body = req.to_body(stream=True)
    assert "plugins" not in body
    assert body["stream"] is True


class _FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


def test_complete_parses_message():
    payload = {"choices": [{"message": {"content": "hello world"}}]}
    fake = _FakeResp(json.dumps(payload).encode())

    with patch.object(client_mod.urllib.request, "urlopen", return_value=fake) as m:
        out = complete(_req(), api_key="sk-test")
        assert out == "hello world"
        sent_req = m.call_args.args[0]
        assert sent_req.headers["Authorization"] == "Bearer sk-test"
        assert sent_req.headers["Content-type"] == "application/json"
        body = json.loads(sent_req.data)
        assert body["stream"] is False


def test_complete_raises_on_http_error():
    import urllib.error
    err = urllib.error.HTTPError(
        url=client_mod.API_URL, code=401, msg="Unauthorized",
        hdrs=None, fp=io.BytesIO(b'{"error":{"message":"bad key"}}'),
    )
    with patch.object(client_mod.urllib.request, "urlopen", side_effect=err):
        with pytest.raises(OpenRouterError) as exc:
            complete(_req(), api_key="sk-bad")
        assert exc.value.status == 401
        assert "bad key" in str(exc.value)


def test_stream_yields_deltas():
    sse = (
        b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n'
        b'data: {"choices":[{"delta":{}}]}\n'
        b'data: [DONE]\n'
    )
    fake = _FakeResp(sse)

    with patch.object(client_mod.urllib.request, "urlopen", return_value=fake):
        chunks = list(stream(_req(), api_key="sk-test"))
    assert chunks == ["Hel", "lo"]


def test_stream_ignores_comments_and_blank():
    sse = (
        b': keepalive\n'
        b'\n'
        b'data: {"choices":[{"delta":{"content":"x"}}]}\n'
        b'data: [DONE]\n'
    )
    fake = _FakeResp(sse)
    with patch.object(client_mod.urllib.request, "urlopen", return_value=fake):
        chunks = list(stream(_req(), api_key="sk-test"))
    assert chunks == ["x"]
