#!/usr/bin/env python3
"""Run the unchanged RPent API planner with the current DeepSeek Flash model.

The pinned SDK predates the ``deepseek-flash`` name. This process-local model
factory supplies its Chat Completions profile without editing RPent or the SDK.
Credentials come only from ``DEEPSEEK_API_KEY``; this module never reads key files.
See https://api-docs.deepseek.com/api/create-chat-completion/ for the wire contract.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "deepseek:deepseek-flash"
MODEL_NAME = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_OUTPUT_TOKENS = 32000
# Conservative request reservation, checked against official pricing 2026-11-01:
# the full 1,048,576-token context as input plus a separate full output allowance.
# This deliberately overcounts the shared context; it is not a billing estimate.
def request_reservation_usd(maximum: int) -> Decimal:
    """Reserve for the exact requested output cap, including the full input bound."""
    if type(maximum) is not int or not 1 <= maximum <= MAX_OUTPUT_TOKENS:
        raise ValueError("DeepSeek Flash requires integer max_tokens from 1 to 32000")
    return (Decimal(1_048_576) * Decimal("0.30") + Decimal(maximum) * Decimal("1.20")) / Decimal(1_000_000)


REQUEST_RESERVATION_USD = request_reservation_usd(MAX_OUTPUT_TOKENS)


def peak_usage_cost(usage: dict, maximum: int = MAX_OUTPUT_TOKENS) -> Decimal:
    """Use verified cache categories at peak rates, otherwise charge all input as miss."""
    prompt, output = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if (type(prompt) is not int or type(output) is not int or not 0 <= prompt <= 1_048_576
            or not 0 <= output <= maximum):
        raise ValueError("DeepSeek response usage is outside the reserved token limits")
    hit, miss = usage.get("prompt_cache_hit_tokens"), usage.get("prompt_cache_miss_tokens")
    if type(hit) is not int or type(miss) is not int or min(hit, miss) < 0 or hit + miss != prompt:
        hit, miss = 0, prompt
    return (Decimal(hit) * Decimal("0.006") + Decimal(miss) * Decimal("0.30") + Decimal(output) * Decimal("1.20")) / Decimal(1_000_000)


class RequestBudgetGuard:
    """Reserve a conservative API cost before each HTTP attempt, including retries.

    Reservations are never refunded after an HTTP error. The bound assumes the
    published official Flash context contract and peak prices above. It excludes
    local GPU cost and is not an exact bill or a guarantee against price changes.
    """

    def __init__(self, max_cost_usd: str):
        try:
            self.max_cost_usd = Decimal(max_cost_usd)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("DeepSeek requires a positive explicit API cost cap") from None
        if not self.max_cost_usd.is_finite() or self.max_cost_usd <= 0:
            raise ValueError("DeepSeek requires a positive explicit API cost cap")
        ledger = os.environ.get("DEEPSEEK_BUDGET_REPORT_PATH")
        if not ledger:
            raise ValueError("DeepSeek requires an explicit persistent budget ledger")
        self.path = Path(ledger).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked() as data:
            self._summarize(data)

    @contextmanager
    def _locked(self):
        """Serialize the durable read/check/update before any request is sent."""
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                data = json.loads(self.path.read_text())
                if data.get("schema_version") != 1 or Decimal(data["limit_usd"]) != self.max_cost_usd:
                    raise ValueError("Existing DeepSeek ledger version or cost cap differs")
                if not isinstance(data.get("attempts"), dict):
                    raise ValueError("Existing DeepSeek budget ledger is invalid")
            else:
                data = {"schema_version": 1, "limit_usd": str(self.max_cost_usd), "attempts": {}}
            yield data
            self._summarize(data)
            fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w") as handle:
                    json.dump(data, handle, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                directory = os.open(self.path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def _summarize(self, data):
        entries = list(data["attempts"].values())
        accounted = sum((Decimal(e["accounted_usd"]) for e in entries), Decimal(0))
        if not accounted.is_finite() or accounted < 0 or accounted > self.max_cost_usd:
            raise ValueError("Existing DeepSeek budget ledger exceeds its cap")
        settled = sum((Decimal(e["accounted_usd"]) for e in entries if e["status"] == "settled"), Decimal(0))
        data.update(accounted_upper_bound_usd=str(accounted), settled_peak_usd=str(settled),
                    unsettled_reservations_usd=str(accounted - settled), request_attempts=len(entries),
                    models=sorted({e["model"] for e in entries if e.get("model")}),
                    updated_at_utc=datetime.now(timezone.utc).isoformat())
        self.reserved_usd = accounted
        self.request_attempts = len(entries)

    def authorize_limit_increase(self, new_limit: str) -> None:
        """Apply an explicitly authorized cap change without dropping past attempts.

        This is an administrative operation, never called by model construction.
        Successful historical usage is reconciled under the same peak-price
        policy used for new requests; failures retain their full reservation.
        """
        value = Decimal(new_limit)
        if not value.is_finite() or value <= self.max_cost_usd:
            raise ValueError("Authorized new limit must exceed the existing cap")
        with self._locked() as data:
            previous = {"limit_usd": data["limit_usd"], "accounted_upper_bound_usd": data.get("accounted_upper_bound_usd"),
                        "request_attempts": len(data["attempts"]), "authorized_at_utc": datetime.now(timezone.utc).isoformat()}
            for entry in data["attempts"].values():
                if entry["status"] == "settled":
                    cost = peak_usage_cost(entry["usage"], entry["max_output_tokens"])
                    entry.setdefault("previous_accounted_usd", entry["accounted_usd"])
                    entry.update(accounted_usd=str(cost), settlement_policy="reported_cache_peak_rates")
            previous["new_limit_usd"] = str(value)
            data.setdefault("authorized_limit_changes", []).append(previous)
            data["limit_usd"] = str(value)
            self.max_cost_usd = value

    async def __call__(self, request: Any) -> None:
        """Validate the destination and request limit before reserving funds."""
        import json

        url = request.url
        if (
            request.method != "POST"
            or url.scheme != "https"
            or url.host != "api.deepseek.com"
            or url.port not in (None, 443)
            or url.username
            or url.password
            or url.path != "/chat/completions"
            or url.query
        ):
            raise ValueError("DeepSeek requests require the official chat endpoint")
        try:
            body = json.loads(await request.aread())
        except (ValueError, TypeError):
            raise ValueError("DeepSeek request must contain a JSON object") from None
        if not isinstance(body, dict):
            raise ValueError("DeepSeek request must contain a JSON object")
        maximum = body.get("max_tokens")
        if (
            body.get("model") != MODEL_NAME
            or type(maximum) is not int
            or not 1 <= maximum <= MAX_OUTPUT_TOKENS
            or "max_completion_tokens" in body
        ):
            raise ValueError("DeepSeek Flash requires integer max_tokens from 1 to 32000")
        reservation = request_reservation_usd(maximum)
        with self._locked() as data:
            self._summarize(data)
            if self.reserved_usd + reservation > self.max_cost_usd:
                raise RuntimeError(
                    "DeepSeek API cost cap reached before HTTP send: "
                    f"accounted=${self.reserved_usd}, limit=${self.max_cost_usd}, "
                    f"next reservation=${reservation}"
                )
            attempt = uuid4().hex
            request.extensions["deepseek_budget_attempt"] = attempt
            data["attempts"][attempt] = {
                "status": "reserved", "accounted_usd": str(reservation),
                "max_output_tokens": maximum, "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "configuration_version": os.environ.get("DEEPSEEK_CONFIG_VERSION"),
            }

    async def settle_response(self, response: Any) -> None:
        """Settle only a complete successful response with validated raw usage.

        Buffering the finite response retains its bytes for the SDK's parser.
        Failed/incomplete responses retain their entire reservation, including
        when the SDK later retries. No request/response text or headers are saved.
        """
        if response.status_code != 200:
            return
        payload = await response.aread()
        objects = []
        if "text/event-stream" in response.headers.get("content-type", ""):
            done = False
            for line in payload.decode("utf-8").splitlines():
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    done = True
                elif value:
                    objects.append(json.loads(value))
            if not done:
                return
        else:
            objects = [json.loads(payload)]
        usage = next((obj["usage"] for obj in reversed(objects) if isinstance(obj, dict) and isinstance(obj.get("usage"), dict)), None)
        allowed_finish_reasons = {"stop", "length", "tool_calls", "content_filter", "function_call", "insufficient_system_resource"}
        finish_reasons = sorted({choice.get("finish_reason") for obj in objects if isinstance(obj, dict)
                                 for choice in obj.get("choices", []) if isinstance(choice, dict)
                                 and isinstance(choice.get("finish_reason"), str)
                                 and choice["finish_reason"] in allowed_finish_reasons})
        attempt = response.request.extensions.get("deepseek_budget_attempt")
        with self._locked() as data:
            entry = data["attempts"].get(attempt)
            if not entry or entry["status"] != "reserved":
                raise ValueError("DeepSeek response has no unsettled request reservation")
            entry["finish_reasons"] = finish_reasons
            if usage is None:
                return
            # Verified cache categories are billed separately; retain peak rates
            # even in off-peak periods so this remains a conservative upper bound.
            cost = peak_usage_cost(usage, entry["max_output_tokens"])
            safe_usage = {key: value for key, value in usage.items() if key in (
                "prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens") and type(value) is int and value >= 0}
            model = next((obj.get("model") for obj in reversed(objects) if isinstance(obj, dict) and isinstance(obj.get("model"), str)), None)
            entry.update(status="settled", accounted_usd=str(cost), usage=safe_usage, settlement_policy="reported_cache_peak_rates",
                         model=model, finished_at_utc=datetime.now(timezone.utc).isoformat())


def build_deepseek_model(*, api_key: str | None = None, http_client: Any = None):
    """Build Flash using the official provider and a current API profile.

    ``http_client`` permits an entirely in-memory transport in offline tests.
    Model construction itself does not make a request.
    """
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.profiles import merge_profile
    from pydantic_ai.profiles.openai import OpenAIModelProfile
    from pydantic_ai.providers.deepseek import DeepSeekProvider

    guard = RequestBudgetGuard(os.environ.get("DEEPSEEK_MAX_COST_USD", ""))
    if http_client is None:
        import httpx

        http_client = httpx.AsyncClient(trust_env=False, follow_redirects=False)
    # OpenAI's SDK retries call client.send again, so the hook covers each
    # attempt rather than only the initial Agent request. No redirects or
    # environment-configured proxies are used by the production client.
    http_client.follow_redirects = False
    http_client.event_hooks.setdefault("request", []).append(guard)
    http_client.event_hooks.setdefault("response", []).append(guard.settle_response)
    provider = DeepSeekProvider(api_key=api_key, http_client=http_client)
    profile = merge_profile(
        DeepSeekProvider.model_profile("deepseek-v4-flash"),
        OpenAIModelProfile(
            supports_image_input=True,
            supports_thinking=True,
            thinking_enabled_by_default=True,
            supports_forced_tool_choice_with_thinking=False,
            openai_chat_supports_max_completion_tokens=False,
            openai_supports_strict_tool_definition=False,
        ),
    )
    return OpenAIChatModel(MODEL_NAME, provider=provider, profile=profile)


def install_compatibility() -> None:
    """Override only the exact Flash model in RPent's shared model factory."""
    from rpent.planner import base

    if getattr(base.build_api_model, "_deepseek_flash_compatibility", False):
        return
    original = base.build_api_model

    def build_api_model(model: str | None, base_url: str | None = None):
        if model == MODEL_ID:
            if base_url is not None and base_url.rstrip("/") != BASE_URL:
                raise ValueError("DeepSeek Flash requires the official HTTPS endpoint")
            return build_deepseek_model()
        return original(model, base_url)

    setattr(build_api_model, "_deepseek_flash_compatibility", True)
    base.build_api_model = build_api_model


def main() -> int:
    """Forward all command-line arguments unchanged to the upstream RPent CLI."""
    sys.path.insert(0, str(ROOT / "workspace/vla_baselines/repos/rpent"))
    install_compatibility()
    from rpent.cli.main import main as upstream_main

    return upstream_main()


if __name__ == "__main__":
    raise SystemExit(main())
