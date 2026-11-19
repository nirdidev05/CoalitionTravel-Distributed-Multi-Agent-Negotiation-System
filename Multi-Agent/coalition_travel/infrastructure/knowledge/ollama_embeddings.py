"""Ollama embedding adapter; isolated from application and domain rules."""

import json
from math import isfinite
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from coalition_travel.application.knowledge import KnowledgeRetrievalError


class OllamaEmbedder:
    def __init__(
        self, model: str, base_url: str = "http://localhost:11434", timeout_seconds: float = 30
    ):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("embedding model must not be blank")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        request = Request(
            f"{self.base_url}/api/embed",
            data=json.dumps({"model": self.model, "input": text}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                embeddings = json.loads(response.read().decode())["embeddings"]
                vector = embeddings[0]
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
        ) as exc:
            raise KnowledgeRetrievalError("Ollama embedding request failed") from exc
        if not isinstance(vector, list) or not vector:
            raise KnowledgeRetrievalError("Ollama returned an invalid embedding")
        try:
            return [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise KnowledgeRetrievalError("Ollama returned a non-numeric embedding") from exc
