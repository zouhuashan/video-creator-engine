# Storyboard 阶段

将已完成的 `script.json` 展开为微信视频号逐镜头分镜。

## 前置条件

- 项目状态必须为 `SCRIPTED`，并读取 `script.json`、[storyboard-template.md](../../../templates/wechat-channel/storyboard-template.md) 与 [storyboard-input.schema.json](../../../templates/storyboard-input.schema.json)。
- 分镜必须覆盖脚本中所有口播内容，顺序不能变化。不要增写未经脚本校验的口播内容。
- 事实性画面使用脚本已有来源编号；每个已引用来源至少要在一个镜头的 `source` 中出现，方便后续核验。

## 编写与落盘

为每个镜头填写 `scene_id`、`start`、`end`、`spoken_text`、`caption`、`visual_description`、`visual_type`、`asset_query`、`motion`、`transition`、`source`。从 `SC001` 连续编号，时间从 0 秒无缝衔接至脚本的目标时长。`source` 是来源编号数组，无来源时填写空数组。`visual_type` 只能使用 `screen_recording`、`screenshot`、`real_video`、`real_image`、`stock`、`hyperframes`、`remotion`、`ai_image`、`ai_video`、`text_only`、`chart`、`comparison`。

将 JSON 输入保存到临时文件后运行：

```text
./video-creator storyboard <project-id> --input-file <storyboard-input.json>
```

命令会校验口播覆盖、连续时间、镜头编号、来源追溯和结束时间，生成 `storyboard.json` 与 `storyboard.md`，然后把项目从 `SCRIPTED` 推进到 `STORYBOARDED`。校验失败、写入失败或已有产物时不会推进状态。

生成分镜后立即运行 `./video-creator review-storyboard <project-id>`。它会输出 `storyboard-review.json`、`storyboard-review.md`，检查静态画面、重复视觉、纯字幕堆叠、来源证据、前三秒 Hook 和结论视觉强化。若 `passed=false`，先修订分镜，不进入素材阶段。审查只生成报告，不改变项目状态。
