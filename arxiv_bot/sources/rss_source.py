"""通用 RSS 数据源：会议/期刊通知等任意订阅地址（feedparser 解析）。"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, List

import feedparser
import requests

from ..config import AppConfig
from ..models import Paper
from .base import Source

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


class RSSSource(Source):
    name = "rss"

    def __init__(self, urls: List[str]):
        self._urls = urls

    def fetch(self, cfg: AppConfig) -> List[Paper]:
        papers: List[Paper] = []
        for url in self._urls:
            try:
                resp = requests.get(url, timeout=30, headers={"User-Agent": "arxiv-bot/2.0"})
                resp.raise_for_status()
                papers.extend(self._parse(feedparser.parse(resp.text), url))
            except Exception as e:  # noqa: BLE001 —— 单个订阅失败跳过
                logger.error("RSS 订阅失败 %s：%s", url, e)
        return papers

    def _parse(self, parsed: Any, url: str) -> List[Paper]:
        papers = []
        for entry in parsed.entries[:30]:
            entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
            digest = hashlib.md5(entry_id.encode("utf-8")).hexdigest()[:16]
            published = ""
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
            papers.append(
                Paper(
                    paper_id=f"rss:{digest}",
                    title=entry.get("title", "").strip().replace("\n", " "),
                    abstract=_strip_html(entry.get("summary", ""))[:600],
                    authors=[a.get("name", "") for a in entry.get("authors", [])][:3],
                    categories=["rss"],
                    published=published,
                    link=entry.get("link", ""),
                    source="rss",
                )
            )
        return papers
