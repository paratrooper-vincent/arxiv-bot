"""推送层：飞书 webhook —— 纯文本（告警/兼容）与 interactive 消息卡片（主推送）。

说明：群「自定义机器人」只能单向发消息。卡片按钮要做「回调交互」需要企业自建应用
（应用服务器接收 card.action 回调），本阶段只放一个跳转 arXiv 的 URL 按钮（无需服务端），
回调闭环的后续方案见 README 的 Roadmap。
"""
from __future__ import annotations

import logging
from typing import List, Sequence

import requests

from .models import ScoredPaper
from .utils import retry_call

logger = logging.getLogger(__name__)


def _post(webhook: str, payload: dict) -> None:
    """POST 到飞书 webhook；成功标准为返回 code==0，否则按失败进入重试。"""

    def do() -> None:
        resp = requests.post(webhook, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code", result.get("StatusCode", 0)) != 0:
            raise RuntimeError(f"飞书返回错误：{result}")

    retry_call(do, "推送飞书")


def send_text(webhook: str, text: str) -> None:
    _post(webhook, {"msg_type": "text", "content": {"text": text}})


def _title_md(s: ScoredPaper) -> str:
    title = s.paper.title.replace("[", "［").replace("]", "］")  # 防止破坏 lark_md 链接语法
    if s.paper.link:
        return f"**[{title}]({s.paper.link})**"
    return f"**{title}**"


def build_card(items: Sequence[ScoredPaper]) -> dict:
    """把推送列表组装成飞书 interactive 卡片（标题/作者/分类/摘要/点评/链接分区展示）。"""
    elements: List[dict] = []
    for i, s in enumerate(items, 1):
        authors = ", ".join(a for a in s.paper.authors[:3] if a) or "未知作者"
        cats = " / ".join(c for c in s.paper.categories[:3] if c) or "-"
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"{i}. {_title_md(s)}"},
                "fields": [
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**评分**\n{s.final_score:.2f}"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**来源**\n{s.paper.source}"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**作者**\n{authors}"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**分类**\n{cats}"},
                    },
                ],
            }
        )
        if s.review and s.review.comment:
            review_line = f"💬 点评：{s.review.comment}"
            if s.review.innovation:
                review_line += f"\n🧩 创新：{s.review.innovation}"
            if s.review.category:
                review_line += f"（{s.review.category}）"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": review_line}})
        abstract = s.paper.abstract[:180] + ("…" if len(s.paper.abstract) > 180 else "")
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": abstract or "（无摘要）"}}
        )
        elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "arXiv 最新列表"},
                    "type": "primary",
                    "url": "https://arxiv.org/list/cs.RO/recent",
                }
            ],
        }
    )
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {
                    "tag": "plain_text",
                    "content": f"📚 论文速递：{len(items)} 篇匹配你的方向",
                },
            },
            "elements": elements,
        },
    }


def build_weekly_card(count: int, summary_md: str, listing_md: str) -> dict:
    """每周汇总卡片：LLM 综述（或统计回退）+ 论文清单。"""
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": summary_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": listing_md[:8000]}},
    ]
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": f"📋 arxiv-bot 周报：近 7 天 {count} 篇"},
            },
            "elements": elements,
        },
    }


def preview_text(items: Sequence[ScoredPaper]) -> str:
    """预览模式的纯文本渲染（内容与卡片一一对应）。"""
    lines = [f"【预览】共 {len(items)} 篇将推送："]
    for i, s in enumerate(items, 1):
        lines.append(
            f"\n{i}. {s.paper.title}\n"
            f"   来源 {s.paper.source}｜评分 {s.final_score:.2f}｜命中 {s.matched_rule}"
        )
        if s.review and s.review.comment:
            lines.append(f"   点评：{s.review.comment}")
        lines.append(f"   链接：{s.paper.link}")
    return "\n".join(lines)


def push_papers(webhook: str, items: Sequence[ScoredPaper]) -> None:
    _post(webhook, build_card(items))


def send_alert(webhook: str, message: str) -> None:
    """连续失败告警；告警本身失败只记日志，绝不打断主流程。"""
    try:
        send_text(webhook, f"⚠️ arxiv-bot 告警\n{message}")
    except Exception as e:  # noqa: BLE001
        logger.error("告警推送失败：%s", e)
