"""统一数据模型：各数据源抓到的条目一律转成 Paper，后续环节只认 Paper。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Paper(BaseModel):
    """一条论文/情报条目（arXiv、Semantic Scholar、GitHub Trending、RSS 共用）。"""

    paper_id: str  # 全局唯一键：arxiv:xxx / s2:xxx / gh:xxx / rss:hash
    title: str
    abstract: str = ""
    authors: List[str] = []
    categories: List[str] = []
    published: str = ""  # 日期字符串（YYYY-MM-DD）
    link: str = ""
    source: str = "arxiv"  # 来源标签，用于卡片展示与统计

    @property
    def text(self) -> str:
        """用于关键词匹配 / 向量化的文本：标题 + 摘要。"""
        return f"{self.title} {self.abstract}".strip()


class PaperReview(BaseModel):
    """LLM 对单篇论文的结构化理解结果。"""

    relevant: Optional[bool] = None  # 是否与研究方向相关
    comment: str = ""  # 中文一句话点评
    innovation: str = ""  # 核心创新点
    category: str = ""  # 方法类别（如：软体机器人 / VLA / 控制）


class ScoredPaper(BaseModel):
    """打分后的候选论文：原始 Paper + 各环节得分 + LLM 结论。"""

    paper: Paper
    keyword_score: float = 0.0  # 关键词命中得分 0~1
    semantic_score: Optional[float] = None  # 语义相似度 0~1；语义不可用时为 None
    matched_rule: str = ""  # 命中说明：keyword:xxx / semantic:0.82
    review: Optional[PaperReview] = None

    @property
    def final_score(self) -> float:
        """组合分：语义可用时 0.35*关键词 + 0.65*语义，否则退回关键词分。"""
        if self.semantic_score is None:
            return self.keyword_score
        return round(0.35 * self.keyword_score + 0.65 * self.semantic_score, 4)
