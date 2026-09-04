"""
ai/router.py
───────────────────────────────
AI Router — provider priority, timeouts, exponential backoff, circuit breaker,
accurate token accounting, model pricing calculation, usage logging.
"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from typing import Any, List, Optional, Tuple

import frappe
import requests


def is_ai_chat_enabled() -> bool:
    """Check if AI Chat feature flag is enabled globally in AI Workplace Settings."""
    try:
        if not frappe.db.exists("DocType", "AI Workplace Settings"):
            return True
        settings = frappe.get_single("AI Workplace Settings")
        if hasattr(settings, "ai_chat_enabled"):
            return bool(settings.ai_chat_enabled)
        return True
    except Exception:
        return True


# ──────────────────────────────────────────────────────────────────────────────
# Circuit Breaker Implementation
# ──────────────────────────────────────────────────────────────────────────────

def _parse_cache_data(data: Any) -> dict:
    if not data:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return {}
    return {}


class CircuitBreaker:
    """
    Tracks state of AI providers: CLOSED (healthy), OPEN (unhealthy), HALF_OPEN (probing).
    """

    @staticmethod
    def get_state(provider_name: str, failure_threshold: int = 3, cooldown_seconds: int = 60) -> str:
        cache_key = f"ai_workplace:circuit:{provider_name}"
        raw = frappe.cache().get_value(cache_key)
        data = _parse_cache_data(raw)
        if not data:
            return "CLOSED"

        state = data.get("state", "CLOSED")
        opened_at = data.get("opened_at", 0)

        if state == "OPEN":
            if time.time() - opened_at >= cooldown_seconds:
                CircuitBreaker.set_state(provider_name, "HALF_OPEN", data.get("failures", failure_threshold))
                frappe.logger("ai_workplace").info(
                    f"Circuit Breaker for {provider_name}: OPEN -> HALF_OPEN (cooldown expired)"
                )
                return "HALF_OPEN"
            return "OPEN"
        return state

    @staticmethod
    def set_state(provider_name: str, state: str, failures: int = 0) -> None:
        cache_key = f"ai_workplace:circuit:{provider_name}"
        payload = {
            "state": state,
            "failures": failures,
            "opened_at": time.time() if state in ("OPEN", "HALF_OPEN") else 0,
        }
        val = json.dumps(payload)
        frappe.cache().set_value(cache_key, val)

    @staticmethod
    def record_success(provider_name: str) -> None:
        current = CircuitBreaker.get_state(provider_name)
        if current in ("OPEN", "HALF_OPEN"):
            frappe.logger("ai_workplace").info(
                f"Circuit Breaker for {provider_name}: {current} -> CLOSED (request succeeded)"
            )
        CircuitBreaker.set_state(provider_name, "CLOSED", failures=0)

    @staticmethod
    def record_failure(provider_name: str, failure_threshold: int = 3, cooldown_seconds: int = 60) -> str:
        cache_key = f"ai_workplace:circuit:{provider_name}"
        raw = frappe.cache().get_value(cache_key)
        data = _parse_cache_data(raw)
        failures = data.get("failures", 0) + 1

        if failures >= failure_threshold:
            CircuitBreaker.set_state(provider_name, "OPEN", failures=failures)
            frappe.logger("ai_workplace").warning(
                f"Circuit Breaker for {provider_name}: CLOSED/HALF_OPEN -> OPEN ({failures} failures)"
            )
            return "OPEN"
        else:
            CircuitBreaker.set_state(provider_name, "CLOSED", failures=failures)
            return "CLOSED"


# ──────────────────────────────────────────────────────────────────────────────
# Token & Cost Helpers
# ──────────────────────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Estimate token count when provider usage is missing."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def calculate_cost(
    model: Any,
    tokens_in: int,
    tokens_out: int,
) -> Tuple[float, float, float, str]:
    """
    Calculate input_cost, output_cost, total_cost, and currency for a completion call.
    """
    in_rate = getattr(model, "input_cost_per_1k", 0.00015)
    if in_rate is None:
        in_rate = 0.00015

    out_rate = getattr(model, "output_cost_per_1k", 0.00060)
    if out_rate is None:
        out_rate = 0.00060

    currency = getattr(model, "currency", "USD") or "USD"

    input_cost = round((tokens_in / 1000.0) * float(in_rate), 6)
    output_cost = round((tokens_out / 1000.0) * float(out_rate), 6)
    total_cost = round(input_cost + output_cost, 6)

    return input_cost, output_cost, total_cost, currency


def classify_error(exc: Optional[Exception], status_code: Optional[int] = None) -> Tuple[str, bool]:
    """
    Classify exception or HTTP status code into (error_type, is_retriable).
    """
    if exc:
        if isinstance(exc, requests.exceptions.Timeout):
            return "TIMEOUT", True
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "CONNECTION_ERROR", True

    if status_code:
        if status_code in (429, 500, 502, 503, 504):
            return f"HTTP_{status_code}", True
        elif status_code in (401, 403):
            return "INVALID_CREDENTIALS", False
        elif status_code == 400:
            return "MALFORMED_REQUEST", False
        elif status_code == 404:
            return "NOT_FOUND", False
        else:
            return f"HTTP_{status_code}", False

    return "UNEXPECTED_ERROR", False


# ──────────────────────────────────────────────────────────────────────────────
# Completion Engine
# ──────────────────────────────────────────────────────────────────────────────

def complete(
    prompt: str = "",
    system: str = "",
    *,
    messages: Optional[List[dict[str, Any]]] = None,
    tools: Optional[List[dict[str, Any]]] = None,
    capabilities: Optional[list[str]] = None,
    channel: str = "WhatsApp",
    employee: str = "",
    model_slug: str = "",
) -> dict[str, Any]:
    """
    Run chat completion via configured providers with fallback, retries, and circuit breaker.
    """
    if not is_ai_chat_enabled():
        return {
            "success": False,
            "text": "",
            "tool_calls": [],
            "provider": "",
            "model": "",
            "error": "AI Chat is disabled by system policy",
        }

    capabilities = capabilities or ["TEXT"]
    providers = _get_active_providers()
    last_error = ""
    last_error_type = "NO_PROVIDER"
    primary_provider_name = providers[0].name if providers else ""

    for idx, provider in enumerate(providers):
        failure_thresh = getattr(provider, "circuit_failure_threshold", 3) or 3
        cooldown_sec = getattr(provider, "circuit_cooldown_seconds", 60) or 60
        cb_state = CircuitBreaker.get_state(provider.name, failure_thresh, cooldown_sec)

        if cb_state == "OPEN":
            frappe.logger("ai_workplace").warning(
                f"AI Router: Skipping provider {provider.name} because Circuit Breaker is OPEN"
            )
            last_error = f"Circuit Breaker for {provider.name} is OPEN"
            last_error_type = "CIRCUIT_OPEN"
            continue

        model = _pick_model(provider, capabilities, model_slug)
        if not model:
            continue

        req_started_at = datetime.utcnow()
        start = time.time()
        is_fallback = (idx > 0)
        fallback_used = primary_provider_name if is_fallback else ""

        try:
            res = _call_provider_with_retry(
                provider,
                model,
                prompt,
                system,
                messages=messages,
                tools=tools,
            )
            latency_ms = int((time.time() - start) * 1000)
            req_completed_at = datetime.utcnow()

            CircuitBreaker.record_success(provider.name)

            tokens_in = res.get("tokens_in", 0)
            tokens_out = res.get("tokens_out", 0)
            tokens_total = tokens_in + tokens_out
            usage_source = res.get("usage_source", "provider_reported")
            retry_count = res.get("retry_count", 0)

            in_cost, out_cost, tot_cost, curr = calculate_cost(model, tokens_in, tokens_out)

            _log_usage(
                provider=provider,
                model=model,
                channel=channel,
                employee=employee,
                latency_ms=latency_ms,
                success=True,
                status="Success",
                prompt=prompt or str(messages),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_total=tokens_total,
                usage_source=usage_source,
                input_cost=in_cost,
                output_cost=out_cost,
                total_cost=tot_cost,
                currency=curr,
                retry_count=retry_count,
                fallback_used=fallback_used,
                request_started_at=req_started_at,
                request_completed_at=req_completed_at,
            )

            return {
                "success": True,
                "text": res.get("text", ""),
                "tool_calls": res.get("tool_calls", []),
                "raw_message": res.get("raw_message"),
                "provider": provider.name,
                "model": model.model_slug,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tokens_total": tokens_total,
                "usage_source": usage_source,
                "total_cost": tot_cost,
                "latency_ms": latency_ms,
            }

        except Exception as exc:
            req_completed_at = datetime.utcnow()
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            err_type, retriable = classify_error(exc, status_code)
            last_error = str(exc)
            last_error_type = err_type
            latency_ms = int((time.time() - start) * 1000)

            CircuitBreaker.record_failure(provider.name, failure_thresh, cooldown_sec)

            tokens_in = estimate_tokens(prompt or str(messages))
            tokens_out = 0

            _log_usage(
                provider=provider,
                model=model,
                channel=channel,
                employee=employee,
                latency_ms=latency_ms,
                success=False,
                status="Timed Out" if err_type == "TIMEOUT" else "Failed",
                prompt=prompt or str(messages),
                error_type=err_type,
                error=last_error,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_total=tokens_in,
                usage_source="tokenizer_estimated",
                fallback_used=fallback_used,
                request_started_at=req_started_at,
                request_completed_at=req_completed_at,
            )

    # All active providers failed -> attempt Groq settings fallback
    fallback = _groq_settings_fallback(prompt, system, messages=messages, tools=tools)
    if fallback.get("success"):
        return fallback

    return {
        "success": False,
        "text": "",
        "tool_calls": [],
        "error": last_error or "No active AI provider configured",
        "error_type": last_error_type,
    }


def _get_active_providers() -> list[Any]:
    if not frappe.db.exists("DocType", "AI Workplace Provider"):
        return []
    names = frappe.get_all(
        "AI Workplace Provider",
        filters={"is_active": 1},
        fields=["name"],
        order_by="priority asc",
    )
    return [frappe.get_doc("AI Workplace Provider", row.name) for row in names]


def _pick_model(provider: Any, capabilities: list[str], model_slug: str) -> Any:
    filters: dict[str, Any] = {"provider": provider.name, "is_active": 1}
    if model_slug:
        filters["model_slug"] = model_slug
    models = frappe.get_all("AI Workplace Model", filters=filters, fields=["name"], order_by="modified desc")
    if not models:
        return None
    return frappe.get_doc("AI Workplace Model", models[0].name)


def _call_provider_with_retry(
    provider: Any,
    model: Any,
    prompt: str,
    system: str,
    messages: Optional[List[dict[str, Any]]] = None,
    tools: Optional[List[dict[str, Any]]] = None,
) -> dict[str, Any]:
    connect_timeout = getattr(provider, "connect_timeout", 5) or 5
    read_timeout = getattr(provider, "read_timeout", 15) or 15
    max_retries = getattr(provider, "max_retries", 3) or 3
    base_delay = getattr(provider, "base_delay", 1.0) or 1.0
    max_delay = getattr(provider, "max_delay", 10.0) or 10.0

    last_exc = None

    for attempt in range(max_retries + 1):
        try:
            res = _call_provider_single(
                provider=provider,
                model=model,
                prompt=prompt,
                system=system,
                messages=messages,
                tools=tools,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            )
            res["retry_count"] = attempt
            return res
        except requests.exceptions.HTTPError as http_err:
            last_exc = http_err
            status_code = http_err.response.status_code if http_err.response is not None else None
            err_type, retriable = classify_error(http_err, status_code)
            
            if not retriable or attempt >= max_retries:
                raise http_err

            retry_after_header = http_err.response.headers.get("Retry-After") if http_err.response is not None else None
            if retry_after_header and retry_after_header.isdigit():
                delay = float(retry_after_header)
            else:
                jitter = random.uniform(0, 0.5 * base_delay)
                delay = min(max_delay, base_delay * (2 ** attempt) + jitter)
            
            time.sleep(delay)

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_err:
            last_exc = net_err
            err_type, retriable = classify_error(net_err)
            if not retriable or attempt >= max_retries:
                raise net_err
            jitter = random.uniform(0, 0.5 * base_delay)
            delay = min(max_delay, base_delay * (2 ** attempt) + jitter)
            time.sleep(delay)

        except Exception as exc:
            raise exc

    if last_exc:
        raise last_exc
    raise frappe.ValidationError("Provider execution failed")


def _call_provider_single(
    provider: Any,
    model: Any,
    prompt: str,
    system: str,
    messages: Optional[List[dict[str, Any]]] = None,
    tools: Optional[List[dict[str, Any]]] = None,
    connect_timeout: int = 5,
    read_timeout: int = 15,
) -> dict[str, Any]:
    api_key = ""
    try:
        api_key = provider.get_password("api_key")
    except Exception:
        api_key = provider.get("api_key") or ""
    if not api_key:
        raise frappe.ValidationError(f"API key missing for provider {provider.name}")

    base_url = (provider.api_base_url or "https://api.groq.com/openai/v1").rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    if messages:
        payload_messages.extend(messages)
    elif prompt:
        payload_messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model.model_slug,
        "messages": payload_messages,
        "max_tokens": model.max_tokens or 1024,
        "temperature": model.temperature or 0.3,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=(connect_timeout, read_timeout),
        proxies={"http": None, "https": None},
    )
    resp.raise_for_status()
    data = resp.json()

    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    text = (msg.get("content") or "").strip()
    tool_calls = msg.get("tool_calls", [])

    usage = data.get("usage", {})
    reported_in = usage.get("prompt_tokens")
    reported_out = usage.get("completion_tokens")

    if reported_in is not None and reported_out is not None:
        tokens_in = reported_in
        tokens_out = reported_out
        usage_source = "provider_reported"
    else:
        tokens_in = estimate_tokens(str(payload_messages))
        tokens_out = estimate_tokens(text)
        usage_source = "tokenizer_estimated"

    return {
        "text": text,
        "tool_calls": tool_calls,
        "raw_message": msg,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "usage_source": usage_source,
    }


def _groq_settings_fallback(
    prompt: str,
    system: str,
    messages: Optional[List[dict[str, Any]]] = None,
    tools: Optional[List[dict[str, Any]]] = None,
) -> dict[str, Any]:
    try:
        if not frappe.db.exists("DocType", "Groq AI Settings"):
            return {"success": False}
        settings = frappe.get_single("Groq AI Settings")
        if not settings.enabled:
            return {"success": False}
        api_key = settings.get_password("api_key")
        if not api_key:
            return {"success": False}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        payload_messages = []
        if system or settings.system_prompt:
            payload_messages.append({"role": "system", "content": system or settings.system_prompt})
        if messages:
            payload_messages.extend(messages)
        elif prompt:
            payload_messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": settings.model or "llama3-8b-8192",
            "messages": payload_messages,
            "max_tokens": settings.max_tokens or 1024,
            "temperature": settings.temperature or 0.3,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=(5, 15),
            proxies={"http": None, "https": None},
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        text = (msg.get("content") or "").strip()
        tool_calls = msg.get("tool_calls", [])

        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens") or estimate_tokens(str(payload_messages))
        tokens_out = usage.get("completion_tokens") or estimate_tokens(text)

        return {
            "success": True,
            "text": text,
            "tool_calls": tool_calls,
            "raw_message": msg,
            "provider": "Groq AI Settings",
            "model": settings.model or "legacy",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tokens_total": tokens_in + tokens_out,
            "usage_source": "provider_reported" if usage else "tokenizer_estimated",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _log_usage(
    *,
    provider: Any,
    model: Any,
    channel: str,
    employee: str,
    latency_ms: int,
    success: bool,
    prompt: str,
    status: str = "Success",
    tokens_in: int = 0,
    tokens_out: int = 0,
    tokens_total: int = 0,
    usage_source: str = "provider_reported",
    input_cost: float = 0.0,
    output_cost: float = 0.0,
    total_cost: float = 0.0,
    currency: str = "USD",
    retry_count: int = 0,
    fallback_used: str = "",
    error_type: str = "",
    error: str = "",
    request_started_at: Optional[datetime] = None,
    request_completed_at: Optional[datetime] = None,
) -> None:
    if not frappe.db.exists("DocType", "AI Workplace Usage Log"):
        return
    try:
        doc = frappe.new_doc("AI Workplace Usage Log")
        doc.provider = provider.name
        doc.model = model.name
        doc.channel = channel
        doc.employee = employee or None
        doc.latency_ms = latency_ms
        doc.success = 1 if success else 0
        doc.status = status
        doc.prompt_hash = frappe.generate_hash(prompt[:500])
        doc.error_message = error
        doc.error_type = error_type
        doc.tokens_in = tokens_in
        doc.tokens_out = tokens_out
        doc.tokens_total = tokens_total or (tokens_in + tokens_out)
        doc.usage_source = usage_source
        doc.input_cost = input_cost
        doc.output_cost = output_cost
        doc.total_cost = total_cost
        doc.currency = currency
        doc.retry_count = retry_count
        doc.fallback_used = fallback_used
        doc.request_started_at = request_started_at or frappe.utils.now_datetime()
        doc.request_completed_at = request_completed_at or frappe.utils.now_datetime()
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"AI Router: Failed to log usage: {exc}")
