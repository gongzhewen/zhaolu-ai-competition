import unittest

from app.core.config import Settings
from app.core.database import SchoolDataPlaneUnavailable, agent_data_session


class SchoolDataPlaneConfigTests(unittest.TestCase):
    def test_default_database_is_used_without_school_map(self):
        config = Settings(_env_file=None, database_url="mysql+asyncmy://default/db")
        self.assertEqual(
            config.database_url_for_school(2),
            "mysql+asyncmy://default/db",
        )

    def test_configured_map_never_falls_back_for_unknown_school(self):
        config = Settings(
            _env_file=None,
            database_url="mysql+asyncmy://default/db",
            school_database_urls='{"1":"mysql+asyncmy://school1/db"}',
        )
        self.assertEqual(
            config.database_url_for_school(1),
            "mysql+asyncmy://school1/db",
        )
        self.assertIsNone(config.database_url_for_school(2))
        self.assertIsNone(config.database_url_for_school(None))

    def test_invalid_school_map_is_ignored_atomically(self):
        config = Settings(
            _env_file=None,
            school_database_urls='{"bad": "mysql+asyncmy://school/db", "2": 3}',
        )
        self.assertEqual(config.school_database_url_map, {})


class SchoolDataPlaneSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_mapped_school_raises_instead_of_using_control_db(self):
        from app.core.config import settings

        previous = settings.school_database_urls
        settings.school_database_urls = '{"1":"mysql+asyncmy://school1/db"}'
        try:
            with self.assertRaises(SchoolDataPlaneUnavailable):
                async with agent_data_session(object(), 2):
                    pass
        finally:
            settings.school_database_urls = previous


if __name__ == "__main__":
    unittest.main()
