"""数据源接口定义（单独成文件，避免与 sources/__init__ 循环导入）。"""
from __future__ import annotations

from typing import List

from ..config import AppConfig
from ..models import Paper


class Source:
    """数据源接口：name 用于日志，fetch() 返回统一 Paper 列表。"""

    name: str = "base"

    def fetch(self, cfg: AppConfig) -> List[Paper]:  # pragma: no cover - 接口定义
        raise NotImplementedError
