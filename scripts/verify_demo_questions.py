from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "agent_core"))
sys.path.insert(0, str(ROOT / "packages" / "data_contracts"))

from app.modules.agent.demo_catalog import DEMO_QUESTIONS


def main() -> None:
    api_base = os.environ.get("DEMO_API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
    username = os.environ.get("DEMO_USERNAME", "admin")
    password = os.environ.get("DEMO_PASSWORD", "ChangeMe123!")
    timeout = float(os.environ.get("DEMO_HTTP_TIMEOUT_SECONDS", "60"))

    with httpx.Client(timeout=timeout) as client:
        login = client.post(f"{api_base}/auth/login", data={"username": username, "password": password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        passed = 0
        for item in DEMO_QUESTIONS:
            question = str(item["question"])
            response = client.post(
                f"{api_base}/agent/chat",
                headers=headers,
                json={"message": question, "context": {}},
            )
            response.raise_for_status()
            payload = response.json()
            actual_intent = str(payload.get("intent"))
            if actual_intent != item["intent"]:
                raise AssertionError(f"意图错误: {question} expected={item['intent']} actual={actual_intent}")
            tool_names = [str(call.get("name")) for call in payload.get("tool_calls", [])]
            expected_tool = item.get("tool")
            if expected_tool and expected_tool not in tool_names:
                raise AssertionError(f"工具错误: {question} expected={expected_tool} actual={tool_names}")
            answer = str(payload.get("answer") or "")
            for term in item.get("required_terms", ()):
                if term not in answer:
                    raise AssertionError(f"缺少关键词: {question} term={term} answer={answer}")
            for term in item.get("forbidden_terms", ()):
                if term in answer:
                    raise AssertionError(f"出现无关内容: {question} term={term} answer={answer}")
            print(f"PASS | {actual_intent} | {tool_names} | {question}")
            passed += 1
        print(f"result={passed}/{len(DEMO_QUESTIONS)}")


if __name__ == "__main__":
    main()