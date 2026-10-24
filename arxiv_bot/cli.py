"""命令行入口。

用法：
  python -m arxiv_bot run    [--preview]        每日任务（默认命令；未配 webhook 自动预览）
  python -m arxiv_bot weekly [--preview]        每周汇总
  python -m arxiv_bot search "soft robot" [--limit 20] [--pushed]   历史全文检索
  python -m arxiv_bot stats                     数据库统计
  python -m arxiv_bot init                      从模板生成 .env / config.json
  python -m arxiv_bot dashboard [--port 8300]   网页仪表盘（P1）
"""
from __future__ import annotations

import argparse
import shutil
import sys
from typing import Optional, Sequence

from .config import PROJECT_ROOT, ConfigError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arxiv_bot", description="arXiv 论文推送机器人")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="每日抓取与推送")
    p_run.add_argument("--preview", action="store_true", help="预览模式：只打印不推送")

    p_weekly = sub.add_parser("weekly", help="每周汇总报告")
    p_weekly.add_argument("--preview", action="store_true", help="预览模式")

    p_search = sub.add_parser("search", help="全文检索历史论文")
    p_search.add_argument("query", help="关键词，多个词用空格分隔（OR 关系）")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--pushed", action="store_true", help="只看已推送的")

    sub.add_parser("stats", help="数据库统计")
    sub.add_parser("init", help="从模板生成 .env 与 config.json（已存在则跳过）")

    p_dash = sub.add_parser("dashboard", help="启动网页仪表盘")
    p_dash.add_argument("--port", type=int, default=8300)
    return parser


def _cmd_init() -> None:
    """从模板生成本地配置文件；已存在的不覆盖。"""
    for src, dst in (
        (PROJECT_ROOT / ".env.example", PROJECT_ROOT / ".env"),
        (PROJECT_ROOT / "config.example.json", PROJECT_ROOT / "config.json"),
    ):
        if dst.exists():
            print(f"已存在，跳过：{dst.name}")
            continue
        shutil.copy(src, dst)
        print(f"已生成：{dst.name}，请打开填写后重新运行")


def _cmd_search(args: argparse.Namespace) -> None:
    from .pipeline import open_storage

    rows = open_storage().search(args.query, limit=args.limit, only_pushed=args.pushed)
    if not rows:
        print("没有检索到结果")
        return
    for r in rows:
        score = f"{r['relevance_score']:.2f}" if r["relevance_score"] is not None else "-"
        print(
            f"{r['pushed_at'] or r['created_at']}｜{r['source']}｜{score}｜"
            f"{r['status']}｜{r['title']}\n    {r['link']}"
        )


def _cmd_stats() -> None:
    from .pipeline import open_storage

    s = open_storage().stats()
    print(
        f"入库论文：{s['total']} 篇（已推送 {s['pushed']}，待推送 {s['new']}）\n"
        f"来源分布：{s['by_source']}"
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # Windows 控制台遇生僻字符不崩溃

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:  # 裸命令 python -m arxiv_bot 等价于 run
        args = parser.parse_args(["run"])

    from .logging_setup import setup_logging

    setup_logging()
    try:
        if args.command == "run":
            from .scheduler import daily

            daily(preview=args.preview)
        elif args.command == "weekly":
            from .scheduler import weekly

            weekly(preview=args.preview)
        elif args.command == "search":
            _cmd_search(args)
        elif args.command == "stats":
            _cmd_stats()
        elif args.command == "init":
            _cmd_init()
        elif args.command == "dashboard":
            from .dashboard import serve

            serve(port=args.port)
    except ConfigError as e:
        print(f"配置错误：{e}", file=sys.stderr)
        sys.exit(2)
    except Exception:  # noqa: BLE001 —— 具体异常已在各层记录，这里只控制退出码
        sys.exit(1)


if __name__ == "__main__":
    main()
