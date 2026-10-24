# arxiv-bot 📚

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Tests](https://img.shields.io/badge/tests-35%20passed-brightgreen)

> 一句话：**多源论文情报推送机器人**——定时抓取 arXiv / Semantic Scholar / GitHub Trending，用「关键词 + 语义 + LLM」三层筛选，把真正相关的新论文用飞书消息卡片推给你，并沉淀为可全文检索的本地知识库。

<!-- 运行截图占位：截图放 docs/images/ 后取消注释
## 运行效果
![飞书卡片](docs/images/feishu-card.png)
![仪表盘](docs/images/dashboard.png)
-->

## 功能特性

- 🔎 **多数据源聚合**：arXiv 官方 API（主源）、Semantic Scholar、GitHub Trending（近 7 天高星新仓库）、任意会议 RSS；跨源自动去重（arXiv id 对齐 + 标题指纹），单源故障不影响整体
- 🧠 **三层筛选**：关键词规则（字面）→ embedding 语义相似度（方向描述 vs 论文摘要，numpy 本地实现，可切换向量 API）→ LLM 二次理解（是否相关 / 中文一句话点评 / 核心创新点 / 方法类别）
- 🛟 **全链路回退**：没配任何 API key 也能跑——语义退本地、LLM 直接跳过、卡片退纯文本预览，绝不因缺配置崩溃
- 📇 **飞书 interactive 卡片**：评分 / 来源 / 作者 / 分类分区展示 + 一键直达 arXiv
- 💾 **SQLite + FTS5**：全量论文落库（打分、LLM 结论、推送状态），支持历史全文检索 `python -m arxiv_bot search "soft robot"`
- 📊 **网页仪表盘**：抓取量、来源分布、命中率、推送成功率、关键词趋势（FastAPI + ECharts，本地可视化）
- 📋 **自动周报**：每周 LLM 综述近 7 天推送（无 key 自动回退统计版）
- 🔁 **工程健壮性**：失败重试（退避递增）、连续失败飞书告警、轮转文件日志、旧版 seen.json 一键迁移
- 🔐 **安全**：密钥只存 `.env`（gitignore），模板见 `.env.example` / `config.example.json`

## 架构说明

<!-- 架构图占位：画好后放 docs/images/architecture.png 并取消注释
![架构图](docs/images/architecture.png)
-->

```
数据源层            处理层                      输出层
┌──────────┐   ┌──────────────┐   ┌────────────────────┐
│ arXiv    │   │ filter  关键词 │   │ 飞书卡片（notifier）│
│ S2       │──▶│ semantic 语义 │──▶│ 仪表盘（FastAPI）   │
│ GitHub   │   │ llm     精选  │   │ 周报（weekly）      │
│ RSS      │   └──────┬───────┘   └────────────────────┘
└──────────┘          ▼
              SQLite + FTS5（storage，去重/检索/统计）
```

三个核心练习点（本项目起源）：**工具调用、错误重试、状态持久化**——一个"数据飞轮"的最小原型。

## 目录结构

```
arxiv-bot/
├── arxiv_bot/                # 主包
│   ├── cli.py                # 命令行入口（run/weekly/search/stats/dashboard/init）
│   ├── config.py             # 配置：.env 密钥 + config.json 业务参数（pydantic 校验）
│   ├── models.py             # 统一数据模型 Paper / PaperReview / ScoredPaper
│   ├── sources/              # 多数据源聚合层
│   │   ├── base.py           #   Source 接口
│   │   ├── arxiv_source.py   #   arXiv 主源
│   │   ├── semantic_scholar.py
│   │   ├── github_trending.py
│   │   ├── rss_source.py     #   任意会议 RSS
│   │   └── papers_with_code.py  # 官方 API 不稳定，默认关闭
│   ├── fetcher.py            # arXiv Atom 接口抓取（重试）
│   ├── filter.py             # 关键词 + 语义组合打分
│   ├── semantic.py           # 语义层：本地 numpy / OpenAI 兼容向量接口（预留 FAISS/Chroma）
│   ├── llm.py                # LLM 点评与周报（OpenAI 兼容接口，失败回退）
│   ├── notifier.py           # 飞书推送：文本 / interactive 卡片 / 告警
│   ├── pipeline.py           # 主流程编排 + 失败计数告警
│   ├── scheduler.py          # 调度入口（daily / weekly）
│   ├── storage.py            # SQLite + FTS5 存储层
│   ├── dashboard.py          # FastAPI 仪表盘
│   └── static/               # 仪表盘前端（ECharts 本地化）
├── tests/                    # pytest 测试（筛选/去重/存储/回退/数据源/仪表盘）
├── run_bot.py                # 兼容启动器（bat / 任务计划程序用）
├── run_bot.bat               # Windows 双击运行
├── config.example.json       # 业务配置模板
├── .env.example              # 密钥模板
├── .github/workflows/        # GitHub Actions 云端定时方案
└── docs/GITHUB_SETUP.md      # 发布到 GitHub 的手把手操作清单
```

## 快速开始

```bash
# 1. 克隆 / 进入项目，安装依赖（Python 3.9+）
pip install -r requirements.txt

# 2. 生成本地配置
python -m arxiv_bot init          # 生成 .env 与 config.json（或手动复制 *.example）

# 3. 填写飞书机器人 webhook（见下文「配置说明」），然后：
python -m arxiv_bot run --preview # 预览：只打印不推送
python -m arxiv_bot run           # 正式：推送飞书卡片

# 其他命令
python -m arxiv_bot search "soft robot"   # 历史全文检索
python -m arxiv_bot stats                 # 数据库统计
python -m arxiv_bot weekly --preview      # 周报预览
python -m arxiv_bot dashboard             # 仪表盘 http://127.0.0.1:8300
```

**测试与静态检查**（开发者）：

```bash
pip install -r requirements-dev.txt
pytest               # 全部测试
ruff check .         # 静态检查
```

## 配置说明

### `.env`（密钥，绝不入库）

| 变量 | 必填 | 说明 |
|---|---|---|
| `FEISHU_WEBHOOK` | 推送必填 | 飞书群自定义机器人地址；留空=预览模式 |
| `LLM_API_KEY` | 否 | OpenAI 兼容接口 key（示例：智谱 glm-4-flash 免费档）；留空自动回退 |
| `LLM_BASE_URL` / `LLM_MODEL` | 否 | 接口地址与模型名 |
| `EMBEDDING_API_KEY` 等 | 否 | 向量接口；留空用本地 numpy 语义匹配 |

### `config.json`（业务参数）

| 字段 | 说明 |
|---|---|
| `research_focus` | 研究方向描述（语义匹配与 LLM 的输入，建议中文+英文关键词混写） |
| `categories` / `keywords` | arXiv 栏目 / 关键词（OR 命中） |
| `fetch_count` / `max_push` | 单次抓取量 / 单次推送上限 |
| `semantic` | 语义开关、后端（auto/local/api）、召回门槛 `min_score` |
| `llm` | LLM 开关与精评篇数 `top_k` |
| `alert` | 连续失败多少次触发飞书告警 |
| `sources.*` | 各数据源开关与参数 |

> 飞书机器人获取：群设置 → 群机器人 → 添加「自定义机器人」→ 安全设置勾「自定义关键词」填 `论文速递`（或 `arxiv`）→ 复制 webhook。

## 定时运行

| 方式 | 适用 | 说明 |
|---|---|---|
| **Windows 任务计划程序（主力，当前启用）** | 本机常开 | 每日 08:00 `run_bot.py run`、周一 08:30 `weekly`；已配置"电池可运行/错过补跑/唤醒" |
| **GitHub Actions（手动备用，定时默认关闭）** | 电脑不常开/外出时 | `.github/workflows/arxiv-bot.yml` 只保留 Run workflow 手动触发；想改云端定时就取消 schedule 注释并禁用本地任务（cron 为 **UTC**，北京 08:00 = `0 0 * * *`）；密钥走 Secrets；云端无状态、与本地可能有少量重复 |
| 云服务器 / 云函数 | 进阶 | 一台常驻小主机（或函数计算 + 定时器）拉取本仓库执行 `python -m arxiv_bot run` 即可，密钥用平台环境变量注入 |

## 技术栈

Python 3.9+ · requests / feedparser（抓取） · pydantic / pydantic-settings（配置校验） · numpy（本地语义） · SQLite FTS5（存储检索） · FastAPI + uvicorn + ECharts（仪表盘） · pytest / ruff（工程质量）

## Roadmap

- [ ] **卡片按钮回调闭环**：现仅 URL 跳转按钮；「收藏 / 不感兴趣」等交互需企业自建应用接收 card.action 回调（webhook 单向限制）
- [ ] **向量库升级**：论文过万后接入 FAISS / Chroma 替换 numpy 暴力计算（接口已预留 `semantic.py`）
- [ ] **Papers with Code 替代源**：官方 API 不稳定，计划换 Hugging Face Datasets
- [ ] 用户反馈闭环（推送后点击行为回流到评分权重）——真正的"飞轮"
- [ ] 多用户 / 多方向订阅
- [ ] Docker 一键部署

## License

[MIT](LICENSE) © 2026 paratrooper-vincent
