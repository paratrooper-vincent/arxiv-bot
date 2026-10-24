"""Semantic Scholar 数据源：图谱检索接口（免 key，限频 100 次/5 分钟）。

论文若带 arXiv 外链 id，则 paper_id 直接用 arxiv: 前缀，
与 arXiv 主源的同一篇论文天然去重合并。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

from ..config import AppConfig
from ..models import Paper
from ..utils import retry_call
from .base import Source

logger = logging.getLogger(__name__)
_API = "https://api.semanticscholar.org/graph/v1/paper/search"


class SemanticScholarSource(Source):
    name = "semantic_scholar"

    def __init__(self, limit: int = 20):
        self._limit = limit

    def fetch(self, cfg: AppConfig) -> List[Paper]:
        query = " ".join(cfg.keywords)

        def do() -> List[Paper]:
            resp = requests.get(
                _API,
                params={
                    "query": query,
                    "limit": self._limit,
                    "fields": "title,abstract,authors,year,externalIds,publicationDate,url",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse(resp.json())

        # S2 限频严格，退避放宽一点
        return retry_call(do, "SemanticScholar", times=3, wait=8)

    def _parse(self, data: Dict[str, Any]) -> List[Paper]:
        papers = []
        for item in data.get("data", []):
            if not item.get("title"):
                continue
            arxiv_id = (item.get("externalIds") or {}).get("ArXiv")
            paper_id = f"arxiv:{arxiv_id}" if arxiv_id else f"s2:{item['paperId']}"
            link = (
                f"https://arxiv.org/abs/{arxiv_id}"
                if arxiv_id
                else item.get("url", f"https://www.semanticscholar.org/paper/{item['paperId']}")
            )
            papers.append(
                Paper(
                    paper_id=paper_id,
                    title=item["title"].strip(),
                    abstract=(item.get("abstract") or "").strip(),
                    authors=[a.get("name", "") for a in item.get("authors", [])][:8],
                    categories=["semantic-scholar"],
                    published=item.get("publicationDate") or str(item.get("year") or ""),
                    link=link,
                    source="s2" if not arxiv_id else "arxiv",
                )
            )
        return papers
