# Cloud Hub Setup

这套云端中枢只做你当前要的两件事：

1. `灵感收件箱`
2. `文章 / 视频学习请求`

## 手机入口

优先使用这个手机端入口：

- `GitHub Pages` 入口：`https://hanjixiang1234-rgb.github.io/solo-template-business/`

这个页面会先在手机上收集你的内容，再跳到已经预填好的 GitHub 提交页。
你不需要再自己手动选择模板和填写字段。

## 你在安卓上怎么用

### 灵感收件箱

1. 打开 GitHub App 或手机浏览器里的仓库
2. 进入 `Issues`
3. 选择 `灵感收件箱`
4. 填 1 句话灵感和你希望后面怎么处理
5. 提交

云端会做的事：

- GitHub Actions 立刻把这条灵感整理成结构化 JSON
- 存到 `cloud/inbox/ideas/`
- 同时生成云端阅读版和每日汇总到 `cloud/views/`

你开电脑后会发生的事：

- 本地同步脚本拉取最新仓库
- 新灵感落到 `research/mobile_inbox/ideas/`
- 同时写入本地记忆账本 `data/cloud_idea_memory.jsonl`
- 同时追加到 `minder/daily_ideas/YYYY-MM-DD.md`

### 文章 / 视频学习请求

1. 打开 `Issues`
2. 选择 `内容解析请求`
3. 选择 `article` 或 `video`
4. 粘贴公开链接
5. 告诉我你觉得它好在哪，以及你希望我重点提炼什么
6. 提交

云端会做的事：

- 文章：抓取正文或页面主要内容
- 视频：优先用 `yt-dlp` 抽元数据；如果是直链视频，会退回到直链元数据提取
- 如果配置了 `OPENAI_API_KEY`，会进一步生成结构化学习总结
- 结果存到 `cloud/processed/`
- 同时生成云端阅读版到 `cloud/views/learnings/`
- 同时更新云端每日学习汇总到 `cloud/views/daily_learning_updates/`
- 同时更新猫meme线程上下文到 `cloud/thread_sync/cat_meme_learning_context.md`
- 同时更新猫meme方法卡片到 `cloud/thread_sync/cat_meme_method_cards.md`

你开电脑后会发生的事：

- 新学习包落到 `research/cloud_learnings/`
- 同时写入本地学习账本 `data/cloud_learning_memory.jsonl`
- 同时追加到 `minder/daily_learning_updates/YYYY-MM-DD.md`
- 同时镜像到 `bilibili-cat-meme/minder/cloud_learnings/`
- 同时追加到 `bilibili-cat-meme/minder/daily_learning_updates/YYYY-MM-DD.md`

## 本地同步逻辑

同步脚本是：

```bash
python3 scripts/sync_cloud_hub_to_local.py --pull --trigger-label manual
```

它会做 3 件事：

1. 如果当前仓库已经连上 GitHub 上游，就先 `git pull --ff-only`
2. 导入新的灵感和学习包
3. 把云端已经生成好的内容镜像到本地 markdown、本地记忆账本、`minder` 每日日志，以及 `bilibili-cat-meme` 学习镜像

如果仓库还没连 GitHub，上面的 `pull` 会安静跳过，不会一直报错。

## 建议的本地常驻同步

```bash
cp ops/com.zhuanz1.minder-sync-terminal.plist ~/Library/LaunchAgents/com.zhuanz1.minder-sync-terminal.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zhuanz1.minder-sync-terminal.plist
launchctl enable gui/$(id -u)/com.zhuanz1.minder-sync-terminal
launchctl kickstart -k gui/$(id -u)/com.zhuanz1.minder-sync-terminal
```

这个 LaunchAgent 会在登录时运行一次，之后每 15 分钟同步一次。

这里不是直接让后台 Python 去碰 `Documents` 目录，而是：

`launchd -> osascript -> Terminal -> sync_cloud_hub_to_local.py`

这样做是因为 `Terminal` 执行这条命令时，可以正常访问 `Documents` 里的两个项目目录。

## GitHub 必要配置

1. 先把这个目录初始化为独立仓库并连上远端：

```bash
/Users/Zhuanz1/Documents/solo-template-business/scripts/connect_github_remote.sh <your-github-remote-url>
```

2. 把这个仓库推到 GitHub
3. 打开 GitHub Actions
4. 添加仓库 Secret：

- `OPENAI_API_KEY`

可选仓库变量：

- `OPENAI_MODEL`
  默认 `gpt-5-mini`

## 当前边界

- 最顺手的手机输入方式是 GitHub Issue Form
- 视频目前最适合公开平台链接或可直接访问的视频链接
- 就算没有 `OPENAI_API_KEY`，云端也会先把原始提取结果保存下来，不会把请求直接丢掉

## 学习原理

### 文章怎么学

- 云端脚本会先抓正文或页面主要文本
- 如果装了 `trafilatura`，优先用它抽主要内容
- 否则退回到页面标题和段落抽取

### 视频怎么学

- 云端脚本优先用 `yt-dlp` 提取公开视频元数据
- 如果不是平台页而是视频直链，会退回到直链元数据抽取

### 在哪里运行

- 文章和视频解析都运行在 GitHub Actions 的云端 runner
- 云端还会直接生成 markdown 阅读版、每日汇总和猫meme线程上下文
- 本地电脑只负责后续镜像同步和本地化沉淀

### 用什么在理解

- 第一层是规则提取：标题、正文、描述、标签、作者、链接等
- 第二层是可选的 AI 结构化总结：如果配置了 `OPENAI_API_KEY`，会生成 `source_summary`、`reusable_patterns`、`hook_observations`、`local_adaptation_ideas` 等字段
