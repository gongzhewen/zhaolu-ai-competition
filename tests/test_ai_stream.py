from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.modules.agent.schemas import ChatRequest
from app.modules.agent.service import AgentService
from app.modules.ai_gateway.router import ai_chat_stream


class AiStreamTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_timeout = settings.agent_chat_timeout_seconds
        self.original_heartbeat = settings.agent_stream_heartbeat_seconds
        settings.agent_stream_heartbeat_seconds = 0.005
        self.assertEqual(settings.agent_stream_heartbeat_seconds, 0.005)

    async def asyncTearDown(self):
        settings.agent_chat_timeout_seconds = self.original_timeout
        settings.agent_stream_heartbeat_seconds = self.original_heartbeat

    async def test_stream_emits_heartbeats_and_answer(self):
        async def fake_chat(*_args, **_kwargs):
            await asyncio.sleep(0.15)
            return {"answer": "完成", "message_id": 1}

        settings.agent_chat_timeout_seconds = 0.5
        with patch.object(AgentService, "chat", new=fake_chat):
            response = await ai_chat_stream(
                ChatRequest(message="测试问题"),
                user=object(),
                db=object(),
            )
            chunks = [chunk if isinstance(chunk, str) else chunk.decode() async for chunk in response.body_iterator]
        body = "".join(chunks)
        self.assertGreaterEqual(body.count("event: heartbeat"), 2)
        self.assertIn("event: answer", body)

    async def test_stream_timeout_emits_error(self):
        async def slow_chat(*_args, **_kwargs):
            await asyncio.sleep(0.1)
            return {"answer": "不应返回"}

        settings.agent_chat_timeout_seconds = 0.02
        with patch.object(AgentService, "chat", new=slow_chat):
            response = await ai_chat_stream(
                ChatRequest(message="测试问题"),
                user=object(),
                db=object(),
            )
            chunks = [chunk if isinstance(chunk, str) else chunk.decode() async for chunk in response.body_iterator]
        body = "".join(chunks)
        self.assertIn("event: error", body)
        self.assertNotIn("event: answer", body)
        self.assertNotIn("event: answer", body)


if __name__ == "__main__":
    unittest.main()
