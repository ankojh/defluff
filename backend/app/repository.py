from app.db import database
from app.models import UrlRecord, UrlStatus


async def create_url_submission(url: str) -> UrlRecord:
    query = """
        insert into url_submissions (url, status)
        values ($1, $2)
        returning id, url, status, created_at, updated_at
    """

    async for connection in database.connection():
        row = await connection.fetchrow(query, url, UrlStatus.pending.value)
        if row is None:
            raise RuntimeError("Failed to create URL submission")
        return UrlRecord(**dict(row))

    raise RuntimeError("Database connection was not available")
