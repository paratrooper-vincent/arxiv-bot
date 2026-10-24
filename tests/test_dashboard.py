"""仪表盘 API 测试：注入临时数据库，用 TestClient 离线验证。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from arxiv_bot.dashboard import create_app
from arxiv_bot.filter import rank_papers
from arxiv_bot.pipeline import _select_final


def _fill(storage, papers, cfg):
    scored = _select_final(rank_papers(papers, cfg, engine=None), cfg)
    storage.upsert_scored(scored)
    storage.mark_pushed([s.paper.paper_id for s in scored])
    storage.log_run(ok=True, pushed=len(scored))


def test_dashboard_api(papers, cfg, storage):
    _fill(storage, papers, cfg)
    client = TestClient(create_app(storage))

    resp = client.get("/api/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2 and data["pushed"] == 2
    assert data["success_rate"] == 1.0
    assert data["by_source"]["arxiv"] == 2

    resp = client.get("/api/papers", params={"status": "pushed"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("Gripper" in i["title"] for i in items)

    resp = client.get("/api/papers", params={"q": "flapping"})
    assert len(resp.json()["items"]) == 1

    resp = client.get("/api/trends")
    assert resp.status_code == 200 and resp.json()["by_rule"]


def test_dashboard_index_html_served(papers, cfg, storage):
    _fill(storage, papers, cfg)
    client = TestClient(create_app(storage))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "arxiv-bot" in resp.text
    # 本地 ECharts 资源可访问（不依赖外网 CDN）
    assert client.get("/static/echarts.min.js").status_code == 200
