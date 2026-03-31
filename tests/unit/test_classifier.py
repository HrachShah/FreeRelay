"""
Tests — Intent Classifier
============================
Verify classification accuracy per spec §14.
"""

from freerelay.core.models.openai import ChatCompletionRequest
from freerelay.core.routing.classifier import classify_intent


class TestClassifier:
    def test_coding_keywords(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Write a Python function to sort a list and debug the error"}],
        )
        assert classify_intent(req) == "coding"

    def test_math_keywords(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Solve this integral equation and prove the theorem"}],
        )
        assert classify_intent(req) == "math"

    def test_creative_keywords(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Write a short story about a character in a fictional world"}],
        )
        assert classify_intent(req) == "creative"

    def test_multilingual_detection(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "これは日本語のテストです"}],
        )
        assert classify_intent(req) == "multilingual"

    def test_cyrillic_multilingual(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Напишите программу на Python"}],
        )
        assert classify_intent(req) == "multilingual"

    def test_short_chat(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "What is the weather today?"}],
        )
        assert classify_intent(req) == "chat"

    def test_tool_use_is_coding(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Get the weather"}],
            tools=[{
                "type": "function",
                "function": {"name": "get_weather", "description": "Get weather"},
            }],
        )
        assert classify_intent(req) == "coding"

    def test_general_fallback(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Tell me about the history of the Roman Empire and its influence on modern governance structures across Europe and the Mediterranean region during the late antiquity period"}],
        )
        assert classify_intent(req) == "general"
