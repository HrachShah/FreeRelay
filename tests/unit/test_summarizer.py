import pytest

from freerelay.core.intelligence.summarizer import summarize_messages
from freerelay.core.models.openai import Message


def messages(count: int) -> list[Message]:
    return [Message(role="user", content=f"message {index}.") for index in range(count)]


def test_zero_recent_messages_still_summarizes_all_history():
    result = summarize_messages(messages(3), keep_last_n=0)

    assert len(result) == 1
    assert result[0].role == "system"
    assert "message 0" in result[0].content


def test_negative_recent_message_count_is_rejected():
    with pytest.raises(ValueError, match="keep_last_n"):
        summarize_messages(messages(3), keep_last_n=-1)


def test_non_positive_summary_budget_is_rejected():
    with pytest.raises(ValueError, match="max_summary_tokens"):
        summarize_messages(messages(3), max_summary_tokens=0)
