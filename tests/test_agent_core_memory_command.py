import unittest
from agent_core.runtime import AgentRuntime
from agent_core.contracts import AgentContext, ToolCall

class StubExecutor:
    async def __call__(self, call: ToolCall, context):
        raise AssertionError('memory command must not call tools')

class MemoryCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_command_returns_ack(self):
        runtime = AgentRuntime(tool_executor=StubExecutor())
        result = await runtime.chat('以后回答都先给结论', context=AgentContext(user_id=1), latest_year=2026)
        self.assertEqual(result['intent'], 'memory_command')
        self.assertIn('已记录', result['answer'])
        self.assertEqual(result['tool_calls'], [])
        self.assertEqual(result['self_check']['action'], 'accepted')

if __name__ == '__main__':
    unittest.main()
