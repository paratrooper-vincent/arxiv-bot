"""筛选打分：关键词规则 + 语义相似度组合排序。

- 语义可用：final = 0.35*关键词 + 0.65*语义；语义达标的论文即使没命中关键词也保留；
- 语义不可用/关闭/异常：自动退回旧版行为——只保留命中关键词的论文，按命中数排序。
"""
from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from .config import AppConfig
from .models import Paper, ScoredPaper
from .semantic import SemanticEngine

logger = logging.getLogger(__name__)


def keyword_score(text: str, keywords: Sequence[str]) -> float:
    """关键词命中得分 0~1：命中越多越高（1 个 0.5、2 个 0.67…），平滑避免多命中溢出。"""
    low = text.lower()
    hits = sum(1 for k in keywords if k.lower() in low)
    return hits / (hits + 1) if hits else 0.0


def hit_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    low = text.lower()
    return [k for k in keywords if k.lower() in low]


def rank_papers(
    papers: Sequence[Paper], cfg: AppConfig, engine: Optional[SemanticEngine]
) -> List[ScoredPaper]:
    """候选论文打分排序（详见模块 docstring 的回退策略）。"""
    sem_scores: Optional[List[float]] = None
    if cfg.semantic.enabled and engine is not None and papers:
        try:
            sem_scores = engine.scores(cfg.research_focus, [p.text for p in papers])
        except Exception as e:  # noqa: BLE001 —— 语义层任何异常都不允许影响主流程
            logger.warning("语义匹配失败，本次退回纯关键词方案：%s", e)
            sem_scores = None

    scored: List[ScoredPaper] = []
    for i, p in enumerate(papers):
        hits = hit_keywords(p.text, cfg.keywords)
        kw = len(hits) / (len(hits) + 1) if hits else 0.0
        sem = sem_scores[i] if sem_scores else None

        if sem is None:
            if not hits:
                continue  # 纯关键词模式：没命中就丢弃（与 v1 行为一致）
            rule = "keyword:" + ",".join(hits[:3])
        else:
            if not hits and sem < cfg.semantic.min_score:
                continue  # 两路都没到门槛，丢弃
            rule = f"keyword:{','.join(hits[:3])}" if hits else f"semantic:{sem:.2f}"
        scored.append(
            ScoredPaper(paper=p, keyword_score=kw, semantic_score=sem, matched_rule=rule)
        )

    scored.sort(key=lambda s: s.final_score, reverse=True)
    logger.info(
        "筛选完成：候选 %d 篇 -> 保留 %d 篇（语义%s）",
        len(papers), len(scored), "启用" if sem_scores else "未启用",
    )
    return scored
