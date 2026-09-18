# ArcReel 独立工作台接入方案

## 定位

VideoCreator Engine 继续保存《镜花缘》的 IP、剧本、角色、场景、分镜、音频、版本与验收主数据。ArcReel 作为可选的独立服务，用于补充异步任务队列、模型调度、成本统计、失败恢复和剪映草稿导出。

```text
VideoCreator Web / 项目仓库（主数据）
              |
              | HTTP Adapter
              v
       ArcReel 独立服务
              |
              +-- 图片 / 视频 Provider
              +-- 异步任务与成本记录
              +-- FFmpeg / 剪映导出
```

不复制 ArcReel 源码、不把它的项目结构设为本项目的主数据，也不让 ArcReel 自动发布内容。这样可以独立升级、停用或更换服务，并保留现有的本地动态分镜主链路。

## 当前接入面

- `GET /health`：连接检测。
- `GET /api/v1/auth/status`：确认服务认证状态。
- `GET/POST /api/v1/projects`：读取或建立镜像项目。
- `GET /api/v1/projects/{name}/workflow-status`：读取工作流状态。
- `GET /api/v1/projects/{name}/tasks`：读取异步任务。
- `POST /api/v1/projects/{name}/generate/storyboard/{segment_id}`：提交分镜任务。
- `POST /api/v1/projects/{name}/generate/video/{segment_id}`：提交可选的视频增强任务。

适配器位于 `adapters/workspaces/arcreel.py`。Web 设置页可以填写独立服务地址及可选访问令牌；两者仅保存在当前服务进程内。也可以使用 `ARCREEL_BASE_URL` 和 `ARCREEL_API_KEY` 环境变量。

## 数据映射

| VideoCreator | ArcReel | 规则 |
| --- | --- | --- |
| `jinghua-yuan-series` | project name | 固定一对一镜像 |
| `S01E001` | script / segment group | 集号保持不变 |
| `S01E001-SC001-SH001` | segment id | 保留稳定镜头 ID |
| Scene JSON prompt | generation prompt | 只发送任务所需内容 |
| 资产版本 ID | 输入文件元数据 | 输出继续回登记到本项目 |

首个同步动作必须由人工触发。远程模型调用仍需单独确认费用；令牌、私有素材和未批准底本不能自动同步。

## 许可边界

ArcReel 使用 AGPL-3.0，并在 `NOTICE` 中要求界面保留可见的 `Powered by ArcReel — https://github.com/ArcReel/ArcReel` 署名和仓库链接。Web 集成卡已保留该署名。若以后分发修改后的 ArcReel 或将其网络服务对外提供，需要按其 AGPL-3.0 与 `NOTICE` 条款处理源代码和署名义务。

官方仓库：https://github.com/ArcReel/ArcReel

## 本地部署状态

- 运行版本：ArcReel `0.30.0`。
- 镜像摘要：`sha256:d56db7fdbebc8a8c13b46a44956707e5bbb0b6052fa324061ac3bc3769aedd63`。
- 地址：`http://127.0.0.1:1241`，只绑定本机回环地址。
- Compose：`integrations/arcreel/compose.yml`。
- 数据目录：`integrations/arcreel/data/`，不纳入 Git。
- 镜像项目：`jinghua-yuan-series`，内容模式 `drama`，来源类型 `novel`，生成模式 `storyboard`，画幅 `9:16`。
- 已将本地公开底本 `jinghua-yuan-first-five-wikisource.txt`（13,899 字符）复制到本机侧车；工作流进入 `ASSET_INVENTORY`。
- 当前任务数为 0，没有配置或调用收费 Provider。
- 当前运行策略：`PAUSED`。容器已停止，数据和固定镜像保留；VideoCreator Web 不再探测服务，并明确显示“已暂停”。

可重复执行的元数据镜像检查：

```bash
python3 scripts/arcreel_mirror.py projects/jinghua-yuan-series
```

默认命令只确保 ArcReel 镜像项目存在，并检查五集、15 个稳定镜头 ID、工作流和任务状态，不会复制底本或启动生成。添加 `--sync-source` 时，只把项目中的单个 `.txt` 底本复制到本机 ArcReel 数据目录，仍不会调用 AI。
