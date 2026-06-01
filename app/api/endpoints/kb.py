"""Knowledge Base — serve raw markdown articles from velora_kb/."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user

router = APIRouter()

_KB_DIR = Path(__file__).parent.parent.parent.parent / "velora_kb"

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
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> list[KBArticle]:
    if not _KB_DIR.exists():
        return []
    articles = []
    for f in sorted(_KB_DIR.glob("*.md")):
        title = f.stem
        slug = f.stem
        articles.append(KBArticle(slug=slug, title=title))
    return articles


@router.get("/graph", response_model=KBGraph)
async def get_graph(
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> KBGraph:
    if not _KB_DIR.exists():
        return KBGraph(nodes=[], links=[])

    slug_map: dict[str, str] = {}  # title → slug
    raw_files: dict[str, str] = {}

    for f in _KB_DIR.glob("*.md"):
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
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    # Prevent path traversal
    safe = (_KB_DIR / f"{slug}.md").resolve()
    if not str(safe).startswith(str(_KB_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid slug.")
    if not safe.exists():
        raise HTTPException(status_code=404, detail="Article not found.")
    return {"slug": slug, "title": slug, "content": safe.read_text(encoding="utf-8")}
