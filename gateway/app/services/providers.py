from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.config import get_settings
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse

logger = logging.getLogger(__name__)

_ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
_OPENAI_API = "https://api.openai.com/v1/chat/completions"
_OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"

_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)


def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    system = None
    rest = []
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content", "")
        else:
            rest.append(m)
    return system, rest


def _anthropic_to_openai(data: dict, model: str) -> dict:
    content = "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    )
    stop_reason = data.get("stop_reason", "end_turn")
    finish_reason = "stop" if stop_reason == "end_turn" else stop_reason
    usage = data.get("usage", {})
    return {
        "id": data.get("id", f"msg_{int(time.time())}"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": data.get("model", model),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


async def call_anthropic(request: ChatCompletionRequest) -> dict:
    settings = get_settings()
    system, messages = _split_system([m.model_dump() for m in request.messages])

    payload: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "messages": messages,
    }
    if system:
        payload["system"] = system
    if request.temperature != 1.0:
        payload["temperature"] = request.temperature

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            _ANTHROPIC_API,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return _anthropic_to_openai(resp.json(), request.model)


async def call_openai(request: ChatCompletionRequest) -> dict:
    settings = get_settings()
    payload = {
        "model": request.model,
        "messages": [m.model_dump() for m in request.messages],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "n": request.n,
    }
    if request.top_p is not None:
        payload["top_p"] = request.top_p

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            _OPENAI_API,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "content-type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def call_openrouter(request: ChatCompletionRequest) -> dict:
    settings = get_settings()
    payload = {
        "model": request.model,
        "messages": [m.model_dump() for m in request.messages],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            _OPENROUTER_API,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://llm-gateway",
                "X-Title": "LLM Gateway",
                "content-type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def call_provider(provider: str, request: ChatCompletionRequest) -> dict:
    if provider == "anthropic":
        return await call_anthropic(request)
    if provider == "openai":
        return await call_openai(request)
    if provider == "openrouter":
        return await call_openrouter(request)
    raise ValueError(f"Unknown provider: {provider}")


async def stream_anthropic(request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
    settings = get_settings()
    system, messages = _split_system([m.model_dump() for m in request.messages])

    payload: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "messages": messages,
        "stream": True,
    }
    if system:
        payload["system"] = system
    if request.temperature != 1.0:
        payload["temperature"] = request.temperature

    completion_id = f"chatcmpl-{int(time.time())}"
    created = int(time.time())

    yield f"data: {json.dumps({'id': completion_id, 'object': 'chat.completion.chunk', 'created': created, 'model': request.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}, 'finish_reason': None}]})}\n\n"

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        async with client.stream(
            "POST",
            _ANTHROPIC_API,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": request.model,
                            "choices": [
                                {"index": 0, "delta": {"content": text}, "finish_reason": None}
                            ],
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                elif event_type == "message_delta":
                    stop_reason = event.get("delta", {}).get("stop_reason", "end_turn")
                    finish_reason = "stop" if stop_reason == "end_turn" else stop_reason
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "choices": [
                            {"index": 0, "delta": {}, "finish_reason": finish_reason}
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"

    yield "data: [DONE]\n\n"


async def stream_openai_compat(
    request: ChatCompletionRequest, provider: str
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    payload = {
        "model": request.model,
        "messages": [m.model_dump() for m in request.messages],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "stream": True,
    }

    if provider == "openai":
        url = _OPENAI_API
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "content-type": "application/json",
        }
    else:
        url = _OPENROUTER_API
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://llm-gateway",
            "X-Title": "LLM Gateway",
            "content-type": "application/json",
        }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield f"{line}\n\n"
                    if line.strip() == "data: [DONE]":
                        break


async def stream_provider(
    provider: str, request: ChatCompletionRequest
) -> AsyncGenerator[str, None]:
    if provider == "anthropic":
        async for chunk in stream_anthropic(request):
            yield chunk
    else:
        async for chunk in stream_openai_compat(request, provider):
            yield chunk
