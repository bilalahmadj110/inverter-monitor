"""OpenAI Q&A endpoint for the dashboard.

Single-turn, non-streaming. The user asks a free-text question about their
solar system; we ship the model:
  - A stable system prompt with app context, LESCO tariff explanation, and
    glossary.
  - A user message with a fresh stats snapshot + the question.

If OPENAI_API_KEY is missing or the SDK isn't installed, /ai/ask returns 503
instead of crashing — the feature is opt-in, not a hard dependency. The
default model is gpt-4o-mini for cost/perf; override via OPENAI_MODEL.
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "gpt-4o-mini"


SYSTEM_PROMPT = """You are the on-board AI for a home solar monitoring dashboard.

The user has a Voltronic Galaxy Primax 3.3kW hybrid inverter on his rooftop in
Pakistan, fed by solar panels and backed by a battery and the LESCO grid. The
dashboard reads QPIGS data from the inverter every few seconds, stores it in
SQLite (power_readings, daily_stats, monthly_stats), and exposes the data via
this dashboard. The user wants concise, *practical* answers — favour numbers,
short sentences, and clear recommendations over long explanations.

You will be given a JSON snapshot containing:
  - `today` — today's solar/grid/load kWh + savings at the current marginal rate
  - `month` — this month's bill simulation (with-solar vs without-solar)
  - `lifetime` — savings since system install
  - `payback` — months/years to recoup install cost
  - `projection` — month-end grid kWh projection + slab cliff alert
  - `config` — LESCO tariff config: consumer type, slabs, FPA, taxes
  - `recent_history` — last 14 days of daily kWh per source

LESCO tariff context (Jan 2026 reference, unprotected residential):
  - Slabs are non-telescopic: total monthly grid kWh determines the *single*
    rate applied to every unit. Crossing 200 kWh raises every unit from
    Rs 22.44 to Rs 28.91 — that is the single most important number to watch.
  - FPA (Fuel Price Adjustment) and FC Surcharge are per-unit add-ons.
  - GST 17% and Electricity Duty 1.5% apply to the energy + FPA + surcharges
    subtotal. TV fee Rs 35 is a fixed monthly add-on.
  - Protected consumers (avg <= 200 units over 6 months) get telescopic billing
    at much lower rates (Rs 3.95 / 10.54 / 13.01 per slab).

Style rules:
  - Lead with the numeric answer. One short paragraph, then 2-4 bullets if
    helpful. No headings. No markdown tables.
  - Round PKR to whole rupees, kWh to 2 decimals.
  - If the question can't be answered from the snapshot, say so plainly and
    name the missing data.
  - Never invent rates, dates, or readings — only use what's in the snapshot.
  - Don't restate the question.
"""


_openai_client = None


def _get_client():
    """Lazy-init the OpenAI client. Returns None if SDK isn't installed or no
    API key is set."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError as e:
        logger.warning(f"openai SDK not installed: {e}")
        return None
    _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _model_name() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def is_available() -> dict[str, Any]:
    """Tell the frontend whether AI Q&A is wired up. Used to show/hide the box."""
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    try:
        import openai  # noqa: F401
        sdk_installed = True
    except ImportError:
        sdk_installed = False
    return {
        "available": has_key and sdk_installed,
        "has_api_key": has_key,
        "sdk_installed": sdk_installed,
        "provider": "openai",
        "model": _model_name(),
    }


def _build_snapshot(stats_manager, cost_config) -> dict[str, Any]:
    """Assemble the JSON context the model sees. Built fresh per question so
    the answer reflects the live state of the system."""
    import cost_savings
    payload = cost_savings.build_full_payload(stats_manager, cost_config)
    history = stats_manager.get_history(14)
    payload["recent_history"] = history
    payload["latest_reading"] = (stats_manager.get_summary() or {})
    return payload


def ask(question: str, stats_manager, cost_config, max_tokens: int = 1024) -> dict[str, Any]:
    """Answer a single question about the dashboard data."""
    question = (question or "").strip()
    if not question:
        return {"ok": False, "error": "Question is empty."}
    if len(question) > 1000:
        return {"ok": False, "error": "Question too long (limit 1000 chars)."}

    client = _get_client()
    if client is None:
        return {
            "ok": False,
            "error": (
                "AI assistant not available. Set OPENAI_API_KEY in the "
                "environment and install the `openai` package."
            ),
        }

    snapshot = _build_snapshot(stats_manager, cost_config)
    snapshot_json = json.dumps(snapshot, default=str, sort_keys=True)

    user_content = (
        f"Current dashboard snapshot:\n```json\n{snapshot_json}\n```\n\n"
        f"Question: {question}"
    )

    model = _model_name()
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        usage = response.usage
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        return {
            "ok": True,
            "answer": text,
            "model": response.model,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cached_tokens": cached,
                "total_tokens": usage.total_tokens,
            },
        }
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return {"ok": False, "error": f"AI request failed: {e}"}
