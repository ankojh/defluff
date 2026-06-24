from app.db.repository import (
    clear_knowledge,
    find_knowledge_matches,
    remember_learned_item,
)
from app.schemas import ContentResponse, KnowledgeMatch

__all__ = ["clear_knowledge", "find_related_knowledge", "remember_learned_item"]


async def find_related_knowledge(content: ContentResponse, limit: int = 5) -> list[KnowledgeMatch]:
    """Find learned knowledge items relevant to the content being consumed.

    Matches are fed to the summary as prior knowledge so already-known material
    can be compressed rather than re-explained.
    """
    search_text = _search_text_for(content)
    if not search_text.strip():
        return []

    return await find_knowledge_matches(search_text, limit)


def _search_text_for(content: ContentResponse) -> str:
    if content.title:
        return content.title

    words = content.text.split()
    return " ".join(words[:16])
