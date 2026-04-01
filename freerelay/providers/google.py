"""
FreeRelay — Google AI Studio / Gemini Provider (§7.2)
=======================================================
Request format differs from OpenAI — requires full translation.
Auth via ?key= query param, NOT Authorization header.
System messages go into systemInstruction, not contents.
Role mapping: assistant → model.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    Message,
    Usage,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


def _openai_to_gemini(request: ChatCompletionRequest) -> dict[str, object]:
    """Translate OpenAI request to Gemini generateContent format."""
    contents: list[dict[str, object]] = []
    system_text: str | None = None

    for msg in request.messages:
        role = msg.role
        if isinstance(msg.content, str):
            text = msg.content
            parts = [{"text": text}]
        elif isinstance(msg.content, list):
            parts = []
            for part in msg.content:
                if isinstance(part, dict):
                    if part.get("type") == "image_url":
                        image_url = part.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:"):
                            header, b64data = image_url.split(",", 1)
                            mime = header.split(":")[1].split(";")[0]
                            parts.append(
                                {
                                    "inlineData": {
                                        "mimeType": mime,
                                        "data": b64data,
                                    }
                                }
                            )
                        else:
                            parts.append(
                                {
                                    "fileData": {
                                        "mimeType": "image/*",
                                        "fileUri": image_url,
                                    }
                                }
                            )
                    elif part.get("type") == "text" and part.get("text"):
                        parts.append({"text": part["text"]})
                elif hasattr(part, "type"):
                    if part.type == "text" and part.text:
                        parts.append({"text": part.text})
                    elif part.type == "image_url" and part.image_url:
                        url = (
                            part.image_url.get("url", "")
                            if isinstance(part.image_url, dict)
                            else ""
                        )
                        if url.startswith("data:"):
                            header, b64data = url.split(",", 1)
                            mime = header.split(":")[1].split(";")[0]
                            parts.append(
                                {"inlineData": {"mimeType": mime, "data": b64data}}
                            )
            if not parts:
                parts = [{"text": ""}]
        else:
            parts = [{"text": ""}]

        if role == "system":
            text_content = " ".join(p.get("text", "") for p in parts if "text" in p)
            system_text = (system_text or "") + text_content + "\n"
            continue

        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": parts})

    payload: dict[str, object] = {"contents": contents}

    if system_text:
        payload["systemInstruction"] = {
            "parts": [{"text": system_text.strip()}],
        }

    gen_config: dict[str, object] = {}
    if request.temperature is not None:
        gen_config["temperature"] = request.temperature
    if request.max_tokens is not None:
        gen_config["maxOutputTokens"] = request.max_tokens
    if request.top_p is not None:
        gen_config["topP"] = request.top_p
    if request.stop:
        stops = [request.stop] if isinstance(request.stop, str) else request.stop
        gen_config["stopSequences"] = stops
    if gen_config:
        payload["generationConfig"] = gen_config

    return payload


def _gemini_to_openai(
    gemini_json: dict[str, object], model: str
) -> ChatCompletionResponse:
    """Translate Gemini response to OpenAI format."""
    candidates = gemini_json.get("candidates", [{}])  # type: ignore[arg-type]
    first = candidates[0] if candidates else {}  # type: ignore[index]
    parts = first.get("content", {}).get("parts", [])  # type: ignore[union-attr]
    text = parts[0].get("text", "") if parts else ""  # type: ignore[index]

    usage_meta = gemini_json.get("usageMetadata", {})

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
        created=int(time.time()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=Message(role="assistant", content=text),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=usage_meta.get("promptTokenCount", 0),  # type: ignore[arg-type]
            completion_tokens=usage_meta.get("candidatesTokenCount", 0),  # type: ignore[arg-type]
            total_tokens=usage_meta.get("totalTokenCount", 0),  # type: ignore[arg-type]
        ),
    )


class GoogleProvider(BaseProvider):
    """Google AI Studio (Gemini) provider."""

    name = "google"
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    supported_features = {"streaming", "vision"}

    _default_model = "gemini-1.5-flash"

    def _resolve_model(self, request: ChatCompletionRequest) -> str:
        model = request.model or self._default_model
        if "/" in model:
            model = model.split("/", 1)[1]
        return model

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        model = self._resolve_model(request)
        gemini_payload = _openai_to_gemini(request)

        url = f"{self.base_url}/{model}:generateContent?key={api_key}"

        resp = await self.http_client.post(
            url,
            headers={"Content-Type": "application/json"},
            json=gemini_payload,
        )

        if resp.status_code == 429:
            raise RateLimitError(provider_name=self.name)
        if resp.status_code >= 400:
            raise ProviderError(
                message=resp.text[:300],
                status_code=resp.status_code,
                provider_name=self.name,
            )

        return _gemini_to_openai(resp.json(), model)

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        model = self._resolve_model(request)
        gemini_payload = _openai_to_gemini(request)
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        url = f"{self.base_url}/{model}:streamGenerateContent?alt=sse&key={api_key}"

        async with self.http_client.stream(
            "POST",
            url,
            headers={"Content-Type": "application/json"},
            json=gemini_payload,
        ) as resp:
            if resp.status_code == 429:
                raise RateLimitError(provider_name=self.name)
            if resp.status_code >= 400:
                await resp.aread()
                raise ProviderError(
                    message=resp.text[:300],
                    status_code=resp.status_code,
                    provider_name=self.name,
                )

            buffer = ""
            async for raw in resp.aiter_text():
                buffer += raw
                while "\n\n" in buffer:
                    event, buffer = buffer.split("\n\n", 1)
                    event = event.strip()
                    if event.startswith("data: "):
                        json_str = event[6:]
                        try:
                            gemini_chunk = json.loads(json_str)
                            sse = _gemini_chunk_to_sse(gemini_chunk, model, chunk_id)
                            yield sse
                        except json.JSONDecodeError:
                            continue

            yield "data: [DONE]\n\n"

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return request.estimate_tokens()


def _gemini_chunk_to_sse(chunk: dict[str, object], model: str, chunk_id: str) -> str:
    """Convert a Gemini streaming chunk to OpenAI SSE format."""
    candidates = chunk.get("candidates", [{}])  # type: ignore[arg-type]
    first = candidates[0] if candidates else {}  # type: ignore[index]
    parts = first.get("content", {}).get("parts", [])  # type: ignore[union-attr]
    text = parts[0].get("text", "") if parts else ""  # type: ignore[index]

    gemini_finish = first.get("finishReason")  # type: ignore[union-attr]
    finish_reason = None
    if gemini_finish:
        finish_map = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
        }
        finish_reason = finish_map.get(gemini_finish, "stop")  # type: ignore[arg-type]

    openai_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": text} if text else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(openai_chunk)}\n\n"
