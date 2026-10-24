"""主流程编排：抓取 -> 去重 -> 打分（关键词+语义）-> LLM 精选 -> 落库 -> 推送。

健壮性约定：
- 预览模式（--preview 或未配置 webhook）：只打印不推送、不标记 pushed、跳过 LLM（省额度）；
- LLM / 语义层失败自动回退，不影响主流程；
- 整体运行异常计入连续失败，达到阈值向飞书发告警；成功一次即清零。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from . import notifier
from .config import DATA_DIR, PROJECT_ROOT, AppConfig, Secrets, load_config, load_secrets
from .fetcher import fetch_arxiv
from .filter import rank_papers
from .llm import review_paper
from .models import ScoredPaper
from .semantic import SemanticEngine
from .storage import Storage

logger = logging.getLogger(__name__)


def open_storage() -> Storage:
    """打开默认位置的数据库（data/arxiv.db）。"""
    return Storage(DATA_DIR / "arxiv.db")


def _select_final(scored: List[ScoredPaper], cfg: AppConfig) -> List[ScoredPaper]:
    """结合 LLM 结论做最终取舍与排序。

    - LLM 判「不相关」且关键词也没命中 -> 淘汰（语义召回但确实跑题）；
    - LLM 判「相关」-> 排序加权 +0.2（人工确认过的高度相关优先推）；
    - 其余按组合分排序，截取 max_push。
    """
    kept = [
        s
        for s in scored
        if not (s.review is not None and s.review.relevant is False and s.keyword_score == 0.0)
    ]
    kept.sort(
        key=lambda s: s.final_score + (0.2 if (s.review and s.review.relevant) else 0.0),
        reverse=True,
    )
    return kept[: cfg.max_push]


def run_daily(
    preview: bool = False,
    cfg: Optional[AppConfig] = None,
    secrets: Optional[Secrets] = None,
    storage: Optional[Storage] = None,
) -> dict:
    """每日主任务。返回运行摘要（mode/count），供测试与日志使用。"""
    cfg = cfg or load_config()
    secrets = secrets or load_secrets()
    preview = preview or not secrets.feishu_webhook
    storage = storage or open_storage()
    storage.import_legacy_seen(PROJECT_ROOT / "seen.json")

    # ---- 1. 抓取（P1 起此处聚合多数据源，单源失败只记日志不中断） ----
    papers = []
    try:
        papers.extend(fetch_arxiv(cfg))
    except Exception as e:  # noqa: BLE001
        logger.error("arXiv 抓取失败：%s", e)
    if not papers:
        raise RuntimeError("没有抓到任何论文（所有数据源失败）")

    # ---- 2. 去重：只保留从未推送过的 ----
    pushed = storage.pushed_ids()
    candidates = [p for p in papers if p.paper_id not in pushed]
    logger.info("抓取 %d 篇，其中 %d 篇未推送过", len(papers), len(candidates))
    if not candidates:
        logger.info("没有新论文，本次收工")
        return {"mode": "preview" if preview else "push", "count": 0}

    # ---- 3. 打分（关键词 + 语义，语义异常自动回退） ----
    engine = SemanticEngine(secrets, cfg.semantic.backend)
    scored = rank_papers(candidates, cfg, engine)

    # ---- 4. LLM 精选（预览模式与未配 key 时自动跳过） ----
    if not preview and cfg.llm.enabled and secrets.llm_api_key:
        for s in scored[: cfg.llm.top_k]:
            s.review = review_paper(s.paper, cfg.research_focus, secrets)

    chosen = _select_final(scored, cfg)
    if not chosen:
        logger.info("筛选后没有可推送的论文，本次收工")
        return {"mode": "preview" if preview else "push", "count": 0}

    # ---- 5. 落库（status=new，推送成功后再标 pushed，失败可自动重试） ----
    storage.upsert_scored(chosen)

    # ---- 6. 推送 ----
    if preview:
        logger.info("预览模式，不推送：\n%s", notifier.preview_text(chosen))
        return {"mode": "preview", "count": len(chosen)}

    notifier.push_papers(secrets.feishu_webhook, chosen)
    storage.mark_pushed(s.paper.paper_id for s in chosen)
    logger.info("已推送 %d 篇（interactive 卡片）并标记 pushed", len(chosen))
    return {"mode": "push", "count": len(chosen)}


def run_guarded(preview: bool = False) -> dict:
    """带失败计数与告警的运行入口（CLI / 定时任务 / Actions 都走这里）。"""
    cfg = load_config()
    secrets = load_secrets()
    storage = open_storage()
    try:
        result = run_daily(preview, cfg, secrets, storage)
        storage.record_success()
        storage.log_run(ok=True, pushed=result.get("count", 0))
        return result
    except Exception as e:  # noqa: BLE001 —— 守门层负责善后，再抛出交 CLI 决定退出码
        logger.exception("本次运行失败")
        failures = storage.record_failure()
        storage.log_run(ok=False, pushed=0)
        if failures >= cfg.alert.consecutive_failures and secrets.feishu_webhook:
            notifier.send_alert(secrets.feishu_webhook, f"已连续失败 {failures} 次，最近错误：{e}")
        raise
