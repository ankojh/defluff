"""SQL access for URL submissions and the personal knowledge store."""

from app.db.session import database
from app.schemas import KnowledgeMatch, LearnRequest, UrlRecord, UrlStatus


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


async def find_knowledge_matches(search_text: str, limit: int = 5) -> list[KnowledgeMatch]:
    """Full-text search learned knowledge items relevant to ``search_text``."""
    query = """
        select
            id,
            source_url as url,
            coalesce(source_title, title) as title,
            summary,
            learned_at as consumed_at,
            ts_rank_cd(
                to_tsvector('english', title || ' ' || summary || ' ' || detail),
                websearch_to_tsquery('english', $1)
            ) as overlap
        from knowledge_items
        where
            to_tsvector('english', title || ' ' || summary || ' ' || detail)
            @@ websearch_to_tsquery('english', $1)
        order by overlap desc, learned_at desc
        limit $2
    """

    async for connection in database.connection():
        rows = await connection.fetch(query, search_text, limit)
        return [KnowledgeMatch(**dict(row)) for row in rows]

    raise RuntimeError("Database connection was not available")


async def remember_learned_item(item: LearnRequest) -> int:
    """Store one chapter/highlight the user marked as learned."""
    query = """
        insert into knowledge_items (kind, source_url, source_title, title, summary, detail)
        values ($1, $2, $3, $4, $5, $6)
        on conflict (source_url, kind, title) do update set
            summary = excluded.summary,
            detail = excluded.detail,
            source_title = excluded.source_title,
            learned_at = now()
        returning id
    """

    async for connection in database.connection():
        row = await connection.fetchrow(
            query,
            item.kind,
            item.source_url,
            item.source_title,
            item.title,
            item.summary,
            item.detail,
        )
        if row is None:
            raise RuntimeError("Failed to store learned knowledge item")
        return int(row["id"])

    raise RuntimeError("Database connection was not available")


async def clear_knowledge() -> int:
    """Delete all stored personal knowledge. Returns the number removed."""
    async for connection in database.connection():
        status = await connection.execute("delete from knowledge_items")
        # asyncpg returns a command tag like "DELETE 5".
        try:
            return int(status.split()[-1])
        except (ValueError, IndexError):
            return 0
    raise RuntimeError("Database connection was not available")
