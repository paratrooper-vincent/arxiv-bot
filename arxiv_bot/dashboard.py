"""FastAPI 仪表盘：查看每日抓取量、命中率、推送成功率、关键词趋势与论文列表。

启动：python -m arxiv_bot dashboard [--port 8300]
默认只监听 127.0.0.1（本机访问），如需局域网访问请自行改 host 并注意数据隐私。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .storage import Storage

logger = logging.getLogger(__name__)
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(storage: Optional[Storage] = None) -> FastAPI:
    """构建仪表盘应用；storage 可注入（测试用），默认打开 data/arxiv.db。"""
    from .pipeline import open_storage

    app = FastAPI(title="arxiv-bot 仪表盘", docs_url="/api/docs")
    app.state.storage = storage or open_storage()
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/api/summary")
    def summary() -> Dict[str, Any]:
        """总览：库容、来源分布、近 14 天推送量、运行成功率。"""
        st = app.state.storage
        stats = st.stats()
        history = st.run_history()
        total_runs = sum(h["runs"] for h in history.values())
        ok_runs = sum(h["ok"] for h in history.values())
        return {
            **stats,
            "run_days": len(history),
            "success_rate": round(ok_runs / total_runs, 3) if total_runs else None,
            "consecutive_failures": st.consecutive_failures(),
        }

    @app.get("/api/papers")
    def papers(
        status: Optional[str] = Query(None, description="pushed / new，留空=全部"),
        q: Optional[str] = Query(None, description="全文检索关键词"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> Dict[str, Any]:
        st = app.state.storage
        rows = (
            st.search(q, limit=limit, only_pushed=(status == "pushed"))
            if q
            else st.list_papers(limit=limit, offset=offset, status=status)
        )
        return {"items": [dict(r) for r in rows]}

    @app.get("/api/trends")
    def trends() -> Dict[str, Any]:
        """命中规则分布（关键词/语义各贡献多少）与逐日推送量。"""
        stats = app.state.storage.stats()
        return {"by_rule": stats["by_rule"], "by_day": stats["by_day"]}

    return app


def serve(port: int = 8300, host: str = "127.0.0.1") -> None:
    """启动仪表盘服务（阻塞运行）。"""
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
