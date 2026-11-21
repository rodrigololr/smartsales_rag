"""Minimal OpenAI-compatible model fixture for the two F05 journeys."""

import json
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MATERIAL_ANSWER = (
    "Podem ser usadas formas de silicone, papel manteiga próprio para airfryer e formas de "
    "alumínio que caibam no cesto, deixando espaço para a circulação de ar "
    "[Fonte: Manual Airfryer SmartChef 4L, p. 14]."
)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def embedding(text: str, dimensions: int) -> list[float]:
    normalized = normalize(text)
    if "aluminio" in normalized:
        topic = 0
    elif "cotacao do dolar" in normalized:
        topic = 1
    else:
        topic = 2
    vector = [0.0] * dimensions
    vector[topic] = 1.0
    return vector


class ModelFixture(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"status": "ok"})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/v1/embeddings":
            self._embeddings(payload)
        elif self.path == "/v1/chat/completions":
            self._chat(payload)
        else:
            self.send_error(404)

    def _embeddings(self, payload: dict[str, Any]) -> None:
        texts = payload["input"]
        if isinstance(texts, str):
            texts = [texts]
        self._json(
            {
                "object": "list",
                "model": "f05-embeddings",
                "usage": {"prompt_tokens": 0, "total_tokens": 0},
                "data": [
                    {
                        "object": "embedding",
                        "index": index,
                        "embedding": embedding(text, payload.get("dimensions", 1536)),
                    }
                    for index, text in enumerate(texts)
                ],
            }
        )

    def _chat(self, payload: dict[str, Any]) -> None:
        question = normalize(payload["messages"][-1]["content"])
        if "aluminio" not in question:
            self._send(b"data: [DONE]\n\n", "text/event-stream")
            return
        event = {
            "id": "f05",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "f05-chat",
            "choices": [
                {"index": 0, "delta": {"content": MATERIAL_ANSWER}, "finish_reason": "stop"}
            ],
        }
        body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode()
        self._send(body, "text/event-stream")

    def _json(self, payload: dict[str, Any]) -> None:
        self._send(json.dumps(payload).encode(), "application/json")

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), ModelFixture).serve_forever()
