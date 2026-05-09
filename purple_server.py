"""
Strain Kallfu Zero — Pi-Bench Purple Agent Server

A2A JSON-RPC 2.0 endpoint for pi-bench policy compliance evaluation.
Orchestrates Cerebro 0 (pre-pipeline) → Cerebro 1 (LLM) → Cerebro 2 (post-pipeline).

Usage:
    uv run purple_server.py --host 0.0.0.0 --port 9009
"""

from __future__ import annotations

import argparse
import logging
import uuid
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cerebro_0 import (
    build_model_messages,
    build_system_prompt,
    classify_intent,
    sanitize_input,
    _as_list,
)
from cerebro_1 import llm_call
from cerebro_2 import (
    check_decision_consistency,
    format_a2a_response,
    validate_tool_calls,
)


def _jsonrpc_success(request_id: str | None, part: dict[str, Any]) -> dict[str, Any]:
    """Wrap a part in a JSON-RPC 2.0 success response."""
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


def _jsonrpc_error(
    request_id: str | None, code: int, message: str
) -> dict[str, Any]:
    """JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id or str(uuid.uuid4()),
        "error": {"code": code, "message": message},
    }

logger = logging.getLogger(__name__)

POLICY_BOOTSTRAP_EXTENSION = "urn:pi-bench:policy-bootstrap:v1"

app = FastAPI(title="Strain Kallfu Zero - Pi-Bench")

_seed: int | None = None
_card_url: str = ""
_sessions: dict[str, dict[str, Any]] = {}


@app.get("/.well-known/agent.json")
async def agent_card() -> JSONResponse:
    return JSONResponse({
        "name": "Strain Kallfu Zero - Pi-Bench",
        "description": (
            "Multi-layer purple agent with deterministic pre/post pipeline "
            "and DeepSeek V3.2 + Llama 4 Maverick fallback. "
            "Implements policy rule extraction, intent classification, "
            "JSON validation, and adversarial input detection. "
            "Pi-Bench bootstrap extension support."
        ),
        "url": _card_url,
        "version": "1.0.0",
        "protocolVersion": "0.3.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
            "extensions": [POLICY_BOOTSTRAP_EXTENSION],
        },
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "pi-bench-policy-compliance",
                "name": "Pi-Bench Policy Compliance",
                "description": (
                    "Evaluates policy compliance using multi-layer pipeline "
                    "with deterministic pre/post processing"
                ),
                "tags": ["policy", "compliance", "pi-bench"],
                "examples": [
                    "Evaluate whether a refund request complies with FINRA policy",
                    "Determine if access should be granted under IT helpdesk rules",
                ],
            }
        ],
    })


@app.get("/.well-known/agent-card.json")
async def agent_card_alias() -> JSONResponse:
    return await agent_card()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "team": "Strain Kallfu Zero"})


@app.post("/")
async def message_send(request: Request) -> JSONResponse:
    body = await request.json()

    method = body.get("method", "")
    if method != "message/send":
        return JSONResponse(content=_jsonrpc_error(
            body.get("id"), -32601, f"Unknown method: {method}"
        ))

    params = body.get("params", {})
    message = params.get("message", {})
    parts = message.get("parts", [])

    if not parts:
        return JSONResponse(content=_jsonrpc_error(
            body.get("id"), -32602, "No message parts"
        ))

    data = parts[0].get("data", {})

    if data.get("bootstrap"):
        result = _handle_bootstrap(body.get("id"), data)
    else:
        result = await _handle_turn(body.get("id"), data)

    return JSONResponse(content=result)


def _handle_bootstrap(request_id: str | None, data: dict[str, Any]) -> dict[str, Any]:
    """Cache benchmark context + tools, return context_id.

    Cerebro 0 processes the benchmark context immediately to extract rules
    and build the enriched system prompt. This is cached per context_id so
    subsequent turns don't need to re-process.
    """
    context_id = str(uuid.uuid4())
    benchmark_context = _as_list(data.get("benchmark_context"))
    tools = _as_list(data.get("tools"))
    domain = str(data.get("domain", ""))

    intent_info = classify_intent([], domain)
    system_prompt = build_system_prompt(benchmark_context, tools, intent_info, domain)

    _sessions[context_id] = {
        "benchmark_context": benchmark_context,
        "tools": tools,
        "system_prompt": system_prompt,
        "intent_info": intent_info,
        "domain": domain,
        "run_id": data.get("run_id"),
    }

    logger.info(
        "Bootstrap: context_id=%s domain=%s rules=%d tools=%d",
        context_id,
        domain,
        sum(1 for _ in system_prompt.split("\n") if _.startswith(tuple("123456789"))),
        len(tools),
    )

    return _jsonrpc_success(request_id, {
        "kind": "data",
        "data": {"bootstrapped": True, "context_id": context_id},
    })


async def _handle_turn(
    request_id: str | None, data: dict[str, Any]
) -> dict[str, Any]:
    """Process a regular conversation turn through the 3-cerebro pipeline."""
    context_id = data.get("context_id")
    messages = _as_list(data.get("messages"))

    if context_id:
        session = _sessions.get(str(context_id))
        if session is None:
            return _jsonrpc_error(
                request_id, -32004,
                f"Unknown bootstrap context_id: {context_id}"
            )
        tools = session["tools"]
        system_prompt = session["system_prompt"]
        benchmark_context = session.get("benchmark_context", [])
        intent_info = session.get("intent_info", {})
    else:
        benchmark_context = _as_list(data.get("benchmark_context"))
        tools = _as_list(data.get("tools"))
        domain = str(data.get("domain", ""))
        intent_info = classify_intent(messages, domain)
        system_prompt = build_system_prompt(benchmark_context, tools, intent_info, domain)

    user_texts = [
        str(m.get("content", ""))
        for m in messages
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    combined_text = " ".join(user_texts)

    injection_info = sanitize_input(combined_text)

    model_messages = build_model_messages(system_prompt, messages)

    try:
        raw_response = await llm_call(
            messages=model_messages,
            tools=tools if tools else None,
            seed=_seed,
        )
    except Exception as exc:
        logger.exception("LLM call failed after all fallbacks")
        return _jsonrpc_error(request_id, -32000, str(exc))

    validated = validate_tool_calls(raw_response, tools)

    flags = check_decision_consistency(validated, intent_info, benchmark_context)
    if flags or injection_info.get("anomaly_score", 0) > 0:
        logger.info(
            "Turn flags: decision=%s injection_score=%s",
            flags, injection_info.get("anomaly_score", 0),
        )

    return format_a2a_response(validated, request_id)


def main() -> None:
    global _seed, _card_url

    parser = argparse.ArgumentParser(
        description="Strain Kallfu Zero - Pi-Bench Purple Agent"
    )
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9009)
    parser.add_argument("--card-url", type=str, default="")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--log-level", type=str, default="INFO")
    args = parser.parse_args()

    _seed = args.seed
    _card_url = args.card_url

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )

    logger.info(
        "Strain Kallfu Zero starting: host=%s port=%d seed=%s",
        args.host, args.port, _seed,
    )

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
