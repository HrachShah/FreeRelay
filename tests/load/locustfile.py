"""
FreeRelay — Load Testing with Locust
========================================
Simulates 1000 concurrent users hitting the FreeRelay endpoint.
Run with: locust -f tests/load/locustfile.py --host=http://localhost:8000
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task


class FreeRelayUser(HttpUser):
    """Simulated FreeRelay user for load testing."""

    wait_time = between(0.5, 2.0)  # Wait 0.5-2s between requests

    @task(5)
    def chat_completion(self) -> None:
        """Send a chat completion request."""
        messages = [
            {
                "role": "user",
                "content": random.choice(
                    [
                        "Hello, how are you?",
                        "What is the capital of France?",
                        "Write a haiku about coding.",
                        "Explain quantum computing in simple terms.",
                        "What is 2 + 2?",
                        "Tell me a joke.",
                        "Summarize the history of Python.",
                        "What is the meaning of life?",
                        "How do I make a cake?",
                        "What is machine learning?",
                    ]
                ),
            },
        ]

        self.client.post(
            "/v1/chat/completions",
            json={
                "messages": messages,
                "max_tokens": 100,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    @task(1)
    def list_models(self) -> None:
        """List available models."""
        self.client.get("/v1/models", timeout=10)

    @task(1)
    def check_stats(self) -> None:
        """Check provider stats."""
        self.client.get("/v1/stats", timeout=10)

    @task(1)
    def health_check(self) -> None:
        """Health check."""
        self.client.get("/health", timeout=5)
