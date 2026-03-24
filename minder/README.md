# Minder

`minder` 是本地自动沉淀层。

这里会保存两类自动同步结果：

- `daily_ideas/`
  每天新增灵感的日志
- `daily_learning_updates/`
  每天新增文章/视频学习包的日志
- `sync_status/`
  每次本地同步后的状态页，方便确认这次有没有把云端结果拉下来

这些文件由 `scripts/sync_cloud_hub_to_local.py` 自动维护，不需要手动编辑。
