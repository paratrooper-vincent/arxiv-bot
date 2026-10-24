# 发布到 GitHub：手把手操作清单

> 本文档是**需要你自己动手**的部分（涉及账号操作，AI 不能代办）。
> 本地仓库已由 AI 初始化并完成首次提交，你从第 3 步开始做即可。

## 0. 前置检查（已为你完成 ✅）

- [x] Git 已安装（本机 Git Bash 可用）
- [x] 本地仓库已 `git init`，首次提交已完成
- [x] `.env` / `config.json` / 数据库 / 日志 已被 .gitignore 忽略，密钥不会上传
- [x] SSH 密钥已配置（`ssh -T git@github.com` 能通）

## 1. 设置你的 git 签名（一次性，全局）

打开 Git Bash，逐行粘贴执行（邮箱用 GitHub 给你的匿名邮箱，不暴露真实邮箱）：

```bash
git config --global user.name "paratrooper-vincent"
git config --global user.email "paratrooper-vincent@users.noreply.github.com"
```

> 如果想用真实邮箱也可以，换成你的常用邮箱即可。

## 2. 在 GitHub 网站上建一个空仓库（不要勾选初始化！）

1. 打开 https://github.com/new （需登录 paratrooper-vincent 账号）
2. Repository name 填：`arxiv-bot`
3. Description 可填：`多源论文情报推送机器人：arXiv/S2/GitHub Trending → 三层筛选 → 飞书卡片`
4. 选 **Private**（先私有，验证无误后再切公开，切换方法见第 6 步）
5. **不要勾选** Add a README / .gitignore / license（本地都有了，勾了会冲突）
6. 点 Create repository

## 3. 本地仓库连上远程并推送

在 Git Bash 中（路径换成你的实际路径）：

```bash
cd "/d/桌面/GitHub开源项目/arxiv-bot"
git remote add origin git@github.com:paratrooper-vincent/arxiv-bot.git
git push -u origin main
```

> 注意：remote 报 `Repository not found` 时，先检查 `paratrooper-vincent` 有没有打错（历史上出过账号名手误）。

## 4. 配置 Actions 密钥（Secrets）

仓库页面 → **Settings** → 左侧 **Secrets and variables** → **Actions** → **New repository secret**，逐个添加：

| Name | Secret 值 | 必填 |
|---|---|---|
| `FEISHU_WEBHOOK` | 你的飞书机器人 webhook 地址（在本地 `.env` 里有） | ✅ |
| `LLM_API_KEY` | 智谱等平台的 key（没有就先不加） | 可选 |
| `LLM_BASE_URL` | 如 `https://open.bigmodel.cn/api/paas/v4` | 可选 |
| `LLM_MODEL` | 如 `glm-4-flash` | 可选 |

配置后到 **Actions** 标签页 → 选 `arxiv-bot` 工作流 → **Run workflow** → 选 `run` 手动触发一次，看是否跑通。

> 提醒：本地 Windows 任务计划和 GitHub Actions **二选一**作为主力（两边都开会有重复推送，云端没有去重数据库）。建议：电脑常开用本地；电脑不常开用 Actions（此时把本地任务禁用：任务计划程序 → arxiv_bot → 禁用）。

## 5. 完善 GitHub 门面（可选但推荐）

1. **About 栏**（仓库首页右上角齿轮）：加描述 + Topics：`arxiv` `python` `feedparser` `feishu` `llm` `semantic-search` `sqlite` `robotics`（用空格分隔）；勾选 Releases 显示
2. **Release 发布版本**：仓库 → Releases → Draft a new release → tag 填 `v2.1.0`，标题 `v2.1.0 多源聚合与智能筛选`，附一段更新说明 → Publish
3. **徽章**：README 顶部有注释好的徽章占位，取消注释即可
4. **截图**：飞书卡片、仪表盘截图存到 `docs/images/`，取消 README 中截图注释

## 6. 切换为公开仓库（想开源时）

Settings → 拉到最底 **Danger Zone** → Change visibility → Make public → 按提示输入仓库名确认。

> 切换前再自查一遍：`git ls-files` 里不应出现 `.env`、`config.json`、`data/`、`logs/`。

## 7. 日常更新流程（以后每次改完代码）

```bash
cd "/d/桌面/GitHub开源项目/arxiv-bot"
git add -A
git commit -m "一句话说明改了什么"
git push
```
