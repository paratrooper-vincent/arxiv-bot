"""存储层测试：去重、推送状态、FTS5 检索、旧版迁移、失败计数。"""
from __future__ import annotations

import json

from arxiv_bot.filter import rank_papers
from arxiv_bot.models import PaperReview


def _scored(papers, cfg):
    return rank_papers(papers, cfg, engine=None)


def test_upsert_and_dedup(papers, cfg, storage):
    """已推送的论文再次出现时不会重复推送（去重核心逻辑）。"""
    scored = _scored(papers, cfg)
    storage.upsert_scored(scored)
    storage.mark_pushed([s.paper.paper_id for s in scored])

    assert storage.pushed_ids() == {s.paper.paper_id for s in scored}
    # 同一批论文再来（模拟第二次运行），候选应为空
    remaining = [p for p in papers if p.paper_id not in storage.pushed_ids()]
    assert remaining == [papers[2]]  # 只剩从未入选的股票论文


def test_mark_pushed_keeps_data(papers, cfg, storage):
    scored = _scored(papers, cfg)
    storage.upsert_scored(scored)
    storage.mark_pushed(["arxiv:2401.00001"])
    rows = {r["paper_id"]: r for r in storage.list_papers(limit=10)}
    assert rows["arxiv:2401.00001"]["status"] == "pushed"
    assert rows["arxiv:2401.00001"]["pushed_at"] != ""
    assert rows["arxiv:2401.00002"]["status"] == "new"


def test_fts_search(papers, cfg, storage):
    """FTS5 全文检索：标题/摘要里的词都能搜到。"""
    storage.upsert_scored(_scored(papers, cfg))
    hits = storage.search("gripper")
    assert len(hits) == 1 and "Gripper" in hits[0]["title"]
    hits = storage.search("tactile")  # 摘要中的词
    assert len(hits) == 1
    assert storage.search("不存在的词xyz") == []
    # 多词 OR：两篇都在库里的词各命中一篇
    assert len(storage.search("gripper flapping")) == 2


def test_fts_search_only_pushed(papers, cfg, storage):
    storage.upsert_scored(_scored(papers, cfg))
    storage.mark_pushed(["arxiv:2401.00001"])
    hits = storage.search("gripper stock", only_pushed=True)
    assert len(hits) == 1 and hits[0]["paper_id"] == "arxiv:2401.00001"


def test_stats(papers, cfg, storage):
    storage.upsert_scored(_scored(papers, cfg))
    storage.mark_pushed(["arxiv:2401.00001"])
    stats = storage.stats()
    assert stats["total"] == 2
    assert stats["pushed"] == 1
    assert stats["new"] == 1
    assert stats["by_source"]["arxiv"] == 2


def test_import_legacy_seen(tmp_path, storage):
    """旧版 seen.json 迁移：补 arxiv: 前缀、标记 pushed、幂等。"""
    seen = tmp_path / "seen.json"
    seen.write_text(
        json.dumps({"2610.31670v1": "2026-10-24", "2610.31661v1": "2026-10-24"}),
        encoding="utf-8",
    )
    assert storage.import_legacy_seen(seen) == 2
    assert storage.import_legacy_seen(seen) == 0  # 幂等
    assert "arxiv:2610.31670v1" in storage.pushed_ids()


def test_consecutive_failure_counter(storage):
    """失败计数与告警阈值判断。"""
    assert storage.consecutive_failures() == 0
    assert storage.record_failure() == 1
    assert storage.record_failure() == 2
    storage.record_success()
    assert storage.consecutive_failures() == 0


def test_run_history(storage):
    storage.log_run(ok=True, pushed=5)
    storage.log_run(ok=False, pushed=0)
    history = storage.run_history()
    (entry,) = history.values()
    assert entry == {"runs": 2, "ok": 1, "pushed": 5}


def test_upsert_does_not_demote_pushed(papers, cfg, storage):
    """重复 upsert 不会把已推送的行降回 new（防止推送状态被覆盖）。"""
    storage.upsert_scored(_scored(papers, cfg))
    storage.mark_pushed(["arxiv:2401.00001"])
    storage.upsert_scored(_scored(papers, cfg))  # 第二轮再写一遍
    rows = {r["paper_id"]: r for r in storage.list_papers(limit=10)}
    assert rows["arxiv:2401.00001"]["status"] == "pushed"


def test_review_fields_persisted(papers, cfg, storage):
    """LLM 点评字段正确入库。"""
    scored = _scored(papers, cfg)
    scored[0].review = PaperReview(
        relevant=True, comment="很相关", innovation="软体夹爪", category="软体机器人"
    )
    storage.upsert_scored(scored)
    row = {r["paper_id"]: r for r in storage.list_papers(limit=10)}["arxiv:2401.00001"]
    assert row["llm_relevant"] == 1
    assert row["llm_comment"] == "很相关"
