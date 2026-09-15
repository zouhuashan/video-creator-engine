---
name: video-creator-review
description: Verify the final package and stop at the human publication gate.
---

# VideoCreator Human Review

项目必须处于 `PACKAGED`。运行 `python3 scripts/review_gate.py <project-dir> <project-id>`，重新计算 `publish-package/` 中七个交付文件的大小和 SHA-256，核对 `package.json`、汇总 QC PASS 及人工发布配置。任一文件变化或检查失败都不推进状态。

验证通过后写入 `review-gate.json`，把状态推进到 `READY_FOR_REVIEW`，显示 `FINAL READY` 和 `WAITING FOR HUMAN PUBLISH`。在用户明确表示已经人工发布前停在这里；不得把“准备发布”理解为发布授权。
