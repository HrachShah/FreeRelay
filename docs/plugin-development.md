# Provider Development Guide

## Adding a New Provider

FreeRelay uses a plugin architecture. Every provider implements `BaseProvider`.

### Step 1: Create the provider file

```python
# freerelay/providers/my_provider.py

from collections.abc import AsyncIterator
import httpx

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


class MyProvider(BaseProvider):
    name = "my_provider"
    base_url = "https://api.myprovider.com/v1"
    supported_features = {"streaming"}

    _default_model = "my-model-v1"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        if not payload.get("model"):
            payload["model"] = self._default_model

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

        if resp.status_code == 429:
            raise RateLimitError(provider_name=self.name)
        if resp.status_code >= 400:
            raise ProviderError(resp.text[:300], resp.status_code, self.name)

        return ChatCompletionResponse.model_validate(resp.json())

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        # Similar to complete, but yield SSE lines
        payload = self.strip_unsupported_fields(request)
        payload["stream"] = True
        # ... implement streaming
        yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        yield "data: [DONE]\n\n"

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return request.estimate_tokens()
```

### Step 2: Register in `main.py`

Add your provider to the `_build_engine` function in `freerelay/main.py`.

### Step 3: Add to `.env.example`

Add the API key environment variable.

### Step 4: Add capability info

Add your models to `freerelay/config/capability_matrix.yaml`.

That's it — ~50 lines of code to add a new provider.
