# OpenAI Cloud Hub Setup

这套方案是 `去 GitHub 日常依赖版`：

- 手机入口直接提交到你自己的轻量云后端
- 云后端用 OpenAI 做文章 / 视频理解与方法提炼
- 电脑开机联网后，自动把云端结果同步到本地 `minder` 和 `bilibili-cat-meme`

## 架构

`Phone -> OpenAI Cloud Hub API -> OpenAI processing -> local sync -> minder / bilibili-cat-meme`

## 关键文件

- 云后端服务：
  `/Users/Zhuanz1/Documents/solo-template-business/scripts/openai_cloud_hub_server.py`
- 本地同步脚本：
  `/Users/Zhuanz1/Documents/solo-template-business/scripts/sync_cloud_hub_to_local.py`
- 手机入口：
  `/Users/Zhuanz1/Documents/solo-template-business/mobile_portal/index.html`
- 本地配置模板：
  `/Users/Zhuanz1/Documents/solo-template-business/config/openai_cloud_hub.example.json`

## 云后端做什么

### 提交接口

- `POST /api/v1/submissions`
- 接收两类任务：
  - `idea`
  - `learning`

### 查询接口

- `GET /health`
- `GET /api/v1/feed?after_id=0`
- `GET /api/v1/submissions/<id>`
- `GET /api/v1/overview`

### 云端处理逻辑

- `idea`：
  直接整理成结构化灵感包
- `learning`：
  - 文章优先抓正文或页面主要文本
  - 视频优先抓平台页元数据或直链元数据
  - 如果配置了 `OPENAI_API_KEY`，会尝试生成结构化总结
  - 如果没有，也会走启发式方法提炼，不会直接丢掉

## 需要的环境变量

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
  - 可选，默认走 `gpt-5-mini`
- `MINDER_CLOUD_WRITE_TOKEN`
  - 手机写入口令
- `MINDER_CLOUD_READ_TOKEN`
  - 电脑同步口令
- `MINDER_CLOUD_PUBLIC_BASE_URL`
  - 可选，用于生成外部可访问的任务详情链接

## 本地先跑起来

```bash
cd /Users/Zhuanz1/Documents/solo-template-business
export OPENAI_API_KEY=your_key
export MINDER_CLOUD_WRITE_TOKEN=your_write_token
export MINDER_CLOUD_READ_TOKEN=your_read_token
python3 scripts/openai_cloud_hub_server.py --host 0.0.0.0 --port 8787
```

## 手机入口怎么配

手机端页面现在支持双模：

1. 优先直连 OpenAI Cloud Hub
2. 如果没配云端地址和口令，就自动回退到 GitHub 提交

你只要在手机页面顶部填：

- `云端接口地址`
  - 例如 `https://your-openai-cloud-hub.example.com`
- `写入口令`

然后点保存。

## 本地同步怎么配

先复制一份本地配置：

```bash
cp /Users/Zhuanz1/Documents/solo-template-business/config/openai_cloud_hub.example.json \
  /Users/Zhuanz1/Documents/solo-template-business/config/openai_cloud_hub.local.json
```

把里面改成你自己的：

```json
{
  "api_base_url": "https://your-openai-cloud-hub.example.com",
  "read_token": "replace-with-read-token"
}
```

然后你原来的同步脚本就能自动切到 API 模式：

```bash
python3 /Users/Zhuanz1/Documents/solo-template-business/scripts/sync_cloud_hub_to_local.py \
  --pull \
  --trigger-label manual
```

当 `openai_cloud_hub.local.json` 存在时：

- 脚本会先从 `/api/v1/feed` 拉结果
- 把结构化 JSON 写入本地 `cloud/`
- 再继续同步到 `minder/`
- 再继续镜像到 `bilibili-cat-meme/`

## 自动同步

当前本地 LaunchAgent 仍然可以继续用。

原因是：

- 同步脚本没有换路径
- 只是新增了“如果存在 API 配置，就优先走云后端拉取”这层逻辑

也就是说，电脑开机联网后，它会自动：

1. 从你的 OpenAI Cloud Hub 拉取新结果
2. 落到本地 `minder`
3. 更新猫 meme 的线程上下文和方法卡片

## 当前边界

- 这是“OpenAI + 轻量云后端”方案，不是“只有 OpenAI 一个服务就全包”
- 轻量云后端负责：
  - 公开 HTTP 入口
  - 提交认证
  - 持久化队列
  - 给本地电脑可轮询的 feed
- OpenAI 负责：
  - 理解
  - 总结
  - 方法提炼
  - 学习结构化输出

## 为什么这样更合适

- 不需要你每天打开 GitHub
- 手机日常使用不再绑定 GitHub 帐号
- 云端处理和本地落盘仍然分层，稳定性更高
- 即使后面想把后端从一个云主机迁到另一个云主机，手机入口和本地同步逻辑都能复用
