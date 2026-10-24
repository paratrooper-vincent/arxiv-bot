"""抓取器：调用 arXiv 官方 Atom 接口拉取最新论文（失败自动重试）。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List

import feedparser
import requests

from .config import AppConfig
from .models import Paper
from .utils import retry_call

logger = logging.getLogger(__name__)
_API_URL = "http://export.arxiv.org/api/query"


def _to_paper(entry: Any) -> Paper:
    """feedparser 条目 -> 统一 Paper 模型。"""
    short_id = entry.get("id", "").split("/abs/")[-1]
    published = ""
    if getattr(entry, "published_parsed", None):
        published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
    return Paper(
        paper_id=f"arxiv:{short_id}",
        title=entry.get("title", "").strip().replace("\n", " "),
        abstract=entry.get("summary", "").strip().replace("\n", " "),
        authors=[a.get("name", "") for a in entry.get("authors", [])],
        categories=[t.get("term", "") for t in entry.get("tags", [])],
        published=published,
        link=entry.get("link", "").replace("http://", "https://"),
        source="arxiv",
    )


def fetch_arxiv(cfg: AppConfig) -> List[Paper]:
    """按栏目抓取最新论文（按提交时间倒序）。"""
    params = {
        "search_query": " OR ".join(f"cat:{c}" for c in cfg.categories),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": cfg.fetch_count,
    }

    def do() -> List[Paper]:
        resp = requests.get(
            _API_URL,
            params=params,
            timeout=30,
            headers={"User-Agent": "arxiv-bot/2.0"},
        )
        resp.raise_for_status()
        papers = [_to_paper(e) for e in feedparser.parse(resp.text).entries if e.get("id")]
        logger.info("arXiv 抓取成功：%d 篇（栏目 %s）", len(papers), cfg.categories)
        return papers

    return retry_call(do, "抓取arXiv")
