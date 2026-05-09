"""
Cerebro 2 — Post-Pipeline (Deterministico)

ToolCallValidator: valida y corrige formato JSON de tool_calls.
DecisionConsistencyCheck: flaggea violaciones de policy (NO corrige).
A2AResponseFormatter: formato JSON-RPC 2.0 compatible con pi-bench.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)


def validate_tool_calls(
    raw_response: dict[str, Any],
    available_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate and repair tool_calls from LLM response."""
    available_names = _get_tool_names(available_tools)

    tool_calls = raw_response.get("tool_calls")
    if not tool_calls:
        content = raw_response.get("content", "")
        if not content:
            content = "###STOP###"
        return {"content": content}

    validated = []
    for tc in tool_calls:
        func = tc.get("function", {})
        name = str(func.get("name", "")).strip()
        arguments = func.get("arguments", "{}")

        if not name:
            continue

        if name not in available_names:
            fuzzy = _fuzzy_match(name, available_names)
            if fuzzy:
                logger.info("Fuzzy match tool: %s → %s", name, fuzzy)
                name = fuzzy
            else:
                logger.warning("Unknown tool skipped: %s", name)
                continue

        normalized_args = _normalize_json(arguments)
        if normalized_args is None:
            logger.warning("Unparseable arguments for tool %s, skipping", name)
            continue

        validated.append({
            "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "type": "function",
            "function": {
                "name": name,
                "arguments": normalized_args,
            },
        })

    if not validated:
        content = raw_response.get("content", "")
        return {"content": content or "###STOP###"}

    return {"tool_calls": validated}


def check_decision_consistency(
    validated: dict[str, Any],
    intent_info: dict[str, Any],
    benchmark_context: list[dict[str, Any]],
) -> list[str]:
    """Check if final decision is consistent with policy. Flags only, never blocks."""
    flags: list[str] = []

    tool_calls = validated.get("tool_calls", [])
    decisions = [
        tc for tc in tool_calls
        if tc.get("function", {}).get("name") == "record_decision"
    ]

    if not decisions:
        flags.append("no_record_decision_found")
        return flags

    last_decision = decisions[-1]
    try:
        args = json.loads(last_decision["function"]["arguments"])
        decision = args.get("decision", "UNKNOWN")
    except (json.JSONDecodeError, KeyError):
        flags.append("unparseable_decision_args")
        return flags

    intent = intent_info.get("intent", "UNKNOWN")
    intent_decision_map = {
        "SUSPICIOUS": ["DENY", "ESCALATE"],
    }

    expected = intent_decision_map.get(intent)
    if expected and decision not in expected:
        flags.append(f"suspicious_intent_mismatch: intent={intent} decision={decision}")

    if flags:
        logger.warning("Decision consistency flags: %s", flags)

    return flags


def format_a2a_response(
    validated: dict[str, Any],
    request_id: str | None = None,
) -> dict[str, Any]:
    """Format response as JSON-RPC 2.0 compatible with pi-bench A2A."""
    if "tool_calls" in validated:
        part = {
            "kind": "data",
            "data": {"tool_calls": validated["tool_calls"]},
        }
    else:
        part = {
            "kind": "data",
            "data": {"content": validated.get("content", "###STOP###")},
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id or str(uuid.uuid4()),
        "result": {
            "status": {
                "message": {
                    "role": "agent",
                    "parts": [part],
                },
            },
        },
    }


def format_error(
    request_id: str | None,
    code: int,
    message: str,
) -> dict[str, Any]:
    """Format JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id or str(uuid.uuid4()),
        "error": {"code": code, "message": message},
    }


def _get_tool_names(tools: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for tool in tools or []:
        if isinstance(tool, dict):
            func = tool.get("function", {})
            name = func.get("name", "") if isinstance(func, dict) else ""
            if name:
                names.add(name)
    return names


def _fuzzy_match(name: str, candidates: set[str]) -> str | None:
    best_score = 0.0
    best_match = None
    for candidate in candidates:
        score = SequenceMatcher(None, name.lower(), candidate.lower()).ratio()
        if score > 0.7 and score > best_score:
            best_score = score
            best_match = candidate
    return best_match


def _normalize_json(raw: str) -> str | None:
    """Normalize JSON arguments from LLM, handling common DeepSeek quirks."""
    if not raw or not raw.strip():
        return "{}"

    try:
        parsed = json.loads(raw)
        return json.dumps(parsed)
    except (json.JSONDecodeError, TypeError):
        pass

    repaired = _repair_json(raw)
    if repaired:
        try:
            parsed = json.loads(repaired)
            return json.dumps(parsed)
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _repair_json(raw: str) -> str | None:
    """Attempt to repair malformed JSON from LLM output."""
    match = re.search(r'\{[^{}]*\}', raw)
    if match:
        candidate = match.group(0)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    for old, new in [
        ("'", '"'),
        ("True", "true"),
        ("False", "false"),
        ("None", "null"),
    ]:
        raw = raw.replace(old, new)

    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    return None
