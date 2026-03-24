# Mobile Portal

这是给手机端使用的独立入口页面。

目标：

- 不用在 GitHub 里手动点来点去
- 优先直接把内容提交到自己的轻量云后端
- 只有在云后端没配置时，才回退到 GitHub issue 提交页

说明：

- 页面本身是静态站点，可通过 GitHub Pages 托管，但 Pages 不是主入口
- 页面顶部的云端地址和写入口令会保存在手机浏览器本地
- 如果你已经部署了 OpenAI Cloud Hub，手机日常使用不再依赖 GitHub
- 如果云后端暂时没配好，直接使用仓库里的 `CLOUD_HUB.md` 和 issue form 链接也能稳定工作
