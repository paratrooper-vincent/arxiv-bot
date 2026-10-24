"""多数据源聚合：每个源实现 Source 接口，build_sources() 按 config 开关装配。

新增一个数据源只需三步：写一个 fetch() 返回 List[Paper] 的类、
在 SourcesConfig 加开关、加进 build_sources()，主流程零改动。
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List

from ..config import AppConfig
from ..models import Paper
from .arxiv_source import ArxivSource
from .base import Source
from .github_trending import GitHubTrendingSource
from .papers_with_code import PapersWithCodeSource
from .rss_source import RSSSource
from .semantic_scholar import SemanticScholarSource

logger = logging.getLogger(__name__)

__all__ = [
    "Source",
    "ArxivSource",
    "SemanticScholarSource",
    "GitHubTrendingSource",
    "RSSSource",
    "PapersWithCodeSource",
    "build_sources",
    "collect_papers",
    "dedupe_cross_source",
]


def build_sources(cfg: AppConfig) -> List[Source]:
    """按 config.json 的 sources.*.enabled 开关装配启用的数据源。"""
    s = cfg.sources
    sources: List[Source] = []
    if s.arxiv.enabled:
        sources.append(ArxivSource())
    if s.semantic_scholar.enabled:
        sources.append(SemanticScholarSource(s.semantic_scholar.limit))
    if s.github_trending.enabled:
        sources.append(GitHubTrendingSource(s.github_trending.topic, s.github_trending.limit))
    if s.rss.enabled and s.rss.urls:
        sources.append(RSSSource(s.rss.urls))
    if s.papers_with_code.enabled:
        sources.append(PapersWithCodeSource(s.papers_with_code.limit))
    return sources


# 跨源去重时的优先级：同一篇论文优先保留信息更全的源
_SOURCE_PRIORITY = {"arxiv": 0, "s2": 1, "github": 2, "rss": 3, "pwc": 4}


def title_fingerprint(title: str) -> str:
    """标题指纹：小写、去非字母数字、压空格——用于不同源同一论文的对齐。"""
    return re.sub(r"\s+", "", re.sub(r"[^0-9a-z]+", " ", title.lower())).strip()[:80]


def dedupe_cross_source(papers: List[Paper]) -> List[Paper]:
    """跨源去重：先按 paper_id（arXiv 同 id 直接合并），再按标题指纹。"""
    by_id: Dict[str, Paper] = {}
    for p in sorted(papers, key=lambda x: _SOURCE_PRIORITY.get(x.source, 9)):
        by_id.setdefault(p.paper_id, p)
    by_fp: Dict[str, Paper] = {}
    for p in by_id.values():
        by_fp.setdefault(title_fingerprint(p.title), p)
    if len(by_fp) < len(papers):
        logger.info("跨源去重：%d -> %d 篇", len(papers), len(by_fp))
    return list(by_fp.values())


def collect_papers(cfg: AppConfig) -> List[Paper]:
    """聚合所有启用数据源；单源失败只记日志，不影响其他源。"""
    papers: List[Paper] = []
    for source in build_sources(cfg):
        try:
            batch = source.fetch(cfg)
            logger.info("数据源 %s：%d 条", source.name, len(batch))
            papers.extend(batch)
        except Exception as e:  # noqa: BLE001 —— 单源故障不允许拖垮整体
            logger.error("数据源 %s 失败，跳过：%s", source.name, e)
    return dedupe_cross_source(papers)
