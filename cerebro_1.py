"""
Cerebro 1 — LLM Core (1 llamada LiteLLM con fallback chain)

Primary:   DeepSeek V3.2 Fast via Nebius
Fallback1: Llama 4 Maverick via Nebius
Fallback2: GPT-4o-mini via OpenAI
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import litellm

logger = logging.getLogger(__name__)

_NEBIUS_BASE = os.environ.get(
    "NEBIUS_API_BASE", "https://api.tokenfactory.us-central1.nebius.com/v1"
)

MODEL_CHAIN = [
    {
        "model": "nebius/deepseek-ai/DeepSeek-V3.2-fast",
        "api_base": _NEBIUS_BASE,
        "api_key": os.environ.get("NEBIUS_API_KEY", ""),
        "temperature": 0.0,
        "base_delay": 0.5,
    },
    {
        "model": "openai/gpt-4o-mini",
        "temperature": 0.1,
        "base_delay": 0.5,
    },
]


async def llm_call(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    seed: int | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call LLM with exponential backoff fallback chain."""
    last_error = None

    for i, config in enumerate(MODEL_CHAIN):
        try:
            kwargs: dict[str, Any] = {
                "model": config["model"],
                "messages": messages,
                "temperature": config.get("temperature", 0.0),
                "max_tokens": max_tokens,
                "drop_params": True,
            }

            if config.get("api_base"):
                kwargs["api_base"] = config["api_base"]
            if config.get("api_key"):
                kwargs["api_key"] = config["api_key"]
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "required"
            if seed is not None:
                kwargs["seed"] = seed

            logger.info(
                "LLM call attempt %d: model=%s", i + 1, config["model"]
            )

            response = await asyncio.to_thread(litellm.completion, **kwargs)
            return _parse_response(response)

        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "LLM attempt %d failed (%s): %s", i + 1, config["model"], last_error
            )
            if i < len(MODEL_CHAIN) - 1:
                delay = config["base_delay"] * (i + 1)
                time.sleep(delay)
                continue

    raise RuntimeError(f"All LLM models failed. Last error: {last_error}")


def _parse_response(response: Any) -> dict[str, Any]:
    """Parse LiteLLM response into normalized dict."""
    choice = response.choices[0]
    message = choice.message

    tool_calls_raw = getattr(message, "tool_calls", None)
    content = getattr(message, "content", None)

    result: dict[str, Any] = {}

    if tool_calls_raw:
        tc_list = []
        for tc in tool_calls_raw:
            tc_list.append({
                "id": getattr(tc, "id", ""),
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })
        result["tool_calls"] = tc_list
        if content:
            result["content"] = content
    elif content:
        result["content"] = content
    else:
        result["content"] = "###STOP###"

    return result
