"""Papers with Code 数据源。

注意：PwC 已并入 Hugging Face / GitHub 归档，官方 API 处于不稳定状态。
本模块按原 v1 接口实现并默认关闭：若接口恢复即可用；
失败时只记 warning 返回空列表，不影响其他数据源（见 Roadmap：计划换 HF Datasets 源）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

from ..config import AppConfig
from ..models import Paper
from .base import Source

logger = logging.getLogger(__name__)
_API = "https://paperswithcode.com/api/v1/papers/"


class PapersWithCodeSource(Source):
    name = "papers_with_code"

    def __init__(self, limit: int = 20):
        self._limit = limit

    def fetch(self, cfg: AppConfig) -> List[Paper]:
        try:
            resp = requests.get(
                _API, params={"page": 1, "items_per_page": self._limit}, timeout=20
            )
            resp.raise_for_status()
            return self._parse(resp.json())
        except Exception as e:  # noqa: BLE001 —— 该源允许彻底失败
            logger.warning("Papers with Code 接口不可用（预期内），跳过：%s", e)
            return []

    def _parse(self, data: Dict[str, Any]) -> List[Paper]:
        papers = []
        for item in data.get("results", []):
            arxiv_id = item.get("arxiv_id")
            paper_id = f"arxiv:{arxiv_id}" if arxiv_id else f"pwc:{item.get('id', '')}"
            papers.append(
                Paper(
                    paper_id=paper_id,
                    title=(item.get("title") or "").strip(),
                    abstract=(item.get("abstract") or "").strip()[:600],
                    authors=[],
                    categories=["papers-with-code"],
                    published=(item.get("published") or "")[:10],
                    link=item.get("url", ""),
                    source="pwc",
                )
            )
        return [p for p in papers if p.title]
