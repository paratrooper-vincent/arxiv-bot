"""arXiv 数据源：官方 Atom 接口（主源）。"""
from __future__ import annotations

from typing import List

from ..config import AppConfig
from ..fetcher import fetch_arxiv
from ..models import Paper
from .base import Source


class ArxivSource(Source):
    name = "arxiv"

    def fetch(self, cfg: AppConfig) -> List[Paper]:
        return fetch_arxiv(cfg)
