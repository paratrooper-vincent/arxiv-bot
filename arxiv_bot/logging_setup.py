"""日志体系：控制台 + 按大小轮转的文件日志（logs/arxiv.log，单文件 2MB × 保留 3 份）。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
_FORMAT = "%(asctime)s  %(levelname)-7s %(name)s  %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """初始化根 logger；重复调用安全（测试/仪表盘场景）。"""
    LOG_DIR.mkdir(exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return

    file_handler = RotatingFileHandler(
        LOG_DIR / "arxiv.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(_FORMAT)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
