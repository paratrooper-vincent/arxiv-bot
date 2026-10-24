"""LLM 二次理解：OpenAI 兼容 chat/completions 接口。

职责：
- 单篇论文结构化点评（是否相关 / 中文一句话点评 / 核心创新 / 方法类别）
- 每周综述生成

兜底原则：没配 key、接口失败、输出不是合法 JSON，一律返回 None，
由上层自动回退规则匹配，绝不让 LLM 故障打断推送主流程。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import List, Optional

import requests

from .config import Secrets
from .models import Paper, PaperReview
from .utils import retry_call

logger = logging.getLogger(__name__)

_REVIEW_SYSTEM = (
    "你是科研论文筛选助手。根据用户的研究方向判断论文相关性，"
    "并只输出一个 JSON 对象，不要输出任何其他文字。"
    'JSON 格式：{"relevant": true/false, "comment": "中文一句话点评", '
    '"innovation": "核心创新点（中文一句话）", "category": "方法类别（中文短语）"}'
)


def _extract_json(text: str) -> dict:
    """从模型输出中稳健地提取 JSON（容忍 ```json 代码块包裹与前后废话）。"""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"输出中找不到 JSON：{text[:120]}")
    return json.loads(match.group(0))


def _chat(secrets: Secrets, system: str, user: str, max_tokens: int = 600) -> str:
    def do() -> str:
        resp = requests.post(
            f"{secrets.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {secrets.llm_api_key}"},
            json={
                "model": secrets.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    content = retry_call(do, "LLM调用", times=2, wait=3)
    time.sleep(0.5)  # 轻限速，避免触发免费档频控
    return content


def review_paper(
    paper: Paper, research_focus: str, secrets: Secrets
) -> Optional[PaperReview]:
    """LLM 点评单篇论文；任何失败返回 None（上层回退规则匹配）。"""
    if not secrets.llm_api_key:
        return None
    user_prompt = (
        f"研究方向：{research_focus}\n标题：{paper.title}\n摘要：{paper.abstract[:1200]}"
    )
    try:
        data = _extract_json(_chat(secrets, _REVIEW_SYSTEM, user_prompt))
        return PaperReview(
            relevant=bool(data.get("relevant")),
            comment=str(data.get("comment", ""))[:200],
            innovation=str(data.get("innovation", ""))[:200],
            category=str(data.get("category", ""))[:50],
        )
    except Exception as e:  # noqa: BLE001 —— LLM 层失败必须无感回退
        logger.warning("LLM 点评失败（%s），该篇回退规则匹配：%s", paper.paper_id, e)
        return None


_WEEKLY_SYSTEM = (
    "你是科研情报助手。根据用户提供的近 7 天论文清单，用中文输出 Markdown 周报综述，"
    "结构：## 本周趋势（2-3 句）## 值得细读（挑 3-5 篇，各一句话理由）## 方向提醒（1-2 句）。"
    "不要编造清单之外的论文。"
)


def weekly_summary(
    titles: List[str], research_focus: str, secrets: Secrets
) -> Optional[str]:
    """LLM 生成周报综述；没 key 或失败返回 None（上层回退统计式周报）。"""
    if not secrets.llm_api_key:
        return None
    listing = "\n".join(f"- {t}" for t in titles[:60])
    try:
        return _chat(
            secrets,
            _WEEKLY_SYSTEM,
            f"研究方向：{research_focus}\n近 7 天推送论文清单：\n{listing}",
            max_tokens=1500,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("周报生成失败，回退统计式周报：%s", e)
        return None
