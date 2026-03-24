# Mobile Portal

这是给手机端使用的独立入口页面。

目标：

- 不用在 GitHub 里手动点来点去
- 在手机端先完成表单交互
- 再跳到已经预填好的 GitHub issue 提交页

说明：

- 页面本身是静态站点，可通过 GitHub Pages 托管，但 Pages 不是主入口
- 提交后仍需要 GitHub 登录态，因为云端工作流当前依赖 GitHub issues 作为接收层
- 如果 Pages 没启用，直接使用仓库里的 `CLOUD_HUB.md` 和 issue form 链接也能稳定工作
