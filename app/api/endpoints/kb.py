"""Knowledge Base — serve raw markdown articles.

Each client can have its own knowledge base folder; clients without one see
the default `velora_kb/`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db

router = APIRouter()

_ROOT = Path(__file__).parent.parent.parent.parent
_KB_DIR = _ROOT / "velora_kb"

# Client code -> its own knowledge base folder, beside the default one.
_CLIENT_KB_DIRS = {
    "ARCELOR-MITTAL": _ROOT / "velora_kb_sox_poc2",
}


async def _kb_dir(db: AsyncSession, client_id: int | None) -> Path:
    """The selected client's knowledge base, or the default one."""
    if client_id is not None:
        from app.models.client import Client

        client = await db.get(Client, client_id)
        folder = _CLIENT_KB_DIRS.get(client.client_code) if client else None
        if folder is not None and folder.is_dir():
            return folder
    return _KB_DIR

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FM_KEY_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def _parse_fm(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}
    return dict(_FM_KEY_RE.findall(m.group(1)))


class KBArticle(BaseModel):
    slug: str
    title: str


class KBNode(BaseModel):
    id: str
    title: str
    color: str | None = None
    node_type: str | None = None


class KBLink(BaseModel):
    source: str
    target: str


class KBGraph(BaseModel):
    nodes: list[KBNode]
    links: list[KBLink]


@router.get("/articles", response_model=list[KBArticle])
async def list_articles(
    client_id: int | None = Query(default=None),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KBArticle]:
    kb_dir = await _kb_dir(db, client_id)
    if not kb_dir.exists():
        return []
    articles = []
    for f in sorted(kb_dir.glob("*.md")):
        title = f.stem
        slug = f.stem
        articles.append(KBArticle(slug=slug, title=title))
    return articles


@router.get("/graph", response_model=KBGraph)
async def get_graph(
    client_id: int | None = Query(default=None),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KBGraph:
    kb_dir = await _kb_dir(db, client_id)
    if not kb_dir.exists():
        return KBGraph(nodes=[], links=[])

    slug_map: dict[str, str] = {}  # title → slug
    raw_files: dict[str, str] = {}

    for f in kb_dir.glob("*.md"):
        slug = f.stem
        slug_map[f.stem] = slug
        raw_files[slug] = f.read_text(encoding="utf-8")

    nodes: list[KBNode] = []
    links: list[KBLink] = []
    seen_links: set[tuple[str, str]] = set()

    for slug, text in raw_files.items():
        fm = _parse_fm(text)
        nodes.append(KBNode(
            id=slug,
            title=slug,
            color=fm.get("color"),
            node_type=fm.get("nodeType"),
        ))
        for wikilink in _WIKILINK_RE.findall(text):
            target_slug = wikilink.strip()
            if target_slug in slug_map and target_slug != slug:
                key = (min(slug, target_slug), max(slug, target_slug))
                if key not in seen_links:
                    seen_links.add(key)
                    links.append(KBLink(source=slug, target=target_slug))

    return KBGraph(nodes=nodes, links=links)


@router.get("/articles/{slug}")
async def get_article(
    slug: str,
    client_id: int | None = Query(default=None),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    kb_dir = await _kb_dir(db, client_id)
    # Prevent path traversal
    safe = (kb_dir / f"{slug}.md").resolve()
    if not safe.is_relative_to(kb_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid slug.")
    if not safe.exists():
        raise HTTPException(status_code=404, detail="Article not found.")
    return {"slug": slug, "title": slug, "content": safe.read_text(encoding="utf-8")}
