from types import SimpleNamespace

import pytest
from starlette.responses import JSONResponse

from freerelay.middleware.idempotency import IdempotencyMiddleware


def request_for(key: str, user_id: str, path: str = "/v1/chat/completions") -> SimpleNamespace:
    return SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path=path),
        headers={"X-Idempotency-Key": key},
        state=SimpleNamespace(user_id=user_id),
        client=SimpleNamespace(host="127.0.0.1"),
    )


@pytest.mark.asyncio
async def test_idempotency_cache_is_scoped_to_authenticated_user() -> None:
    middleware = IdempotencyMiddleware(object())
    calls = 0

    async def call_next(_request: object) -> JSONResponse:
        nonlocal calls
        calls += 1
        return JSONResponse({"call": calls})

    first = await middleware.dispatch(request_for("same-key", "user-a"), call_next)
    replay = await middleware.dispatch(request_for("same-key", "user-a"), call_next)
    other_user = await middleware.dispatch(request_for("same-key", "user-b"), call_next)

    assert first.body == b'{"call":1}'
    assert replay.body == b'{"call":1}'
    assert replay.headers["X-Idempotency-Replayed"] == "true"
    assert other_user.body == b'{"call":2}'
    assert calls == 2


@pytest.mark.asyncio
async def test_idempotency_cache_is_scoped_to_request_path() -> None:
    middleware = IdempotencyMiddleware(object())
    calls = 0

    async def call_next(_request: object) -> JSONResponse:
        nonlocal calls
        calls += 1
        return JSONResponse({"call": calls})

    await middleware.dispatch(request_for("same-key", "user-a", "/v1/models"), call_next)
    response = await middleware.dispatch(request_for("same-key", "user-a", "/v1/chat/completions"), call_next)

    assert response.body == b'{"call":2}'
    assert calls == 2


@pytest.mark.asyncio
async def test_idempotency_does_not_replay_failed_responses() -> None:
    middleware = IdempotencyMiddleware(object())
    calls = 0

    async def call_next(_request: object) -> JSONResponse:
        nonlocal calls
        calls += 1
        return JSONResponse({"call": calls}, status_code=503)

    first = await middleware.dispatch(request_for("retryable", "user-a"), call_next)
    retry = await middleware.dispatch(request_for("retryable", "user-a"), call_next)

    assert first.status_code == 503
    assert retry.status_code == 503
    assert retry.body == b'{"call":2}'
    assert "X-Idempotency-Replayed" not in retry.headers
    assert calls == 2
