"""多数据源测试：离线 fixture 解析 + 跨源去重（不打真实网络）。"""
from __future__ import annotations

from unittest import mock

from arxiv_bot.config import AppConfig
from arxiv_bot.models import Paper
from arxiv_bot.sources import (
    SemanticScholarSource,
    build_sources,
    dedupe_cross_source,
)
from arxiv_bot.sources.github_trending import GitHubTrendingSource

_S2_PAYLOAD = {
    "data": [
        {
            "paperId": "abc123",
            "title": "Bionic Soft Actuator",
            "abstract": "A bionic soft actuator study.",
            "authors": [{"name": "Eve"}],
            "year": 2026,
            "publicationDate": "2026-10-20",
            "externalIds": {"ArXiv": "2610.99999"},
            "url": "https://www.semanticscholar.org/paper/abc123",
        },
        {
            "paperId": "def456",
            "title": "Non-ArXiv Paper",
            "abstract": "Only on S2.",
            "authors": [],
            "year": 2026,
            "publicationDate": None,
            "externalIds": {},
            "url": "https://www.semanticscholar.org/paper/def456",
        },
        {"paperId": "ghi789", "title": None, "abstract": "broken"},  # 脏数据应被跳过
    ]
}

_GH_PAYLOAD = {
    "items": [
        {
            "full_name": "someone/awesome-robot-lib",
            "description": "Robot learning library",
            "stargazers_count": 42,
            "created_at": "2026-10-22T00:00:00Z",
            "html_url": "https://github.com/someone/awesome-robot-lib",
            "owner": {"login": "someone"},
            "topics": ["robotics", "ml"],
        }
    ]
}


def test_s2_parse_arxiv_bridge():
    """S2 带 arXiv 外链的论文：paper_id 用 arxiv: 前缀（与主源天然合并）。"""
    source = SemanticScholarSource()
    papers = source._parse(_S2_PAYLOAD)
    assert len(papers) == 2  # 脏数据被跳过
    assert papers[0].paper_id == "arxiv:2610.99999"
    assert papers[0].link == "https://arxiv.org/abs/2610.99999"
    assert papers[1].paper_id == "s2:def456"


def test_s2_fetch_retries_then_ok():
    """接口第一次 429、第二次成功：重试机制生效。"""
    bad = mock.Mock()
    bad.raise_for_status.side_effect = RuntimeError("429 Too Many Requests")
    good = mock.Mock()
    good.raise_for_status = mock.Mock()
    good.json.return_value = _S2_PAYLOAD
    with mock.patch("arxiv_bot.sources.semantic_scholar.requests.get", side_effect=[bad, good]):
        with mock.patch("arxiv_bot.utils.time.sleep"):
            papers = SemanticScholarSource().fetch(
                AppConfig(keywords=["robot"], categories=["cs.RO"])
            )
    assert len(papers) == 2


def test_github_trending_parse():
    papers = GitHubTrendingSource()._parse(_GH_PAYLOAD)
    assert len(papers) == 1
    p = papers[0]
    assert p.paper_id == "gh:someone/awesome-robot-lib"
    assert p.source == "github"
    assert "★42" in p.title


def test_dedupe_cross_source_same_arxiv_id():
    """arXiv 主源与 S2 的同一篇（同 arXiv id）合并为一条。"""
    a = Paper(paper_id="arxiv:2610.99999", title="Bionic Soft Actuator", source="arxiv")
    b = Paper(
        paper_id="arxiv:2610.99999",
        title="Bionic Soft Actuator (duplicate from s2)",
        source="s2",
    )
    result = dedupe_cross_source([b, a])
    assert len(result) == 1
    assert result[0].source == "arxiv"  # 优先保留高优先级源


def test_dedupe_cross_source_same_title():
    """不同 id 但标题相同的论文按指纹合并。"""
    a = Paper(paper_id="arxiv:111", title="A Great Robot Paper: Study!", source="arxiv")
    b = Paper(paper_id="s2:222", title="a great robot paper  study", source="s2")
    assert len(dedupe_cross_source([a, b])) == 1


def test_build_sources_respects_switches():
    cfg = AppConfig(keywords=["robot"], categories=["cs.RO"])
    names = [s.name for s in build_sources(cfg)]
    assert names == ["arxiv"]  # 其他源默认关闭
    # 注意走构造函数（会校验），model_copy(update=) 不重新校验 dict
    cfg2 = AppConfig(
        keywords=["robot"],
        categories=["cs.RO"],
        sources={
            "arxiv": {"enabled": True},
            "semantic_scholar": {"enabled": True, "limit": 10},
            "github_trending": {"enabled": True, "topic": "robotics", "limit": 5},
            "rss": {"enabled": True, "urls": ["https://example.com/rss"]},
            "papers_with_code": {"enabled": False, "limit": 10},
        },
    )
    names2 = [s.name for s in build_sources(cfg2)]
    assert names2 == ["arxiv", "semantic_scholar", "github_trending", "rss"]
