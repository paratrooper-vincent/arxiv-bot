"""筛选打分测试：关键词命中、排序、语义回退。"""
from __future__ import annotations

from arxiv_bot.filter import hit_keywords, keyword_score, rank_papers


def test_keyword_score_basic():
    text = "A soft robot gripper for robot manipulation"
    assert keyword_score(text, ["robot"]) > 0.0
    assert keyword_score("nothing here", ["robot"]) == 0.0
    # 命中两个关键词的得分应高于只命中一个
    assert keyword_score("robot bionic", ["robot", "bionic"]) > keyword_score(
        "robot only", ["robot", "bionic"]
    )


def test_hit_keywords_case_insensitive():
    assert hit_keywords("SOFT ROBOT arm", ["soft robot"]) == ["soft robot"]


def test_rank_keyword_only_mode(papers, cfg):
    """无语义引擎（= 回退场景）：只保留命中关键词的，按分排序。"""
    scored = rank_papers(papers, cfg, engine=None)
    ids = [s.paper.paper_id for s in scored]
    assert "arxiv:2401.00003" not in ids  # 不相关论文被过滤
    assert set(ids) == {"arxiv:2401.00001", "arxiv:2401.00002"}
    assert all(s.semantic_score is None for s in scored)
    # max_push=2 全保留
    assert len(scored) == 2


def test_rank_keyword_mode_returns_all_matched(cfg):
    """rank 只负责排序不去截断（max_push 在 _select_final 生效）。"""
    from arxiv_bot.models import Paper

    many = [
        Paper(paper_id=f"arxiv:x{i:03d}", title=f"robot paper {i}", abstract="robot")
        for i in range(10)
    ]
    scored = rank_papers(many, cfg, engine=None)
    assert len(scored) == 10


class FakeEngine:
    """固定分数的假语义引擎：只给「软体夹爪」高分。"""

    def __init__(self, scores):
        self._scores = scores

    def scores(self, query, docs):
        return self._scores


def test_rank_semantic_mode_semantic_only_survives(papers, cfg):
    """语义启用时：没命中关键词但语义达标的论文保留（v2 新能力）。"""
    engine = FakeEngine([0.9, 0.1, 0.5])  # 夹爪 0.9 / 仿生翼 0.1 / 股票预测 0.5
    scored = rank_papers(papers, cfg, engine)
    ids = {s.paper.paper_id for s in scored}
    assert "arxiv:2401.00003" in ids  # 语义 0.5 >= min_score 0.35，未命中关键词也入选
    assert "arxiv:2401.00002" in ids  # 命中关键词的论文无论语义分多少都保留（显式兴趣优先）
    # 排序：夹爪（关键词+高语义）应排第一
    assert scored[0].paper.paper_id == "arxiv:2401.00001"


def test_rank_semantic_below_threshold_dropped(papers, cfg):
    """语义未达门槛且关键词没命中 -> 丢弃。"""
    engine = FakeEngine([0.9, 0.4, 0.1])  # 股票论文语义仅 0.1
    scored = rank_papers(papers, cfg, engine)
    ids = {s.paper.paper_id for s in scored}
    assert "arxiv:2401.00003" not in ids
