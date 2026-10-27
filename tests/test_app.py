import asyncio
import os

import httpx
import pytest

import app as service

SECRET = 'this-is-a-long-test-secret-key-value-12345'


def run(coro):
    return asyncio.run(coro)


async def call(data, path=None, origin=None):
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    if origin:
        headers["origin"] = origin
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=service.app), base_url="http://testserver"
    ) as client:
        return await client.post(path or f"/{SECRET}/mcp", json=data, headers=headers)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("MCP_SECRET_PATH", SECRET)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("MAX_CALLS_PER_DAY", "15")
    service._recent_requests.clear()


@pytest.mark.parametrize("url", [
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=25s",
    "https://youtube.com/shorts/dQw4w9WgXcQ",
    "https://m.youtube.com/live/dQw4w9WgXcQ",
])
def test_youtube_url(url):
    assert service.canonical_youtube_url(url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.parametrize("url", [
    "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/playlist?list=PL999",
    "https://127.0.0.1/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=short",
    "https://youtube.com@evil.test/shorts/dQw4w9WgXcQ",
    "file:///etc/passwd",
])
def test_disallowed_urls(url):
    with pytest.raises(ValueError):
        service.canonical_youtube_url(url)


def test_handshake_tools_list():
    a = run(call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}))
    assert a.status_code == 200
    assert a.json()["result"]["protocolVersion"] == "2025-11-25"
    b = run(call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    assert b.status_code == 200
    assert {x["name"] for x in b.json()["result"]["tools"]} == {
        "analyze_youtube_video", "inspect_youtube_moment", "youtube_mcp_status"
    }


def test_missing_key_gives_tool_error():
    r = run(call({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "analyze_youtube_video", "arguments": {
            "url": "https://www.youtube.com/shorts/dQw4w9WgXcQ", "mode": "visual"
        }}}))
    assert r.status_code == 200
    assert r.json()["result"]["isError"] is True
    assert "GEMINI_API_KEY" in r.json()["result"]["content"][0]["text"]


def test_reject_bad_secret_and_origin():
    a = run(call({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, path="/wrong-token/mcp"))
    assert a.status_code == 404
    b = run(call({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, origin="https://evil.test"))
    assert b.status_code == 403


def test_notification():
    a = run(call({"jsonrpc": "2.0", "method": "notifications/initialized"}))
    assert a.status_code == 202


def test_bad_timestamp():
    a = run(call({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "inspect_youtube_moment", "arguments": {
            "url": "https://youtu.be/dQw4w9WgXcQ", "timestamp": "99:99", "question": "What?"
        }}}))
    assert a.json()["result"]["isError"] is True


def test_visual_dispatch(monkeypatch):
    async def fake_backend(url, prompt, mode):
        assert url == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        assert 'визуальные сцены' in prompt
        assert mode == 'visual'
        return 'В 00:05 показан экран приложения.'
    monkeypatch.setattr(service, 'analyze_with_gemini', fake_backend)
    a = run(call({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "analyze_youtube_video", "arguments": {
            "url": "https://youtu.be/dQw4w9WgXcQ", "mode": "visual"
        }}}))
    assert a.json()["result"]["isError"] is False
    assert '00:05' in a.json()["result"]["content"][0]["text"]


def test_gemini_video_payload_uses_visual_media_not_web_page(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key-not-real")
    received = {}

    def mock_handler(request: httpx.Request):
        import json
        received["url"] = str(request.url)
        received["api_key"] = request.headers.get("x-goog-api-key")
        received["payload"] = json.loads(request.content)
        return httpx.Response(200, json={
            "status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "В кадре видна надпись. [00:03]"}]}]
        })

    client_class = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(mock_handler)
        return client_class(*args, **kwargs)

    monkeypatch.setattr(service.httpx, "AsyncClient", client_factory)
    result = run(service.analyze_with_gemini(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Опиши кадры", "visual"
    ))
    assert "В кадре видна" in result
    assert received["api_key"] == "fake-test-key-not-real"
    assert received["payload"]["input"][0]["uri"].startswith("https://www.youtube.com/watch?")
    assert received["payload"]["input"][1]["text"] == "Опиши кадры"
    assert received["url"].endswith("/v1beta/interactions")


def test_gemini_rate_limit_can_block_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("MAX_CALLS_PER_DAY", "1")
    service._recent_requests.append(service.time.monotonic())
    with pytest.raises(RuntimeError, match="лимит"):
        run(service.analyze_with_gemini("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "test", "quick"))
