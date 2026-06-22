from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg

from app.config import settings

SCHEMA_PATHS = (
    Path.cwd() / "sql" / "schema.sql",
    Path(__file__).resolve().parent.parent / "sql" / "schema.sql",
)


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(settings.database_url)
        await self.apply_schema()

    async def disconnect(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def apply_schema(self) -> None:
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")

        for schema_path in SCHEMA_PATHS:
            if schema_path.exists():
                schema = schema_path.read_text(encoding="utf-8")
                break
        else:
            raise FileNotFoundError("Could not find sql/schema.sql")

        async with self.pool.acquire() as connection:
            await connection.execute(schema)

    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")

        async with self.pool.acquire() as connection:
            yield connection


database = Database()
