import unittest

from app.modules.ai_gateway.minimind_router import (
    MiniMindRouter,
    ModelEndpoint,
    ModelRolloutConfig,
)


def endpoints() -> tuple[ModelEndpoint, ModelEndpoint]:
    return (
        ModelEndpoint("stable", "http://stable.local/v1", "stable-model"),
        ModelEndpoint("canary", "http://canary.local/v1", "canary-model"),
    )


def valid_response() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"tools":[{"name":"admissions_overview",'
                        '"params":{"year":2026}}]}'
                    )
                }
            }
        ]
    }


class ModelRolloutTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.config import settings

        self.settings = settings
        self.original_enabled = settings.minimind_enabled
        self.original_redis = settings.redis_enabled
        settings.minimind_enabled = True
        settings.redis_enabled = False

    async def asyncTearDown(self):
        self.settings.minimind_enabled = self.original_enabled
        self.settings.redis_enabled = self.original_redis

    def test_percentage_zero_and_hundred_select_expected_version(self):
        stable, canary = endpoints()
        self.assertEqual(
            ModelRolloutConfig(stable, canary, 0).select("问题", {}).version_id,
            "stable",
        )
        self.assertEqual(
            ModelRolloutConfig(stable, canary, 100).select("问题", {}).version_id,
            "canary",
        )

    def test_selection_is_deterministic_for_same_request(self):
        stable, canary = endpoints()
        rollout = ModelRolloutConfig(stable, canary, 50)
        first = rollout.select("2026年各专业录取数", {"year": 2026}).version_id
        second = rollout.select("2026年各专业录取数", {"year": 2026}).version_id
        self.assertEqual(first, second)

    async def test_canary_failure_falls_back_to_stable(self):
        stable, canary = endpoints()
        called_urls: list[str] = []

        async def post_json(url: str, _payload: dict, _timeout: float) -> dict:
            called_urls.append(url)
            if "canary.local" in url:
                raise TimeoutError("canary unavailable")
            return valid_response()

        router = MiniMindRouter(
            rollout=ModelRolloutConfig(stable, canary, 100),
            post_json=post_json,
        )
        plan = await router.route(
            message="2026年招生多少人",
            fallback_intent="admissions_overview",
            params={"year": 2026},
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["model_version"], "stable")
        self.assertEqual(plan["fallback_from"], "canary")
        self.assertEqual(len(called_urls), 2)

    async def test_canary_success_keeps_canary_version(self):
        stable, canary = endpoints()

        async def post_json(_url: str, payload: dict, _timeout: float) -> dict:
            self.assertEqual(payload["model"], "canary-model")
            return valid_response()

        router = MiniMindRouter(
            rollout=ModelRolloutConfig(stable, canary, 100),
            post_json=post_json,
        )
        plan = await router.route(
            message="2026年招生多少人",
            fallback_intent="admissions_overview",
            params={"year": 2026},
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["model_version"], "canary")
        self.assertNotIn("fallback_from", plan)

    async def test_rollback_to_stable_is_zero_canary_percent(self):
        stable, canary = endpoints()

        async def post_json(url: str, _payload: dict, _timeout: float) -> dict:
            self.assertIn("stable.local", url)
            return valid_response()

        router = MiniMindRouter(
            rollout=ModelRolloutConfig(stable, canary, 0),
            post_json=post_json,
        )
        plan = await router.route(
            message="2026年招生多少人",
            fallback_intent="admissions_overview",
            params={"year": 2026},
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["model_version"], "stable")


if __name__ == "__main__":
    unittest.main()
