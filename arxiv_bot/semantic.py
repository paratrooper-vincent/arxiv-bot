"""语义匹配层：研究方向描述 vs 论文文本 的向量化余弦相似度。

后端选择（backend=auto）：
- 配置了 EMBEDDING_API_KEY + EMBEDDING_BASE_URL → OpenAI 兼容 /embeddings 接口；
- 否则 → 本地字符 n-gram TF 向量（numpy 实现，零费用、离线可用，百级文档规模够用）；
- 接口调用失败 → 自动回退本地。

扩展预留：本模块 scores() 即向量检索唯一入口，后续接 FAISS / Chroma
只需替换内部实现，调用方（filter.pipeline）完全不用改。
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Sequence

import numpy as np
import requests

from .config import Secrets
from .utils import retry_call

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """只保留中英文与数字，小写化，让中英混合描述也能稳定切 n-gram。"""
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _ngrams(text: str, n: int = 3) -> List[str]:
    tokens = _normalize(text)
    if not tokens:
        return []
    if len(tokens) <= n:
        return [tokens]
    return [tokens[i : i + n] for i in range(len(tokens) - n + 1)]


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class LocalEncoder:
    """字符 n-gram TF 向量编码器：次线性 TF 抑制长文优势，L2 归一化后点积即余弦。"""

    def fit_transform(self, texts: Sequence[str]) -> np.ndarray:
        vocab: Dict[str, int] = {}
        grams_list = [_ngrams(t) for t in texts]
        for grams in grams_list:
            for g in grams:
                vocab.setdefault(g, len(vocab))
        counts = np.zeros((len(texts), len(vocab)))
        for row, grams in enumerate(grams_list):
            for g in grams:
                counts[row, vocab[g]] += 1.0
        # 次线性 TF：1 + log(tf)，且只作用于原本非零的位置（零位保持 0）
        tf = np.zeros_like(counts)
        mask = counts > 0
        tf[mask] = 1.0 + np.log(counts[mask])
        return _l2_normalize(tf)


class SemanticEngine:
    """语义打分门面：自动选后端、逐级回退，整体失败由上层退回关键词方案。"""

    def __init__(self, secrets: Secrets, backend: str = "auto"):
        self._secrets = secrets
        self._backend = backend

    def scores(self, query: str, docs: Sequence[str]) -> List[float]:
        """返回每个 doc 与 query 的余弦相似度（0~1，越高越相关）。"""
        if not docs:
            return []
        use_api = bool(
            self._backend in ("auto", "api")
            and self._secrets.embedding_api_key
            and self._secrets.embedding_base_url
        )
        if use_api:
            try:
                return self._api_scores(query, docs)
            except Exception as e:  # noqa: BLE001 —— 接口失败回退本地
                logger.warning("向量接口失败，回退本地匹配：%s", e)
        return self._local_scores(query, docs)

    def _local_scores(self, query: str, docs: Sequence[str]) -> List[float]:
        texts = [query, *docs]
        mat = LocalEncoder().fit_transform(texts)
        sims = (mat[1:] @ mat[0]).clip(min=0.0)
        return [round(float(s), 4) for s in sims]

    def _api_scores(self, query: str, docs: Sequence[str]) -> List[float]:
        logger.info("语义后端：向量接口（%s）", self._secrets.embedding_model)

        def embed_batch(batch: List[str]) -> List[np.ndarray]:
            def do() -> List[np.ndarray]:
                resp = requests.post(
                    f"{self._secrets.embedding_base_url.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {self._secrets.embedding_api_key}"},
                    json={"model": self._secrets.embedding_model, "input": batch},
                    timeout=60,
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                return [np.array(d["embedding"], dtype=float) for d in data]

            return retry_call(do, "embedding接口")

        vectors = embed_batch([query])
        for i in range(0, len(docs), 25):  # 分批，避免单次请求过大
            vectors.extend(embed_batch(list(docs[i : i + 25])))
        q = vectors[0] / (np.linalg.norm(vectors[0]) or 1.0)
        result = []
        for v in vectors[1:]:
            norm = float(np.linalg.norm(v))
            result.append(round(float(q @ v) / norm, 4) if norm else 0.0)
        return result
