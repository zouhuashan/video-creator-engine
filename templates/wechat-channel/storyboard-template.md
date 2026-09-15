# 微信视频号分镜模板

将通过校验的脚本口播完整、按顺序拆入镜头。所有镜头时间连续，首镜从 0 秒开始，末镜结束时间等于脚本目标时长。

每个镜头都填写：`scene_id`（从 `SC001` 连续编号）、`start`、`end`、`spoken_text`、`caption`、`visual_description`、`visual_type`、`asset_query`、`motion`、`transition` 和 `source`。`source` 使用脚本中的来源编号；有引用的事实必须在至少一个证据画面中关联对应来源。

`visual_type` 只能使用：`screen_recording`、`screenshot`、`real_video`、`real_image`、`stock`、`hyperframes`、`remotion`、`ai_image`、`ai_video`、`text_only`、`chart`、`comparison`。自动分镜审查将在后续任务接入。
