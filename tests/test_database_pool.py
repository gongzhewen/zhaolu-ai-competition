import unittest

from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core.database import build_engine_kwargs


class DatabasePoolTests(unittest.TestCase):
    def test_mysql_engine_uses_bounded_async_pool(self):
        kwargs = build_engine_kwargs("mysql+asyncmy://user:pass@localhost/db")
        self.assertEqual(kwargs["poolclass"], AsyncAdaptedQueuePool)
        self.assertEqual(kwargs["pool_size"], 8)
        self.assertEqual(kwargs["max_overflow"], 4)
        self.assertEqual(kwargs["pool_timeout"], 30.0)
        self.assertEqual(kwargs["pool_recycle"], 300)
        self.assertTrue(kwargs["pool_pre_ping"])
        self.assertTrue(kwargs["pool_use_lifo"])


if __name__ == "__main__":
    unittest.main()
