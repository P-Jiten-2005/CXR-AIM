import unittest
from sqlalchemy import select, inspect
from app.core.database import AsyncSessionLocal, engine, run_additive_migrations
from app.models import models
import asyncio

class TestDatabaseMigrations(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Run migrations before testing columns/tables
        await run_additive_migrations()

    async def test_columns_exist(self):
        async with engine.connect() as conn:
            # We inspect the columns in the shots table
            def inspect_cols(connection):
                inspector = inspect(connection)
                return [col["name"] for col in inspector.get_columns("shots")]
            columns = await conn.run_sync(inspect_cols)
            self.assertIn("verdict", columns)
            self.assertIn("verdict_explanation", columns)
            self.assertIn("confidence_score", columns)

    async def test_tables_exist(self):
        async with engine.connect() as conn:
            # We inspect the tables in the database
            def inspect_tables(connection):
                inspector = inspect(connection)
                return inspector.get_table_names()
            tables = await conn.run_sync(inspect_tables)
            self.assertIn("lane_configs", tables)
            self.assertIn("verification_audits", tables)
