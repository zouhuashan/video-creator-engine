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

Web 启动器不会直接使用用户目录中的 Python 包，也不再依赖 `venv/ensurepip`。

当前方式：

```text
/opt/homebrew/bin/python3   # 原生 arm64 Python
.web-python/                # 项目私有第三方依赖目录
requirements-web.txt        # Web 最小 Python 依赖
```

启动器用基础 Python 自带的 `pip` 将依赖安装到 `.web-python/`：

```bash
python3 -m pip install --target .web-python -r requirements-web.txt
```

Web 运行时使用：

```text
PYTHONNOUSERSITE=1
PYTHONPATH=<project>/.web-python
```

因此 `~/Library/Python/.../site-packages` 中旧的 x86_64/arm64 混装包不会进入 Web 进程。

第一次成功启动通常会显示：

```text
RUN  Install Web Python dependencies
PASS Web started
PY   /opt/homebrew/bin/python3 (arm64)
DEPS <project>/.web-python
```

之前脚本创建过的 `.venv-web/` 属于旧方案；新版启动器发现后会自动删除。

环境安装日志：

```text
logs/web-env.log
```

## 11. 找不到 arm64 Python 时自动修复

Apple Silicon Mac 会优先扫描：

```text
/opt/homebrew/bin/python3
/opt/homebrew/opt/python/bin/python3
/opt/homebrew/opt/python@3.14/bin/python3.14
/opt/homebrew/opt/python@3.13/bin/python3.13
/opt/homebrew/opt/python@3.12/bin/python3.12
```

如果仍找不到，并且存在原生 Homebrew：

```text
/opt/homebrew/bin/brew
```

脚本会自动执行：

```bash
arch -arm64 /opt/homebrew/bin/brew install python
```

安装完成后继续安装项目私有 Web 依赖，不创建 venv，因此不会触发 `ensurepip`。

如果不希望自动安装 Python：

```bash
VIDEO_CREATOR_AUTO_INSTALL_PYTHON=0 ./start-web.command
```

如果显式指定基础 Python：

```bash
VIDEO_CREATOR_PYTHON=/opt/homebrew/bin/python3 ./start-web.command
```

Apple Silicon 上该解释器必须实际报告 `arm64`。

## 12. pip truststore 兼容

在部分 macOS 26 + Homebrew Python 3.14 + pip 26.x 组合上，pip 的 truststore 后端可能无法读取系统版本，表现为：

```text
ValueError: invalid literal for int() with base 10: ''
```

Web 启动器安装项目私有依赖时固定增加：

```text
--use-deprecated=legacy-certs
```

这会让 pip 绕过 truststore 系统证书后端，继续使用兼容的证书校验路径；不会修改 macOS Keychain，也不会关闭 HTTPS 校验。

## 13. macOS 26 版本探测兼容

某些 macOS 26 环境中，Python 的 `platform.mac_ver()` 可能返回空字符串。pip 的 truststore 与 packaging wheel 标签计算都会把该值当数字解析，从而报：

```text
ValueError: invalid literal for int() with base 10: ''
```

项目提供：

```text
support/web-python/sitecustomize.py
```

它只在 Python 无法得到 macOS 版本时调用：

```bash
/usr/bin/sw_vers -productVersion
```

并把该真实版本提供给当前 Python 进程。不会修改系统文件，也不会硬编码具体 macOS 版本。

启动器在安装依赖、环境自检和 Web 服务运行时统一加载这层兼容逻辑。

## 14. pip 只下载 wheel，项目自行安装

在当前 Homebrew Python 3.14 + pip 26.2.1 环境中，Pillow wheel 可以正常解析和下载，但 pip 的安装阶段可能报：

```text
ImportError: No module named 'pip._internal.operations.install.wheel'
```

因此启动器只让 pip 做它当前已经验证正常的部分：

```text
版本解析 -> 平台匹配 -> 下载 arm64 wheel
```

下载目录：

```text
cache/web-wheels/
```

随后由：

```text
support/web-python/install_wheels.py
```

使用 Python 标准库 `zipfile` 将 wheel 安装到：

```text
.web-python/
```

因此 Web 依赖安装不再调用 pip 的内部 wheel installer。
