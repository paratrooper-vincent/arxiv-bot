"""配置模块：环境变量（.env，含密钥）与业务配置（config.json）统一管理。

约定：
- 一切密钥（webhook / API key）只放 .env，绝不写进代码或 config.json；
- config.json 只放可公开的业务参数（关键词、条数、开关）；
- 配置缺失或非法时启动即抛 ConfigError，绝不带病运行。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录 = 本文件上两级（arxiv_bot/config.py -> arxiv_bot/ -> 项目根）
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"


class ConfigError(Exception):
    """配置错误：文件缺失、JSON 非法或字段不合法。"""


class Secrets(BaseSettings):
    """从项目根 .env 读取的环境变量；未配置的密钥为空字符串（触发对应回退）。"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    feishu_webhook: str = ""  # 飞书自定义机器人 webhook；为空 => 预览模式
    llm_api_key: str = ""  # OpenAI 兼容 LLM key；为空 => 回退关键词方案
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    llm_model: str = "glm-4-flash"
    embedding_api_key: str = ""  # 向量接口 key；为空 => 回退本地 numpy 匹配
    embedding_base_url: str = ""
    embedding_model: str = ""


class SemanticConfig(BaseModel):
    enabled: bool = True
    backend: str = "auto"  # auto：配了 key 用接口，否则本地 numpy
    top_k: int = Field(15, gt=0)
    min_score: float = Field(0.35, ge=0.0, le=1.0)


class LLMConfig(BaseModel):
    enabled: bool = True
    top_k: int = Field(8, gt=0)


class AlertConfig(BaseModel):
    consecutive_failures: int = Field(3, ge=1)


class ArxivSourceConfig(BaseModel):
    enabled: bool = True


class SemanticScholarSourceConfig(BaseModel):
    enabled: bool = False
    limit: int = Field(20, gt=0, le=100)


class GitHubTrendingSourceConfig(BaseModel):
    enabled: bool = False
    topic: str = "robotics"
    limit: int = Field(10, gt=0, le=30)


class RSSSourceConfig(BaseModel):
    enabled: bool = False
    urls: List[str] = []


class PapersWithCodeSourceConfig(BaseModel):
    """PwC 官方 API 已不稳定，默认关闭（详见 sources/papers_with_code.py 说明）。"""

    enabled: bool = False
    limit: int = Field(20, gt=0, le=50)


class SourcesConfig(BaseModel):
    arxiv: ArxivSourceConfig = ArxivSourceConfig()
    semantic_scholar: SemanticScholarSourceConfig = SemanticScholarSourceConfig()
    github_trending: GitHubTrendingSourceConfig = GitHubTrendingSourceConfig()
    rss: RSSSourceConfig = RSSSourceConfig()
    papers_with_code: PapersWithCodeSourceConfig = PapersWithCodeSourceConfig()


class AppConfig(BaseModel):
    """config.json 的全量业务配置模型（未写的节自动取默认值，兼容旧配置）。"""

    research_focus: str = "机器人仿生学：仿生机构、软体机器人、生物启发感知与驱动"
    categories: List[str] = ["cs.RO"]
    keywords: List[str] = Field(default_factory=lambda: ["robot", "robotic"])
    fetch_count: int = Field(100, gt=0, le=300)  # arXiv 官方建议单次不超过 300
    max_push: int = Field(10, gt=0, le=20)
    semantic: SemanticConfig = SemanticConfig()
    llm: LLMConfig = LLMConfig()
    alert: AlertConfig = AlertConfig()
    sources: SourcesConfig = SourcesConfig()

    @field_validator("categories", "keywords")
    @classmethod
    def _not_blank(cls, v: List[str]) -> List[str]:
        cleaned = [x.strip() for x in v if x.strip()]
        if not cleaned:
            raise ValueError("不能为空列表")
        return cleaned


def load_config(path: Optional[Path] = None) -> AppConfig:
    """读取并校验 config.json；任何问题都以中文 ConfigError 终止启动。"""
    path = path or (PROJECT_ROOT / "config.json")
    if not path.exists():
        raise ConfigError(f"找不到配置文件 {path}，请先复制 config.example.json 为 config.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json 不是合法 JSON：{e}") from e
    try:
        return AppConfig.model_validate(data)
    except Exception as e:
        raise ConfigError(f"config.json 字段不合法：{e}") from e


def load_secrets() -> Secrets:
    return Secrets()
