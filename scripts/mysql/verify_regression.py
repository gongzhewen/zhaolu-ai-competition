from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for source_path in (
    ROOT / "packages" / "agent_core",
    ROOT / "packages" / "data_contracts",
    ROOT / "apps" / "api",
):
    sys.path.insert(0, str(source_path))
env_file = ROOT / "apps" / "api" / ".env.mysql"
if "DATABASE_URL" not in os.environ and env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

if "DATABASE_URL" not in os.environ:
    raise SystemExit("DATABASE_URL is not configured")

os.environ.setdefault("JWT_SECRET", "local_test_secret_for_mysql_regression_32_bytes")
os.environ.setdefault("DATABASE_NULL_POOL", "true")

from app.main import app
from fastapi.testclient import TestClient

QUESTIONS = [
    ("admissions_overview", "2026年湖南招生多少人"),
    ("source_overview", "生源渠道和报到情况怎么样"),
    ("candidate_profile", "考生性别和科类分布怎么样"),
    ("subject_scores", "计算机科学与技术专业各科平均分"),
    ("major_choices", "哪个专业最火"),
    ("medical_summary", "体检结论如何"),
    ("forecast", "明年土木工程招生预测"),
    ("official_admission_stats", "2026年官方招生统计"),
    ("major_alias_lookup", "计科是什么专业"),
    ("student_statistics", "2026年录取的姓王的学生有多少"),
    ("student_lookup", "分析2026年录取的王小明"),
    ("anomaly_detection", "2026年有哪些专业异常风险"),
    ("plan_simulation", "如果土木工程增加20个计划，录取和风险会怎样变化"),
    ("policy_faq", "平行志愿如何投档"),
    ("policy_faq", "新生到校比例怎么理解？"),
    ("consultation_overview", "2026年咨询渠道转化率怎么样"),
    ("enrollment_funnel", "2026年招生漏斗和报到流失情况"),
    ("score_band_statistics", "2026年政治分数段分布"),
]


def main() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "ChangeMe123!"},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        passed = 0
        for expected_intent, question in QUESTIONS:
            response = client.post(
                "/api/v1/agent/chat",
                headers=headers,
                json={"message": question, "context": {}},
            )
            response.raise_for_status()
            payload = response.json()
            actual_intent = payload["intent"]
            if actual_intent != expected_intent:
                raise AssertionError(
                    f"intent mismatch: expected={expected_intent}, actual={actual_intent}, question={question}"
                )
            print(f"OK | {actual_intent} | {question}")
            passed += 1
    print(f"result={passed}/{len(QUESTIONS)}")
    if passed != len(QUESTIONS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()



