"""Tests for EmbeddingRequest / EmbeddingResponse wire format."""

from __future__ import annotations

from freerelay.core.models.embeddings import (
    EmbeddingRequest,
    EmbeddingResponse,
)


def test_inputs_as_strings_str() -> None:
    req = EmbeddingRequest(input="hello world")
    assert req.inputs_as_strings() == ["hello world"]


def test_inputs_as_strings_list_str() -> None:
    req = EmbeddingRequest(input=["foo", "bar"])
    assert req.inputs_as_strings() == ["foo", "bar"]


def test_inputs_as_strings_empty_list() -> None:
    req = EmbeddingRequest(input=[])
    assert req.inputs_as_strings() == []


def test_from_vectors() -> None:
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    resp = EmbeddingResponse.from_vectors(
        vectors, model="mistral-embed", prompt_tokens=10
    )
    assert resp.model == "mistral-embed"
    assert len(resp.data) == 2
    assert resp.data[0].index == 0
    assert resp.data[1].embedding == [0.4, 0.5, 0.6]
    assert resp.usage.prompt_tokens == 10
    assert resp.usage.total_tokens == 10


def test_response_serializes_as_list() -> None:
    resp = EmbeddingResponse.from_vectors([[1.0]], model="test")
    d = resp.model_dump()
    assert d["object"] == "list"
    assert d["data"][0]["object"] == "embedding"
