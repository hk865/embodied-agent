"""Offline wire-contract checks for the pinned RPent/DeepSeek integration."""

from __future__ import annotations

import base64
import asyncio
from decimal import Decimal
import json
import socket
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "workspace/vla_baselines/repos/rpent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepseek_api import (
    BASE_URL,
    MODEL_ID,
    REQUEST_RESERVATION_USD,
    request_reservation_usd,
    RequestBudgetGuard,
    peak_usage_cost,
    build_deepseek_model,
    install_compatibility,
)
from rpent.planner.api_loop import ApiAgentLoop
from rpent.tools.toolkit import ToolResult


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6"
    "fVwAAAAASUVORK5CYII="
)
FINISH = {"status": "success", "summary": "offline tool chain completed"}


class Events:
    enabled = True

    def emit(self, event):
        pass


class FakeToolkit:
    """Only the robot boundary is fake; the upstream API loop is unchanged."""

    state = None

    def __init__(self):
        self.calls = []

    def get_tools_spec(self):
        return [
            {
                "name": "observe",
                "description": "Read a camera image",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "finish",
                "description": "Finish the task",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["status", "summary"],
                },
            },
        ]

    def execute_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "observe":
            return ToolResult(name, {"object": "cup", "_image_bytes": PNG})
        if name == "finish":
            return ToolResult(name, {"_finish": True, **arguments})
        raise AssertionError(f"Unexpected tool: {name}")

    def cancel_active_and_wait(self):
        pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """A socket attempt fails, even if a future edit bypasses MockTransport."""
    def deny_connect(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline checks")

    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_connect)
    monkeypatch.setenv("PYDANTIC_AI_NO_BANNER", "1")
    monkeypatch.setenv("DEEPSEEK_MAX_COST_USD", "2")
    monkeypatch.setenv("DEEPSEEK_BUDGET_REPORT_PATH", str(tmp_path / "budget.json"))


def reply(tool_name, arguments, *, thinking):
    return {
        "id": f"offline-{tool_name}",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    **({"reasoning_content": "offline reasoning"} if thinking else {}),
                    "tool_calls": [
                        {
                            "id": f"call-{tool_name}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def stream_reply(response):
    """Serve the same completion using DeepSeek's documented SSE shape."""
    choice = response["choices"][0]
    message = choice["message"]
    shared = {key: response[key] for key in ("id", "created", "model")}
    shared["object"] = "chat.completion.chunk"
    deltas = []
    if message.get("reasoning_content"):
        deltas.append({"reasoning_content": message["reasoning_content"]})
    deltas.append({"tool_calls": [{"index": 0, **message["tool_calls"][0]}]})
    chunks = [
        {**shared, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
        for delta in deltas
    ]
    chunks.append(
        {
            **shared,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            "usage": response["usage"],
        }
    )
    events = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
    return events + "data: [DONE]\n\n"


@pytest.mark.parametrize("effort", ["high", "none"])
@pytest.mark.parametrize("max_tokens", [512, 10000, 32000])
def test_real_api_loop_preserves_images_tools_and_reasoning(effort, max_tokens):
    requests = []

    def handle(request):
        assert str(request.url) == BASE_URL + "/chat/completions"
        body = json.loads(request.content)
        requests.append(body)
        name, arguments = ("observe", {}) if len(requests) == 1 else ("finish", FINISH)
        response = reply(name, arguments, thinking=effort == "high")
        if body.get("stream"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=stream_reply(response),
            )
        return httpx.Response(200, json=response)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    model = build_deepseek_model(api_key="offline-placeholder", http_client=client)
    toolkit = FakeToolkit()
    planner = ApiAgentLoop(
        model=model,
        dashboard_events=Events(),
        reasoning_effort=effort,
        max_tokens=max_tokens,
        timeout_s=5,
    )
    result = planner.solve(
        system_prompt="Observe, then finish.",
        user_message="Run the offline contract check.",
        toolkit=toolkit,
        max_turns=3,
    )
    assert result.error is None, result.error
    assert result.finish_result == {"_finish": True, **FINISH}
    assert toolkit.calls == [("observe", {}), ("finish", FINISH)]
    assert len(requests) == 2
    for body in requests:
        assert body["model"] == "deepseek-flash"
        assert body["reasoning_effort"] == effort
        assert body["max_tokens"] == max_tokens
        assert "max_completion_tokens" not in body
        assert body.get("tool_choice") != "required"
        assert all(not item["function"].get("strict") for item in body["tools"])
    images = [
        part
        for message in requests[1]["messages"]
        if message["role"] == "user" and isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    ]
    assert len(images) == 1
    assert images[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assistant = next(m for m in requests[1]["messages"] if m["role"] == "assistant")
    if effort == "high":
        assert assistant["reasoning_content"] == "offline reasoning"
    assert result.stats["turns_used"] == 2


def test_endpoint_override_is_rejected_before_credentials_or_request(monkeypatch):
    from rpent.planner import base

    original = base.build_api_model
    monkeypatch.setattr(base, "build_api_model", original)
    install_compatibility()
    with pytest.raises(ValueError, match="official HTTPS endpoint"):
        base.build_api_model(MODEL_ID, "https://unapproved.invalid")


def test_compatibility_factory_only_handles_current_deepseek_name(monkeypatch):
    from rpent.planner import base

    sentinel = object()
    calls = []

    def upstream(model, base_url=None):
        calls.append((model, base_url))
        return sentinel

    monkeypatch.setattr(base, "build_api_model", upstream)
    install_compatibility()
    installed = base.build_api_model
    install_compatibility()
    assert base.build_api_model is installed
    assert base.build_api_model("another-provider:another-model", None) is sentinel
    assert calls == [("another-provider:another-model", None)]


@pytest.mark.parametrize("maximum,reservation,allowed", [
    (8192, Decimal("0.3244032"), 6),
    (10000, Decimal("0.3265728"), 6),
    (32000, Decimal("0.3529728"), 5),
])
def test_next_request_is_blocked_using_the_actual_wire_limit(maximum, reservation, allowed):
    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(200, json={"ok": True})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            body = {"model": "deepseek-flash", "max_tokens": maximum}
            for _ in range(allowed):
                response = await client.post(BASE_URL + "/chat/completions", json=body)
                assert response.status_code == 200
            with pytest.raises(RuntimeError, match="cost cap reached before HTTP send"):
                await client.post(BASE_URL + "/chat/completions", json=body)
            guard = client.event_hooks["request"][-1]
            assert guard.request_attempts == allowed
            assert guard.reserved_usd == reservation * allowed

    asyncio.run(run())
    assert len(attempts) == allowed
    assert request_reservation_usd(maximum) == reservation
    assert REQUEST_RESERVATION_USD == Decimal("0.3529728")


def test_sdk_retries_consume_reservations_and_failures_do_not_refund():
    from openai import APIConnectionError, InternalServerError

    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(
            500,
            headers={"retry-after-ms": "1"},
            json={"error": {"message": "offline simulated failure", "type": "server_error"}},
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            model = build_deepseek_model(api_key="offline-placeholder", http_client=client)
            kwargs = {
                "model": "deepseek-flash",
                "messages": [{"role": "user", "content": "offline"}],
                "max_tokens": 8192,
            }
            # Default SDK policy: one attempt plus two retries per call.
            for _ in range(2):
                with pytest.raises(InternalServerError):
                    await model.client.chat.completions.create(**kwargs)
            with pytest.raises(RuntimeError, match="cost cap reached"):
                await model.client.chat.completions.create(**kwargs)
            guard = client.event_hooks["request"][-1]
            assert guard.request_attempts == 6
            assert guard.reserved_usd == Decimal("1.9464192")

    asyncio.run(run())
    assert len(attempts) == 6


@pytest.mark.parametrize(
    "body",
    [
        {"model": "deepseek-flash"},
        {"model": "deepseek-flash", "max_tokens": 32001},
        {"model": "deepseek-flash", "max_tokens": 32768},
        {"model": "deepseek-flash", "max_tokens": 0},
        {"model": "deepseek-flash", "max_tokens": True},
        {"model": "deepseek-flash", "max_tokens": "8192"},
        {"model": "another-model", "max_tokens": 8192},
        {"model": "deepseek-flash", "max_tokens": 8192, "max_completion_tokens": 8192},
    ],
)
def test_invalid_output_reservation_is_blocked_before_transport(body):
    attempts = []

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: attempts.append(request))
        ) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            with pytest.raises(ValueError, match="integer max_tokens"):
                await client.post(BASE_URL + "/chat/completions", json=body)
            assert client.event_hooks["request"][-1].reserved_usd == 0

    asyncio.run(run())
    assert attempts == []


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com/chat/completions",
        "https://unapproved.invalid/chat/completions",
        "https://api.deepseek.com:444/chat/completions",
        "https://user:password@api.deepseek.com/chat/completions",
        "https://api.deepseek.com/models",
        "https://api.deepseek.com/chat/completions?redirect=1",
    ],
)
def test_request_guard_rejects_other_destinations_before_transport(url):
    attempts = []

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: attempts.append(request))
        ) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            with pytest.raises(ValueError, match="official chat endpoint"):
                await client.post(url, json={"model": "deepseek-flash", "max_tokens": 8192})
            assert client.event_hooks["request"][-1].reserved_usd == 0

    asyncio.run(run())
    assert attempts == []


@pytest.mark.parametrize("limit", [None, "", "0", "-1", "NaN", "Infinity", "not-money"])
def test_execution_requires_a_positive_explicit_cost_cap(monkeypatch, limit):
    if limit is None:
        monkeypatch.delenv("DEEPSEEK_MAX_COST_USD", raising=False)
    else:
        monkeypatch.setenv("DEEPSEEK_MAX_COST_USD", limit)
    with pytest.raises(ValueError, match="positive explicit API cost cap"):
        build_deepseek_model(api_key="offline-placeholder")


def test_successful_usage_settles_and_survives_a_new_guard():
    attempts = []

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=reply("finish", FINISH, thinking=False))
        )) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            for _ in range(10):
                attempts.append(await client.post(BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": 8192}))
        guard = RequestBudgetGuard("2")
        assert guard.request_attempts == 10
        assert guard.reserved_usd == Decimal("0.000090")
        data = json.loads(guard.path.read_text())
        assert data["models"] == ["deepseek-flash"]
        assert data["unsettled_reservations_usd"] == "0.000000"
        assert all(e["status"] == "settled" for e in data["attempts"].values())

    asyncio.run(run())
    assert len(attempts) == 10


def test_reservations_survive_restart_and_cannot_raise_the_cap():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            for _ in range(6):
                await client.post(BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": 8192})
        guard = RequestBudgetGuard("2")
        assert guard.request_attempts == 6
        request = httpx.Request("POST", BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": 8192})
        with pytest.raises(RuntimeError, match="cost cap reached"):
            await guard(request)
        with pytest.raises(ValueError, match="cap differs"):
            RequestBudgetGuard("3")
    asyncio.run(run())


@pytest.mark.parametrize("complete", [True, False])
def test_stream_usage_settles_only_after_done(complete):
    async def run():
        payload = stream_reply(reply("finish", FINISH, thinking=True))
        if not complete:
            payload = payload.replace("data: [DONE]\n\n", "")
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=payload
        ))) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            response = await client.post(BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": 8192})
            assert "offline reasoning" in response.text
            guard = client.event_hooks["request"][-1]
            assert guard.reserved_usd == (Decimal("0.000009") if complete else request_reservation_usd(8192))
    asyncio.run(run())


@pytest.mark.parametrize("wire_limit,reported_output", [(8192, 9000), (10000, 10001), (32000, 32001)])
def test_malformed_usage_does_not_release_reservation(wire_limit, reported_output):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"model": "deepseek-flash", "usage": {"prompt_tokens": 10, "completion_tokens": reported_output}}
        ))) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            with pytest.raises(ValueError, match="reserved token limits"):
                await client.post(BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": wire_limit})
            assert RequestBudgetGuard("2").reserved_usd == request_reservation_usd(wire_limit)
    asyncio.run(run())


def test_cache_breakdown_is_used_only_when_it_reconciles():
    valid = {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 8, "prompt_cache_miss_tokens": 2}
    assert peak_usage_cost(valid) == Decimal("0.000006648")
    assert peak_usage_cost({**valid, "prompt_cache_miss_tokens": 3}) == Decimal("0.000009")


def test_authorized_cap_increase_preserves_attempts_and_unsettled_reservations():
    async def run():
        guard = RequestBudgetGuard("2")
        await guard(httpx.Request("POST", BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": 8192}))
        guard.authorize_limit_increase("40")
        restored = RequestBudgetGuard("40")
        assert restored.request_attempts == 1
        assert restored.reserved_usd == request_reservation_usd(8192)
        data = json.loads(restored.path.read_text())
        assert data["authorized_limit_changes"][0]["limit_usd"] == "2"
        assert data["authorized_limit_changes"][0]["new_limit_usd"] == "40"
        with pytest.raises(ValueError, match="cap differs"):
            RequestBudgetGuard("2")
    asyncio.run(run())


@pytest.mark.parametrize("wire_limit,reported_output,version,expected_reservation,expected_cost,expected_total", [
    (10000, 9000, "v2-output-10000", "0.6509760", "0.010803", "0.3352062"),
    (32000, 30000, "v3-output-32000", "0.6773760", "0.036003", "0.3604062"),
])
def test_wire_limit_and_large_output_settle_without_changing_legacy_entry(
    monkeypatch, wire_limit, reported_output, version, expected_reservation, expected_cost, expected_total
):
    import os

    path = Path(os.environ["DEEPSEEK_BUDGET_REPORT_PATH"])
    legacy = {
        "status": "reserved", "accounted_usd": "0.3244032",
        "max_output_tokens": 8192, "started_at_utc": "2026-11-01T16:00:00+00:00",
    }
    path.write_text(json.dumps({"schema_version": 1, "limit_usd": "40", "attempts": {"legacy": legacy}}))
    monkeypatch.setenv("DEEPSEEK_MAX_COST_USD", "40")
    monkeypatch.setenv("DEEPSEEK_CONFIG_VERSION", version)
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["max_tokens"] == wire_limit
        reserved = json.loads(path.read_text())
        assert Decimal(reserved["accounted_upper_bound_usd"]) == Decimal(expected_reservation)
        return httpx.Response(200, json={
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "length", "message": {"content": "response-body-must-not-save"}},
                        {"finish_reason": "not-a-documented-enum"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": reported_output, "total_tokens": 10 + reported_output},
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            await client.post(BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": wire_limit})
        data = json.loads(path.read_text())
        assert data["attempts"]["legacy"] == legacy
        assert data["limit_usd"] == "40"
        assert data["request_attempts"] == 2
        current = next(value for key, value in data["attempts"].items() if key != "legacy")
        assert current["status"] == "settled"
        assert current["max_output_tokens"] == wire_limit
        assert current["configuration_version"] == version
        assert current["finish_reasons"] == ["length"]
        assert "response-body-must-not-save" not in path.read_text()
        assert Decimal(current["accounted_usd"]) == Decimal(expected_cost)
        assert Decimal(data["accounted_upper_bound_usd"]) == Decimal(expected_total)

    asyncio.run(run())
    assert len(requests) == 1


def test_finish_reason_without_usage_keeps_full_reservation():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"choices": [{"finish_reason": "length"}]}
        ))) as client:
            build_deepseek_model(api_key="offline-placeholder", http_client=client)
            await client.post(BASE_URL + "/chat/completions", json={"model": "deepseek-flash", "max_tokens": 10000})
            guard = client.event_hooks["request"][-1]
            assert guard.reserved_usd == request_reservation_usd(10000)
            entry = next(iter(json.loads(guard.path.read_text())["attempts"].values()))
            assert entry["status"] == "reserved"
            assert entry["finish_reasons"] == ["length"]
    asyncio.run(run())
