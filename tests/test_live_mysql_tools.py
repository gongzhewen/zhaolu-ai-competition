from __future__ import annotations

import os
import unittest

from app.core.config import settings
from app.core.text import text

LIVE_MYSQL_TESTS = os.environ.get("LIVE_MYSQL_TESTS") == "1"


@unittest.skipUnless(LIVE_MYSQL_TESTS, "set LIVE_MYSQL_TESTS=1 to run MySQL integration tests")
class LiveMysqlToolRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import AsyncSessionLocal

        self.original_vector_enabled = settings.rag_vector_enabled
        settings.rag_vector_enabled = False
        self.db = AsyncSessionLocal()

    async def asyncTearDown(self):
        from app.core.database import engine
        settings.rag_vector_enabled = self.original_vector_enabled
        await self.db.close()
        await engine.dispose()

    async def test_all_eighteen_native_tools_return_contract_payloads(self):
        from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

        student_name = await self.db.scalar(
            text(
                """
                SELECT si.student_name
                FROM fact.student_identity si
                JOIN fact.admission_record ar ON ar.candidate_key=si.candidate_key
                WHERE si.year_no=2026 AND si.student_name IS NOT NULL
                LIMIT 1
                """
            )
        )
        self.assertTrue(student_name)
        cases = [
            ("admissions_overview", {"year": 2026, "province": "湖南", "query": "2026年湖南招生多少人"}),
            ("source_overview", {"year": 2026}),
            ("candidate_profile", {"year": 2026}),
            ("subject_scores", {"year": 2026, "major": "计算机科学与技术"}),
            ("major_choices", {"year": 2026}),
            ("medical_summary", {"year": 2026}),
            ("forecast", {"year": 2026}),
            ("official_admission_stats", {"year": 2026}),
            ("major_alias_lookup", {"source_name": "计科"}),
            ("student_lookup", {"student_name": str(student_name), "year": 2026, "can_lookup_students": True}),
            ("student_statistics", {"year": 2026, "surname": "王"}),
            ("anomaly_detection", {"year": 2026}),
            ("plan_simulation", {"year": 2026, "major": "土木工程", "plan_delta": 20}),
            ("policy_faq", {"query": "平行志愿如何投档"}),
            ("consultation_overview", {"year": 2026}),
            ("enrollment_funnel", {"year": 2026}),
            ("score_band_statistics", {"year": 2026, "subject_name": "政治"}),
            ("admissions_statistics", {"year": 2026, "query": "2026年各专业一志愿录取率和调剂率", "group_by": "major_name"}),
        ]
        self.assertEqual({name for name, _params in cases}, set(NATIVE_TOOL_EXECUTORS))
        for name, params in cases:
            with self.subTest(tool=name):
                result = await NATIVE_TOOL_EXECUTORS[name](self.db, params)
                self.assertIsInstance(result, dict)
                self.assertIsInstance(result.get("answer"), str)
                self.assertTrue(result["answer"])
                self.assertIsInstance(result.get("charts"), list)
                self.assertIsInstance(result.get("metrics"), dict)
                self.assertIsInstance(result.get("data_sources"), list)
                self.assertIn("table", result)

        admission = await NATIVE_TOOL_EXECUTORS["admissions_overview"](
            self.db,
            {"year": 2026, "province": "湖南", "query": "2026年湖南招生多少人"},
        )
        self.assertGreater(admission["metrics"].get("plan_count", 0), 0)
        funnel = await NATIVE_TOOL_EXECUTORS["enrollment_funnel"](self.db, {"year": 2026})
        self.assertGreater(funnel["metrics"].get("plan_count", 0), 0)
        bands = await NATIVE_TOOL_EXECUTORS["score_band_statistics"](
            self.db,
            {"year": 2026, "subject_name": "政治"},
        )
        self.assertGreater(bands["metrics"].get("total_students", 0), 0)

    async def test_admissions_statistics_dimension_matrix(self):
        from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

        cases = [
            ("按年份统计计划数、录取数、报到率", "year_no"),
            ("按省份统计计划数和录取数", "province_name"),
            ("按科类统计录取数和平均分", "subject_name"),
            ("按批次统计录取数", "batch_name"),
            ("按专业统计计划完成率、志愿率和调剂率", "major_name"),
            ("按学院统计录取数和报到率", "major_group"),
            ("按层次统计计划数和录取数", "level_name"),
            ("按招生类型统计计划数和录取数", "plan_type"),
            ("按性别统计录取数", "gender_name"),
            ("按生源高中统计录取数", "source_school_name"),
            ("按考生类别统计录取数", "candidate_type_code"),
            ("按外语语种统计录取数", "foreign_language_code"),
            ("按选科要求统计计划数", "subject_req"),
            ("按专业代码统计计划数", "major_code"),
        ]
        for query, expected_group_by in cases:
            with self.subTest(group_by=expected_group_by):
                result = await NATIVE_TOOL_EXECUTORS["admissions_statistics"](
                    self.db,
                    {
                        "school_id": 1,
                        "year": 2026,
                        "query": query,
                        "group_by": expected_group_by,
                    },
                )
                self.assertEqual(result["metrics"]["group_by"], expected_group_by)
                self.assertFalse(result["metrics"]["unsupported"])
                self.assertGreater(result["metrics"]["row_count"], 0)
                self.assertIsInstance(result["table"], dict)

    async def test_admissions_statistics_metric_matrix(self):
        from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

        queries = [
            "2026年计划数、录取数和计划完成率",
            "2026年报到数、报到率和未报到人数",
            "2026年最高分、最低分、平均分、中位分和下四分位分",
            "2026年最高分位次、最低分位次和平均分位次",
            "2026年志愿数、志愿率、报考数和报考率",
            "2026年一志愿录取数、一志愿录取率和一志愿报考率",
            "2026年调剂数和调剂率",
            "2026年男生数和女生数",
        ]
        for query in queries:
            with self.subTest(query=query):
                result = await NATIVE_TOOL_EXECUTORS["admissions_statistics"](
                    self.db,
                    {"school_id": 1, "year": 2026, "query": query},
                )
                self.assertIsInstance(result["metrics"], dict)
                self.assertFalse(result["metrics"].get("unsupported"))
                self.assertIsInstance(result["table"], dict)
                self.assertGreaterEqual(result["metrics"]["row_count"], 1)

    async def test_admissions_statistics_empty_and_unsupported_contracts(self):
        from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

        empty = await NATIVE_TOOL_EXECUTORS["admissions_statistics"](
            self.db,
            {
                "school_id": 1,
                "year": 2099,
                "query": "2099年各专业计划完成率",
                "group_by": "major_name",
            },
        )
        self.assertEqual(empty["metrics"]["row_count"], 0)
        self.assertIn("没有找到", empty["answer"])

        unsupported = await NATIVE_TOOL_EXECUTORS["admissions_statistics"](
            self.db,
            {
                "school_id": 1,
                "year": 2026,
                "query": "按地市和校区统计征集数、省控线和位次占比",
            },
        )
        self.assertIsNone(unsupported["table"])
        self.assertTrue(unsupported["metrics"]["unsupported"])
        self.assertIn("无法可靠计算", unsupported["answer"])

    async def test_admissions_statistics_top_n_is_bounded(self):
        from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

        result = await NATIVE_TOOL_EXECUTORS["admissions_statistics"](
            self.db,
            {
                "school_id": 1,
                "year": 2026,
                "query": "按专业统计录取数",
                "group_by": "major_name",
                "top_n": 999,
            },
        )
        self.assertLessEqual(result["metrics"]["row_count"], 50)


if __name__ == "__main__":
    unittest.main()
