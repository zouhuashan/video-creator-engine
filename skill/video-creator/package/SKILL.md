---
name: video-creator-package
description: Build an integrity-checked WeChat Channels publishing package after QC passes.
---

# VideoCreator Packaging

只有状态为 `QC_PASS` 且 `qc.json` 明确通过的项目可以打包。运行 `./video-creator package <project-id>`，将 `final.mp4`、`cover.png`、`title.md`、`caption.md`、`hashtags.md`、`sources.md` 和 `qc-report.md` 复制到 `publish-package/`，并用 `package.json` 记录大小和 SHA-256。缺少、空白、符号链接或格式错误的产物会中止打包，不推进状态。

发布包只供人工检查和上传。配置中的 `auto_publish` 必须为 false，禁止在打包步骤调用微信、浏览器自动化或任何发布接口。
