# OpenAI Image Provider / Web AI 生图

## 定位

OpenAI Image 是 VideoCreator 的高质量图片备用 Provider，用于角色定妆板、镜头关键帧和后续 rescue-shot。它不是独立聊天旁路：所有结果直接写入当前国漫项目并进入人工审核门。

当前默认模型：`gpt-image-2`。

## Web 使用

打开现有 VideoCreator Web Console（默认 `http://127.0.0.1:18765`），点击左侧 **AI 生图**。

页面提供：

- 国漫项目选择；
- OpenAI API Key 会话配置；
- **生成角色定妆板**；
- **生成镜头关键帧**；
- 附加 prompt；
- 最近生成预览；
- **通过** / **需要修改** 人工审核。

不需要为了日常生图单独运行终端 command。

## 密钥

密钥沿用 Web Console 当前安全策略：

- 只保存在当前服务进程的内存；
- 不写项目文件；
- 不写日志；
- 不通过状态 API 返回；
- Web 服务重启后需重新输入，除非系统环境已经存在 `OPENAI_API_KEY`。

OpenAI Sora 与 OpenAI Image 使用同一个 `OPENAI_API_KEY` 时，当前 Web session 可复用已输入的 Sora key。

## Provider Router

`support/providers/image_provider_router.py` 是最终视觉的可执行路由层。它只做选择和门禁，不做网络请求：高质量最终视觉先进入 `IMAGE_PROVIDER_ROUTER`，当前没有更高优先级 Provider 时回退到 `OPENAI_IMAGE`；`BLENDER_ANIME` 固定为 `AUXILIARY_3D_CONTROL`，不能被当成最终画质 Provider。

Router 同时强制执行远程计费确认和未来参考图上传授权。Web 状态 API 会返回路由摘要，页面直接显示当前最终视觉路由与 Blender 角色。

## API

- `GET /api/image-studio/status?project_id=<project>`
- `POST /api/image-studio/character-bible`
- `POST /api/image-studio/keyframe`
- `POST /api/image-studio/review`

远程生图请求必须携带 `confirm_billable=true`。Web 页面在发起请求前会显示确认框，Router 在生成函数内部再次校验，因此不能通过绕过前端直接触发未确认的计费调用。

## 输出

角色定妆板：

`projects/<project>/lookdev/image-studio/character-bible/`

镜头关键帧：

`projects/<project>/lookdev/image-studio/keyframes/`

每张 PNG 都有同名 JSON metadata，记录 Provider、model、角色/镜头 ID、prompt 和 `review_status`。

初始人工审核状态始终为 `PENDING`，技术生成成功不会自动改成 APPROVED。

## 角色锁

当前首个角色为 `CHAR-CHILD-001`，视觉锁来自 `STYLE-REF-GUOFENG-DIALOGUE-001`：

- 明确幼态小女孩；
- 黑棕双髻、自然刘海、侧发；
- 青色发带与克制金饰；
- 浅青 + 象牙白多层汉服；
- 柔软动漫脸和大而有层次的眼睛；
- 禁止成年女性体态；
- 禁止低模玩具/吉祥物读感。

## 测试与零扣费约束

`tests/test_image_provider_router.py` 只测试纯路由策略；`tests/test_image_studio.py` 的生成与 Web API 测试会 mock `OpenAIImageProvider.generate`，只启动本机临时 HTTP 服务，不访问真实 OpenAI 图片接口，也不会产生远程费用。

## 下一步

角色定妆板人工 APPROVED 后，镜头关键帧继续沿用同一角色视觉锁。下一阶段再把 APPROVED keyframe 作为 image-to-video / motion provider 的输入。
