# VideoCreator Web 启动与重启

> 适用项目：VideoCreator Engine  
> 默认服务：`scripts/web_server.py`  
> 默认地址：`http://127.0.0.1:18765`

## 1. 推荐用法

在项目根目录执行：

```bash
./start-web.command
```

启动成功后会输出：

```text
PASS Web started
URL  http://127.0.0.1:18765
PID  <pid>
LOG  <project>/logs/web-server.log
```

需要重启时执行：

```bash
./restart-web.command
```

重启脚本会：

1. 优先读取 `cache/web-server.pid`。
2. 只停止当前 VideoCreator Engine 自己的 `scripts/web_server.py` 进程。
3. 等待正常退出；必要时才强制结束。
4. 再调用 `start-web.command`。
5. 不会按名称批量结束其他 Python 服务。

## 2. 脚本位置

```text
start-web.command
restart-web.command
scripts/web_server.py
logs/web-server.log
cache/web-server.pid
```

其中：

- `logs/web-server.log` 保存后台 Web 日志。
- `cache/web-server.pid` 保存当前由脚本管理的 Web PID。
- `logs/` 和 `cache/` 已属于运行时目录，不应提交具体日志或 PID。

## 3. 重复启动保护

再次运行：

```bash
./start-web.command
```

如果 Web 已经正常运行，脚本不会再启动第二份进程，而是直接返回当前 URL、PID 和日志位置。

如果默认端口 `18765` 被其他程序占用，脚本会失败并明确提示，不会自动杀掉占用端口的其他服务。

## 4. 修改端口

临时改成 `8877`：

```bash
VIDEO_CREATOR_WEB_PORT=8877 ./start-web.command
```

重启同一个自定义端口时同样传入：

```bash
VIDEO_CREATOR_WEB_PORT=8877 ./restart-web.command
```

默认值：

```text
VIDEO_CREATOR_WEB_HOST=127.0.0.1
VIDEO_CREATOR_WEB_PORT=18765
VIDEO_CREATOR_PYTHON=python3
```

如需指定 Python：

```bash
VIDEO_CREATOR_PYTHON=/opt/homebrew/bin/python3 ./start-web.command
```

## 5. 查看日志

```bash
tail -f logs/web-server.log
```

只看最后 100 行：

```bash
tail -n 100 logs/web-server.log
```

启动失败时，`start-web.command` 会自动输出日志尾部，通常不需要先手工查日志。

## 6. 检查 Web 是否启动

浏览器打开：

```text
http://127.0.0.1:18765
```

也可以：

```bash
curl -I http://127.0.0.1:18765
```

脚本启动时本身会使用 HTTP 请求做健康检查，因此出现 `PASS Web started` 后才表示 Web 已经可以访问。

## 7. Finder 双击

两个文件都是 macOS 可执行 `.command`：

```text
start-web.command
restart-web.command
```

Git 已保存 executable bit。克隆仓库后通常可以直接双击；如果 macOS 本地权限被外部工具改坏，可恢复：

```bash
chmod +x start-web.command restart-web.command
```

## 8. 为什么不用 pkill

不要使用：

```bash
pkill -f web_server.py
pkill -f python
```

因为可能误杀其他项目或本机服务。

本项目脚本使用 PID、端口和项目路径三重识别，只管理当前仓库自己的 Web 服务。

## 9. 当前边界

这些脚本只负责 **本机 Web Console 的进程生命周期**：

```text
start
restart
health check
PID
log
single-instance protection
```

它们不会：

- 启动远程 AI Provider。
- 自动配置 API Key。
- 启动 ArcReel。
- 自动发布视频。
- 改变 P28 人工审核状态。

Web 中涉及远程 Provider 的动作仍受现有上传授权、计费确认和人工发布门控制。

## 10. Python / Pillow 架构隔离

Web 启动器不会再直接使用用户目录中的 Python 包。它会在项目根目录创建：

```text
.venv-web/
```

Apple Silicon Mac 会优先选择原生 arm64 Python（优先 `/opt/homebrew/bin/python3`），并在独立环境中安装 `requirements-web.txt`。因此即使 `~/Library/Python/.../site-packages` 中存在旧的 x86_64/arm64 混装 Pillow，也不会再污染 Web 进程。

首次启动可能出现：

```text
RUN  Create isolated Web Python environment
RUN  Install Web Python dependencies
```

之后依赖文件没有变化时不会重复安装。

环境安装日志：

```text
logs/web-env.log
```

如果曾经手工创建过错误架构的 `.venv-web`，启动器在 Apple Silicon 上检测到非 arm64 后会自动删除并重建。

`VIDEO_CREATOR_PYTHON` 现在表示“创建 Web venv 使用的基础 Python”。Apple Silicon 上显式指定的 Python 也必须是 arm64，否则启动器直接失败，避免再次出现 `_imaging ... incompatible architecture`。

## 11. 找不到 arm64 Python 时自动修复

在 Apple Silicon Mac 上，如果系统 PATH 中只有 Rosetta/x86_64 Python，`start-web.command` 会先扫描原生 Homebrew 常见路径。

如果仍找不到，并且存在：

```text
/opt/homebrew/bin/brew
```

脚本会自动执行原生架构的 Homebrew Python 安装：

```bash
arch -arm64 /opt/homebrew/bin/brew install python
```

安装完成后继续自动创建 `.venv-web`，不需要再次手工运行安装命令。

如不希望启动脚本自动安装 Python，可临时关闭：

```bash
VIDEO_CREATOR_AUTO_INSTALL_PYTHON=0 ./start-web.command
```

此时缺少 arm64 Python 会直接失败并给出明确提示。

如果本机没有 `/opt/homebrew/bin/brew`，脚本不会尝试使用可能是 Intel 架构的 `/usr/local/bin/brew` 来创建 Web 环境，避免再次混入 x86_64 依赖。
