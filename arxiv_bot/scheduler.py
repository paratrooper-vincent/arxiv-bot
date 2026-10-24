"""调度入口：被 CLI / run_bot.bat / Windows 任务计划程序 / GitHub Actions 调用。

定时触发本身由外部调度器承担（本地=任务计划程序每天 08:00；云端=Actions cron），
本模块只提供「这一轮该干什么」：daily() 每日抓推，weekly() 每周汇总。
"""
from __future__ import annotations

import logging

from . import notifier
from .config import load_config, load_secrets
from .llm import weekly_summary
from .pipeline import open_storage

logger = logging.getLogger(__name__)


def daily(preview: bool = False) -> dict:
    """每日任务：抓取 -> 筛选 -> 推送（详见 pipeline.run_guarded）。"""
    from .pipeline import run_guarded  # 延迟导入，避免与 dashboard 的循环依赖

    return run_guarded(preview)


def weekly(preview: bool = False) -> dict:
    """每周任务：汇总近 7 天已推送论文，LLM 生成综述（无 key 回退统计清单）并推送。"""
    cfg = load_config()
    secrets = load_secrets()
    preview = preview or not secrets.feishu_webhook
    storage = open_storage()

    rows = storage.recent_pushed(days=7)
    if not rows:
        logger.info("近 7 天没有已推送论文，周报跳过")
        return {"mode": "weekly", "count": 0}

    titles = [r["title"] for r in rows]
    summary = weekly_summary(titles, cfg.research_focus, secrets)
    if summary is None:
        by_source = {}
        for r in rows:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        src_text = "、".join(f"{k} {v} 篇" for k, v in by_source.items())
        summary = (
            f"**本周综述（统计回退版，配置 LLM_API_KEY 可获得 AI 综述）**\n\n"
            f"近 7 天共推送 **{len(rows)}** 篇（{src_text}），"
            f"研究方向：{cfg.research_focus}。"
        )
    listing = "\n".join(f"- [{r['title']}]({r['link']})（{r['source']}）" for r in rows)
    card = notifier.build_weekly_card(len(rows), summary, listing)

    if preview:
        logger.info("周报预览模式，不推送。综述：\n%s\n清单：%d 篇", summary, len(rows))
        return {"mode": "weekly-preview", "count": len(rows)}
    notifier._post(secrets.feishu_webhook, card)
    logger.info("周报已推送（%d 篇汇总）", len(rows))
    return {"mode": "weekly", "count": len(rows)}
