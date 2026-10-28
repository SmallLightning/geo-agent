"""Verify the LLM client against a local fake OpenAI-compatible server.

Proves the request/response plumbing works without any real API key — useful before
the MiniMax / StepFun credentials arrive, and as a regression test afterwards.

    python3 -m unittest tests.test_llm -v
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.intent import parse_llm  # noqa: E402
from src.llm import LLMClient, LLMError  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    reply: dict = {}
    last_body: dict = {}
    last_auth: str = ""

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        _Handler.last_body = json.loads(self.rfile.read(length).decode())
        _Handler.last_auth = self.headers.get("Authorization", "")
        body = json.dumps(_Handler.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


def _chat_reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class TestLLMClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def client(self, model="test-model"):
        return LLMClient(
            provider="stepfun",
            api_key="sk-test",
            base_url=f"http://127.0.0.1:{self.port}/v1",
            model=model,
        )

    def test_not_configured(self):
        self.assertFalse(LLMClient(provider="stepfun", api_key="", base_url="", model="").configured)
        with self.assertRaises(LLMError):
            LLMClient(provider="stepfun", api_key="", base_url="", model="").chat([])

    def test_chat_roundtrip(self):
        _Handler.reply = _chat_reply("收到")
        out = self.client().chat([{"role": "user", "content": "只回复两个字：收到"}])
        self.assertEqual(out, "收到")
        self.assertEqual(_Handler.last_auth, "Bearer sk-test")
        self.assertEqual(_Handler.last_body["model"], "test-model")
        self.assertFalse(_Handler.last_body["stream"])

    def test_json_mode_flag(self):
        _Handler.reply = _chat_reply('{"origin":"杭州东站"}')
        out = self.client().chat([{"role": "user", "content": "x"}], json_mode=True)
        self.assertIn("origin", out)
        self.assertEqual(_Handler.last_body["response_format"], {"type": "json_object"})

    def test_parse_llm_merges_model_output(self):
        _Handler.reply = _chat_reply(
            json.dumps(
                {
                    "origin": "杭州东站",
                    "city": "杭州",
                    "keyword": "餐厅",
                    "types": "050000",
                    "budget": 88,
                    "radius_m": 1500,
                    "top": 2,
                    "min_rating": 4.6,
                    "travel_mode": "walking",
                },
                ensure_ascii=False,
            )
        )
        intent = parse_llm(self.client(), "从杭州东站出发，安静点、能停车的餐厅")
        self.assertEqual(intent.source, "llm")
        self.assertEqual(intent.budget, 88.0)
        self.assertEqual(intent.radius_m, 1500)
        self.assertEqual(intent.top, 2)
        self.assertEqual(intent.min_rating, 4.6)
        self.assertEqual(intent.travel_mode, "walking")

    def test_parse_llm_falls_back_on_garbage(self):
        _Handler.reply = _chat_reply("抱歉，我不明白")
        intent = parse_llm(self.client(), "从杭州东站出发，人均100以内的餐厅")
        self.assertEqual(intent.source, "rules")
        self.assertEqual(intent.origin, "杭州东站")
        self.assertEqual(intent.budget, 100.0)


if __name__ == "__main__":
    unittest.main()
