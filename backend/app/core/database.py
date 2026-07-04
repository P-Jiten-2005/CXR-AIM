from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
from app.core.config import settings

# For async operations, ensure we use standard dialect patterns (sqlite+aiosqlite)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Columns added after the initial schema. Since the project uses create_all (no Alembic),
# existing databases miss these — we add them idempotently on startup. New databases get
# them from the models directly, so these ALTERs simply no-op there.
_ADDITIVE_COLUMNS = {
    "sessions": [
        ("target_type", "VARCHAR(50) DEFAULT 'figure_11'"),
        ("bullet_caliber", "FLOAT DEFAULT 5.56"),
        ("geometry_homography_json", "JSON"),
        ("unit_number", "VARCHAR(100)"),
        ("session_date", "VARCHAR(64)"),
        ("session_range", "VARCHAR(100)"),
        ("drill_type", "VARCHAR(50)"),
        ("bullets_per_drill", "INTEGER"),
    ],
    "shots": [
        ("score", "INTEGER"),
        ("decimal_score", "FLOAT"),
        ("nearest_ring_value", "INTEGER"),
        ("distance_to_nearest_ring_mm", "FLOAT"),
        ("bullseye_id", "INTEGER"),
        ("distance_to_center_mm", "FLOAT"),
        ("boundary_status", "VARCHAR(50)"),
        ("localization_error_mm", "FLOAT DEFAULT 0.0"),
        ("verdict", "VARCHAR(50)"),
        ("verdict_explanation", "VARCHAR(1024)"),
        ("confidence_score", "FLOAT"),
    ],
}


async def run_additive_migrations():
    """Add any missing additive columns to existing SQLite tables (safe + idempotent)."""
    # Import models to register them on Base.metadata and prevent circular imports
    from app.models import models
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, columns in _ADDITIVE_COLUMNS.items():
            try:
                rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
                existing = {r[1] for r in rows.fetchall()}
            except Exception:
                # Table doesn't exist yet (fresh DB) — create_all will handle it.
                continue
            for col_name, col_def in columns:
                if col_name not in existing:
                    try:
                        await conn.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
                        )
                    except Exception:
                        pass

