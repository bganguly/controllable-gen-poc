from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "claude-sonnet-4-6"
    messages: list[ChatMessage]
    max_tokens: int = 4096
    temperature: float = 1.0
    stream: bool = False
    top_p: float | None = None
    n: int = 1


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: UsageInfo


class CreateKeyRequest(BaseModel):
    owner: str
    allowed_models: list[str] = Field(default_factory=lambda: ["*"])
    rate_limit_tier: Literal["free", "standard", "premium"] = "standard"


class CreateKeyResponse(BaseModel):
    key: str
    id: str
    owner: str
    rate_limit_tier: str
    message: str = "Store this key securely — it will not be shown again."


class KeyInfo(BaseModel):
    id: str
    owner: str
    allowed_models: list[str]
    rate_limit_tier: str
    created_at: str
    is_active: bool


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: dict | None = None


class AuditQueryParams(BaseModel):
    start: str
    end: str
    standard: Literal["soc2", "iso27001", "both"] = "soc2"
