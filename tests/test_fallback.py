"""回退逻辑测试：LLM / 语义层各种故障下主流程不崩、行为正确。"""
from __future__ import annotations

from unittest import mock

from arxiv_bot.config import Secrets
from arxiv_bot.filter import rank_papers
from arxiv_bot.llm import _extract_json, review_paper
from arxiv_bot.models import Paper, PaperReview
from arxiv_bot.pipeline import _select_final
from arxiv_bot.semantic import SemanticEngine

# ---------------- LLM 回退 ----------------

def test_review_paper_no_key_returns_none(papers, secrets):
    """未配置 LLM_API_KEY：直接返回 None，不发起任何网络请求。"""
    assert review_paper(papers[0], "机器人仿生学", secrets) is None


def test_extract_json_tolerates_fences():
    assert _extract_json('```json\n{"relevant": true}\n```') == {"relevant": True}
    assert _extract_json('好的，结果如下：{"relevant": false} 以上。') == {"relevant": False}


def test_review_paper_connection_error_returns_none(papers):
    """接口不可达：重试后返回 None 而不是抛异常（上层回退规则匹配）。"""
    fake = Secrets(
        llm_api_key="fake-key",
        llm_base_url="http://127.0.0.1:9",  # 不可达端口，快速失败
    )
    with mock.patch("arxiv_bot.utils.time.sleep"):  # 跳过重试等待，测试提速
        assert review_paper(papers[0], "机器人仿生学", fake) is None


def test_review_paper_parses_normal_response(papers):
    """正常响应：正确解析为 PaperReview。"""
    fake_response = mock.Mock()
    fake_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"relevant": true, "comment": "高度相关", '
                    '"innovation": "软体感知", "category": "软体机器人"}'
                }
            }
        ]
    }
    fake_response.raise_for_status = mock.Mock()
    with mock.patch("arxiv_bot.llm.requests.post", return_value=fake_response):
        review = review_paper(papers[0], "机器人仿生学", Secrets(llm_api_key="k"))
    assert review == PaperReview(
        relevant=True, comment="高度相关", innovation="软体感知", category="软体机器人"
    )


# ---------------- 语义回退 ----------------

def test_local_encoder_orders_by_relevance():
    """本地 numpy 编码：相关文档相似度必须高于无关文档。"""
    query = "soft robot gripper tactile sensing"
    docs = [
        "Soft robotic gripper with tactile sensor skin",
        "Stock price prediction using LSTM networks",
        "A soft robot hand for fruit picking",
    ]
    scores = SemanticEngine(Secrets(), backend="local").scores(query, docs)
    assert scores[0] > scores[1]
    assert scores[2] > scores[1]
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_local_encoder_empty_docs():
    assert SemanticEngine(Secrets(), backend="local").scores("q", []) == []


def test_engine_api_failure_falls_back_to_local():
    """接口后端失败：自动回退本地并给出合理分数。"""
    engine = SemanticEngine(
        Secrets(
            embedding_api_key="k",
            embedding_base_url="http://127.0.0.1:9",  # 不可达，触发回退
        ),
        backend="api",
    )
    with mock.patch("arxiv_bot.utils.time.sleep"):  # 跳过重试等待，测试提速
        scores = engine.scores("soft robot", ["soft robot gripper", "cooking recipes"])
    assert len(scores) == 2 and scores[0] > scores[1]


def test_rank_with_failing_engine_keeps_keyword_mode(papers, cfg):
    """语义引擎整体抛异常：rank_papers 退回纯关键词，不崩。"""

    class Boom:
        def scores(self, query, docs):
            raise RuntimeError("backend exploded")

    scored = rank_papers(papers, cfg, Boom())
    assert {s.paper.paper_id for s in scored} == {"arxiv:2401.00001", "arxiv:2401.00002"}


# ---------------- 最终取舍 ----------------

def test_select_final_drops_llm_irrelevant_semantic_only(cfg):
    """语义召回 + LLM 判不相关 + 关键词未命中 -> 淘汰。"""
    from arxiv_bot.models import ScoredPaper as SP

    cfg_ok = cfg.model_copy(update={"max_push": 10})
    sem_only = SP(
        paper=Paper(paper_id="arxiv:2401.00003", title="Stock", abstract="finance"),
        keyword_score=0.0,
        semantic_score=0.6,
        matched_rule="semantic:0.60",
        review=PaperReview(relevant=False, comment="跑题"),
    )
    assert _select_final([sem_only], cfg_ok) == []


def test_select_final_llm_relevant_boosted(cfg):
    from arxiv_bot.models import ScoredPaper as SP

    a = SP(
        paper=Paper(paper_id="a", title="robot a", abstract="robot", source="arxiv"),
        keyword_score=0.5,
    )
    b = SP(
        paper=Paper(paper_id="b", title="robot b", abstract="robot", source="arxiv"),
        keyword_score=0.5,
        review=PaperReview(relevant=True, comment="ok"),
    )
    result = _select_final([a, b], cfg)
    assert result[0].paper.paper_id == "b"  # LLM 相关者排前


def test_select_final_respects_max_push(cfg):
    """max_push（一次最多推几篇）在最终取舍环节生效。"""
    from arxiv_bot.models import ScoredPaper as SP

    many = [
        SP(
            paper=Paper(paper_id=f"arxiv:x{i:03d}", title=f"robot {i}", abstract="robot"),
            keyword_score=0.5,
            matched_rule="keyword:robot",
        )
        for i in range(10)
    ]
    cfg3 = cfg.model_copy(update={"max_push": 3})
    assert len(_select_final(many, cfg3)) == 3
