"""GitHub Trending 数据源（代理实现）。

GitHub 官方没有 Trending API，这里用 Search API 检索
「最近 7 天创建、指定 topic、按 star 排序」的仓库作为等价情报流。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests

from ..config import AppConfig
from ..models import Paper
from ..utils import retry_call
from .base import Source

logger = logging.getLogger(__name__)
_API = "https://api.github.com/search/repositories"


class GitHubTrendingSource(Source):
    name = "github_trending"

    def __init__(self, topic: str = "robotics", limit: int = 10):
        self._topic = topic
        self._limit = limit

    def fetch(self, cfg: AppConfig) -> List[Paper]:
        since = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

        def do() -> List[Paper]:
            resp = requests.get(
                _API,
                params={
                    "q": f"topic:{self._topic} created:>{since}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": self._limit,
                },
                headers={"Accept": "application/vnd.github+json"},
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse(resp.json())

        return retry_call(do, "GitHubTrending", times=2, wait=5)

    def _parse(self, data: Dict[str, Any]) -> List[Paper]:
        papers = []
        for item in data.get("items", []):
            desc = (item.get("description") or "").strip()
            stars = item.get("stargazers_count", 0)
            papers.append(
                Paper(
                    paper_id=f"gh:{item['full_name']}",
                    title=f"[GitHub] {item['full_name']} (★{stars})",
                    abstract=desc or "（无描述）",
                    authors=[(item.get("owner") or {}).get("login", "")],
                    categories=[f"topic:{t}" for t in item.get("topics", [])[:3]],
                    published=(item.get("created_at") or "")[:10],
                    link=item.get("html_url", ""),
                    source="github",
                )
            )
        return papers
