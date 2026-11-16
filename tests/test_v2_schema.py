import ast
import unittest
from pathlib import Path

from app.core.config import Settings
from app.models import Base


class SchemaBaselineTests(unittest.TestCase):
    def test_core_orm_tables_exist(self):
        required = {
            "sys.user_account",
            "sys.role",
            "dim.school",
            "dim.major",
            "fact.enrollment_status",
            "gov.dbf_import_batch",
            "gov.dbf_interface_profile",
            "ai.agent_memory",
            "ai.prompt_template",
            "ai.response_evaluation",
        }
        self.assertTrue(required.issubset(set(Base.metadata.tables)))

    def test_settings_preserve_agent_flags(self):
        settings = Settings(
            database_url="postgresql+asyncpg://u:p@db:5432/zhaolu",
            agent_min_data_support=0.65,
            minimind_enabled=True,
        )
        self.assertEqual(settings.sync_database_url, "postgresql+psycopg://u:p@db:5432/zhaolu")
        self.assertEqual(settings.agent_min_data_support, 0.65)
        self.assertTrue(settings.minimind_enabled)

    def test_migration_chain_contains_agent_and_runtime_updates(self):
        versions_dir = Path(__file__).parents[1] / "apps" / "api" / "alembic" / "versions"
        revisions = {}
        for path in versions_dir.glob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8"))
            values = {}
            for node in module.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if node.targets[0].id in {"revision", "down_revision"}:
                        try:
                            values[node.targets[0].id] = ast.literal_eval(node.value)
                        except (ValueError, TypeError):
                            values[node.targets[0].id] = None
            if "revision" in values:
                revisions[values["revision"]] = values.get("down_revision")
        expected = {f"{number:04d}" for number in range(1, 17)}
        normalized = {str(key)[:4] for key in revisions if key}
        self.assertTrue(expected.issubset(normalized))
        latest_prefix = sorted(normalized)[-1]
        self.assertTrue(any(str(key).startswith(latest_prefix) for key in revisions))


if __name__ == "__main__":
    unittest.main()


