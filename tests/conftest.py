"""测试公共设施：样例论文、内存数据库、基础配置。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 让 tests 目录下的用例能直接 import arxiv_bot（无论从哪里启动 pytest）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arxiv_bot.config import AppConfig, Secrets  # noqa: E402
from arxiv_bot.models import Paper  # noqa: E402
from arxiv_bot.storage import Storage  # noqa: E402


@pytest.fixture()
def papers() -> list:
    """三篇样例论文：命中 robot、命中 bionic、全不命中。"""
    return [
        Paper(
            paper_id="arxiv:2401.00001",
            title="Soft Robot Gripper with Tactile Sensing",
            abstract="A soft robot gripper for delicate manipulation.",
            authors=["Alice", "Bob"],
            categories=["cs.RO"],
            published="2026-10-20",
            link="https://arxiv.org/abs/2401.00001",
        ),
        Paper(
            paper_id="arxiv:2401.00002",
            title="Biomimetic Flapping Wing Design",
            abstract="Inspired by insect flight, a bionic wing mechanism.",
            authors=["Carol"],
            categories=["cs.RO"],
            published="2026-10-21",
            link="https://arxiv.org/abs/2401.00002",
        ),
        Paper(
            paper_id="arxiv:2401.00003",
            title="Stock Market Prediction with Deep Learning",
            abstract="LSTM based financial forecasting.",
            authors=["Dave"],
            categories=["q-fin.ST"],
            published="2026-10-22",
            link="https://arxiv.org/abs/2401.00003",
        ),
    ]


@pytest.fixture()
def storage(tmp_path) -> Storage:
    return Storage(tmp_path / "test.db")


@pytest.fixture()
def cfg() -> AppConfig:
    return AppConfig(
        keywords=["robot", "bionic", "biomimetic", "soft robot"],
        categories=["cs.RO"],
        max_push=2,
    )


@pytest.fixture()
def secrets() -> Secrets:
    """没有任何 key 的密钥配置——用于验证回退路径。"""
    return Secrets(feishu_webhook="", llm_api_key="", embedding_api_key="")
