"""通用工具：带退避的网络重试。"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


def retry_call(action: Callable[[], T], name: str, times: int = 3, wait: int = 5) -> T:
    """执行 action，失败则退避重试（间隔递增），共 times 次；全部失败抛 RuntimeError。"""
    last: Optional[Exception] = None
    for i in range(1, times + 1):
        try:
            return action()
        except Exception as e:  # noqa: BLE001 —— 重试层需要捕获一切可恢复异常
            last = e
            logger.warning("[%s] 第 %d/%d 次失败：%s", name, i, times, e)
            if i < times:
                time.sleep(wait * i)
    raise RuntimeError(f"{name} 连续失败 {times} 次：{last}")
