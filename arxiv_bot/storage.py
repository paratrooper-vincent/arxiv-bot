"""存储层：SQLite 持久化 + FTS5 全文检索 + 运行状态（失败计数、每日运行史）。

表结构：
- papers      论文主表，paper_id 唯一；含打分、LLM 结论、推送状态
- papers_fts  title/abstract 的 FTS5 全文索引（触发器与主表自动同步）
- meta        键值表：连续失败计数、run_history 等
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

from .models import ScoredPaper

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    abstract        TEXT DEFAULT '',
    authors         TEXT DEFAULT '[]',
    categories      TEXT DEFAULT '',
    published       TEXT DEFAULT '',
    link            TEXT DEFAULT '',
    source          TEXT DEFAULT 'arxiv',
    matched_rule    TEXT DEFAULT '',
    relevance_score REAL,
    llm_relevant    INTEGER,
    llm_comment     TEXT DEFAULT '',
    llm_innovation  TEXT DEFAULT '',
    llm_category    TEXT DEFAULT '',
    status          TEXT DEFAULT 'new',
    pushed_at       TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    title, abstract, content='papers', content_rowid='rowid'
);
"""

# FTS5 外部内容表需要触发器维护索引与主表一致
_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(rowid, title, abstract)
    VALUES (new.rowid, new.title, new.abstract);
END;
CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
    VALUES ('delete', old.rowid, old.title, old.abstract);
END;
CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
    VALUES ('delete', old.rowid, old.title, old.abstract);
    INSERT INTO papers_fts(rowid, title, abstract)
    VALUES (new.rowid, new.title, new.abstract);
END;
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Storage:
    """SQLite 存储门面；加锁 + WAL，任务进程与仪表盘线程可安全共用。"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.fts_enabled = self._init_schema()

    def _init_schema(self) -> bool:
        """建表；返回 FTS5 是否可用（不可用时全文检索自动降级为 LIKE）。"""
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            try:
                self._conn.executescript(_FTS + _TRIGGERS)
                return True
            except sqlite3.OperationalError as e:
                logger.warning("FTS5 不可用，全文检索降级为 LIKE 匹配：%s", e)
                return False

    def close(self) -> None:
        self._conn.close()

    # ==================== 论文 ====================

    def upsert_scored(self, items: Sequence[ScoredPaper]) -> None:
        """写入/更新候选论文（含打分与 LLM 结论）。

        已推送过的行不会被降级：ON CONFLICT 更新不碰 status / pushed_at。
        """
        with self._lock, self._conn:
            for s in items:
                review = s.review
                self._conn.execute(
                    """
                    INSERT INTO papers (paper_id, title, abstract, authors, categories,
                        published, link, source, matched_rule, relevance_score,
                        llm_relevant, llm_comment, llm_innovation, llm_category, status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new')
                    ON CONFLICT(paper_id) DO UPDATE SET
                        title=excluded.title, abstract=excluded.abstract,
                        authors=excluded.authors, categories=excluded.categories,
                        published=excluded.published, link=excluded.link,
                        source=excluded.source, matched_rule=excluded.matched_rule,
                        relevance_score=excluded.relevance_score,
                        llm_relevant=excluded.llm_relevant,
                        llm_comment=excluded.llm_comment,
                        llm_innovation=excluded.llm_innovation,
                        llm_category=excluded.llm_category
                    """,
                    (
                        s.paper.paper_id,
                        s.paper.title,
                        s.paper.abstract,
                        json.dumps(s.paper.authors, ensure_ascii=False),
                        ",".join(s.paper.categories),
                        s.paper.published,
                        s.paper.link,
                        s.paper.source,
                        s.matched_rule,
                        s.final_score,
                        None if review is None or review.relevant is None else int(review.relevant),
                        review.comment if review else "",
                        review.innovation if review else "",
                        review.category if review else "",
                    ),
                )

    def pushed_ids(self) -> Set[str]:
        """已推送过的论文 id 集合——去重的唯一依据，防止重复推送。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT paper_id FROM papers WHERE status='pushed'"
            ).fetchall()
        return {r["paper_id"] for r in rows}

    def mark_pushed(self, paper_ids: Iterable[str]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE papers SET status='pushed', pushed_at=? WHERE paper_id=?",
                [(_now(), pid) for pid in paper_ids],
            )

    def search(
        self, query: str, limit: int = 20, only_pushed: bool = False
    ) -> List[sqlite3.Row]:
        """全文检索：FTS5 优先（多词 OR），异常或未启用时降级 LIKE。"""
        cond = "AND status='pushed'" if only_pushed else ""
        if self.fts_enabled and query.strip():
            terms = " OR ".join(f'"{t}"' for t in query.split() if t)
            sql = f"""
                SELECT p.* FROM papers_fts f
                JOIN papers p ON p.rowid = f.rowid
                WHERE papers_fts MATCH ? {cond}
                ORDER BY rank LIMIT ?
            """
            try:
                with self._lock:
                    return self._conn.execute(sql, (terms, limit)).fetchall()
            except sqlite3.OperationalError:
                logger.warning("FTS 查询语法异常，降级 LIKE：%r", query)
        like = f"%{query}%"
        sql = f"SELECT * FROM papers WHERE (title LIKE ? OR abstract LIKE ?) {cond} LIMIT ?"
        with self._lock:
            return self._conn.execute(sql, (like, like, limit)).fetchall()

    def recent_pushed(self, days: int = 7) -> List[sqlite3.Row]:
        """最近 N 天推送过的论文（周报数据源）。"""
        with self._lock:
            return self._conn.execute(
                """SELECT * FROM papers WHERE status='pushed' AND pushed_at != ''
                   AND pushed_at >= datetime('now', 'localtime', ?)
                   ORDER BY pushed_at DESC""",
                (f"-{days} days",),
            ).fetchall()

    def list_papers(
        self, limit: int = 50, offset: int = 0, status: Optional[str] = None
    ) -> List[sqlite3.Row]:
        cond = "WHERE status=?" if status else ""
        sql = f"SELECT * FROM papers {cond} ORDER BY rowid DESC LIMIT ? OFFSET ?"
        params: tuple = (status, limit, offset) if status else (limit, offset)
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def stats(self) -> Dict[str, object]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) c FROM papers").fetchone()["c"]
            pushed = self._conn.execute(
                "SELECT COUNT(*) c FROM papers WHERE status='pushed'"
            ).fetchone()["c"]
            by_source = {
                r["source"]: r["c"]
                for r in self._conn.execute(
                    "SELECT source, COUNT(*) c FROM papers GROUP BY source ORDER BY c DESC"
                )
            }
            by_day = [
                dict(r)
                for r in self._conn.execute(
                    """SELECT substr(pushed_at, 1, 10) AS day, COUNT(*) AS count
                       FROM papers
                       WHERE status='pushed' AND pushed_at != ''
                       GROUP BY day ORDER BY day DESC LIMIT 14"""
                )
            ]
            by_rule = [
                dict(r)
                for r in self._conn.execute(
                    """SELECT matched_rule AS rule, COUNT(*) AS count FROM papers
                       WHERE matched_rule != '' GROUP BY rule ORDER BY count DESC LIMIT 10"""
                )
            ]
        return {
            "total": total,
            "pushed": pushed,
            "new": total - pushed,
            "by_source": by_source,
            "by_day": by_day,
            "by_rule": by_rule,
        }

    # ==================== 运行状态 ====================

    def _get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def _set_meta(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def record_failure(self) -> int:
        """整体运行失败 +1，返回最新连续失败次数。"""
        n = int(self._get_meta("consecutive_failures", "0")) + 1
        self._set_meta("consecutive_failures", str(n))
        return n

    def record_success(self) -> None:
        self._set_meta("consecutive_failures", "0")

    def consecutive_failures(self) -> int:
        return int(self._get_meta("consecutive_failures", "0"))

    def log_run(self, ok: bool, pushed: int) -> None:
        """记录每日运行史（仪表盘统计推送成功率用），只保留最近 60 天。"""
        history = json.loads(self._get_meta("run_history", "{}"))
        today = datetime.now().strftime("%Y-%m-%d")
        entry = history.get(today, {"runs": 0, "ok": 0, "pushed": 0})
        entry["runs"] += 1
        entry["ok"] += 1 if ok else 0
        entry["pushed"] += pushed
        history[today] = entry
        if len(history) > 60:
            history = dict(sorted(history.items())[-60:])
        self._set_meta("run_history", json.dumps(history, ensure_ascii=False))

    def run_history(self) -> Dict[str, dict]:
        return json.loads(self._get_meta("run_history", "{}"))

    def import_legacy_seen(self, seen_path: Path) -> int:
        """迁移旧版 seen.json（幂等）：只补 paper_id 和推送日期，防止旧论文被重推。"""
        if not seen_path.exists():
            return 0
        try:
            data = json.loads(seen_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        imported = 0
        with self._lock, self._conn:
            for pid, date in data.items():
                # 旧版 id 形如 2610.12345v1，新版统一为 arxiv: 前缀
                new_id = pid if ":" in pid else f"arxiv:{pid}"
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO papers (paper_id, title, source, status, pushed_at) "
                    "VALUES (?, '(旧版 seen.json 导入)', 'legacy', 'pushed', ?)",
                    (new_id, str(date)),
                )
                imported += cur.rowcount
        if imported:
            logger.info("旧版 seen.json 迁移 %d 条", imported)
        return imported
