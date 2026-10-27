# Android VM Proxy

[English](README.en.md)

让 Android 自带 Linux Terminal 中的 CLI 显式使用手机已有的 HTTP 代理。通过同机无线 ADB，将手机的回环代理端口转发到 VM，再为需要联网的进程设置代理环境变量。无需 Android Root，也无需在 VM 中另装代理内核。

这是 [T3 Code on Android as an Agent](https://github.com/RAKiQWQ/t3-code-on-android-as-an-agent) 的独立可选配套项目，也可以单独使用。它只维护出站代理转发，不管理 T3 入口、登录回调或 SSH。

## 为什么需要它

在 Pixel 9a / GrapheneOS / Android 17 的实测中，手机 VPN 已连接，但 Linux VM 的出站路径仍未进入该 VPN。仅看手机状态栏，或把 Terminal 加入按应用 VPN，并不能证明 VM 已使用同一路径。

解决方式是复用手机代理客户端提供的 HTTP 或混合代理入口：VM 中的程序连接 `http://127.0.0.1:18080`，ADB 将连接送到手机的 `127.0.0.1:10808`，后续出站由手机代理客户端处理。`10808` 是原始实测端口，安装时请替换为自己的 HTTP／混合端口。

## 安装与使用

以下命令在手机 Linux Terminal 的 Debian VM 中，以普通用户执行。需要手机已开启无线调试，代理客户端已启动，并提供可用的 HTTP CONNECT 代理；纯 VPN 或纯 SOCKS 入口不满足此条件。手机代理可保持仅监听回环地址，无需开启局域网共享。ADB 使用默认的本机 `5037` 服务，不要用 `adb -a` 启动它。

### 1. 安装

```bash
sudo apt-get update
sudo apt-get install -y adb python3 iproute2 curl git
git clone https://github.com/RAKiQWQ/android-vm-proxy.git
cd android-vm-proxy
bash install.sh
export PATH="$HOME/.local/bin:$PATH"
```

安装器只安装命令、私有配置和 systemd 用户服务。Python 要求 3.10+。它不会编辑 T3、Shell 启动文件、手机 VPN 或路由；新安装的服务需要在配置后手动启用。

### 2. 配对与配置

在“开发者选项 → 无线调试 → 使用配对码配对设备”中查看**配对端口**，替换 `12345`，在 ADB 的本地提示中输入配对码：

```bash
phone-vm-proxy pair 12345
```

回到无线调试主页面，将 `54321` 替换为**连接端口**。将 `10808` 替换为手机代理的 HTTP／混合端口：

```bash
phone-vm-proxy configure 54321 --phone-port 10808 --vm-port 18080
systemctl --user enable --now android-vm-proxy.service
journalctl --user -u android-vm-proxy.service -n 20
```

默认使用 VM 的 IPv4 网关作为手机地址。若该路径不可用，在 `pair` 和 `configure` 上都添加 `--host 手机地址`。已在同一 VM 内配对过的手机可以跳过 `pair`；无需重新创建配对密钥。

服务每 12 秒检查连接及转发，ADB 暂时断开后会重连。`Forward configured` 仅表示映射建立且 VM 监听地址检查通过，仍需下一步测试代理是否可用。它使用 `adb forward --no-rebind`，遇到其他映射或监听占用端口会报错，不会替换它们。若新建的监听不是回环地址，会移除该映射并报错。

### 3. 在实际运行 CLI 的 Shell 中启用并验证

```bash
source "$HOME/.config/android-vm-proxy/env.sh"
curl --fail --head --noproxy '' --proxy http://127.0.0.1:18080 \
  --connect-timeout 10 --max-time 30 https://example.com/
```

HTTPS 请求通过后，再从这个 Shell 启动需要联网的 CLI。`HTTPS_PROXY` 的值仍以 `http://` 开头，表示通过 HTTP 代理建立 CONNECT 隧道；它不关闭目标站点的 TLS 验证。修改 VM 端口后，测试命令中的端口也要更新。

生成的配置保存在 `~/.config/android-vm-proxy/`。`env.sh` 设置大小写两套 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`，并用 `NO_PROXY=localhost,127.0.0.1,::1` 保持本地入口和登录回调直连。需要每个新 Shell 自动启用时，可自行将上面的 `source` 行加入 `~/.bashrc`。

### 4. 为 T3 的后台进程启用

```bash
phone-vm-proxy env
```

将输出的 8 项 `KEY=VALUE` 添加或更新到 T3 的 `~/.t3/service.env`（使用自定义 T3 home 时，选择对应文件），保留其他设置，同名变量只留一条。然后在任务空闲时执行：

```bash
t3 service restart
```

T3 后台服务不会自动继承当前终端中新设置的变量。已经运行的 CLI、提供方进程和 tmux pane 也需要分别重新加载或重启；只新开一个 tmux 窗口可能仍继承旧环境。环境文件的规则见 [T3 官方说明](https://github.com/pingdotgg/t3code/blob/main/docs/user/background-service.md#configure-the-service-environment)。

## 维护与排障

无线调试连接端口变化后，停止服务、更新配置并重新启动；未指定的选项保留原值：

```bash
systemctl --user stop android-vm-proxy.service
phone-vm-proxy configure 54321
systemctl --user start android-vm-proxy.service
```

检查连接、映射和监听：

```bash
adb -H 127.0.0.1 -P 5037 devices
adb -H 127.0.0.1 -P 5037 forward --list
ss -ltn 'sport = :18080'
journalctl --user -u android-vm-proxy.service -n 30
```

VM 的 `18080` 应只监听在 `127.0.0.1`／`::1`。不要把它加入 Terminal 的 Port control。端口被占用时可停止服务后用 `phone-vm-proxy configure 54321 --vm-port 18081` 更换，再重新加载 Shell 和 T3 的环境；不要清空全部 ADB 映射。更换手机网关后若残留旧映射，先用 `forward --list` 核对旧设备和端口，再按 ADB 官方命令移除对应单条映射。

映射正常但 `curl` 失败时，检查手机代理是否仍在运行、端口是否支持 HTTP CONNECT，以及代理自身的出站连接。浏览器登录回调能到达 CLI，与 VM 能否完成联网请求是不同环节；本项目仅处理出站代理，手机回调入口由 T3 手机部署项目维护。

早期实测使用的 `phone-link.service` 同时管理代理、T3 等转发。安装器检测到它会退出；应先手动迁移和归档，避免两个控制器争用同一代理端口。当前精简版 `android-local-agent-link.service` 只维护反向转发，可与本项目配合使用。

## 卸载

```bash
bash scripts/uninstall.sh
```

卸载会停止并删除本项目的服务和命令，只移除与配置中设备、VM 端口和手机端口完全匹配的正向映射。ADB 配对、手机代理、其他映射及私有配置会保留。若清理失败，命令会保留以便重试。

同时删除或恢复你在 T3 `service.env` 和 Shell 启动文件中手动添加的代理设置，并重启相关进程。关闭当前 Shell 的这组设置可执行（若原来有其他代理，应恢复原值）：

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy NO_PROXY no_proxy
```

## 实践依据

原始方案于 2026-10-26 在 Pixel 9a、GrapheneOS `2026102100` / Android 17、Debian 13 ARM64、手机 v2rayNG 代理环境中实测。VM 经同机无线 ADB 转发复用了手机本地代理，认证发现接口返回 HTTP 200，随后 Codex CLI `0.164.0` 完成登录。后续修复了 tmux 重建后未继承代理环境的问题。

## 局限性

- 本仓库是从上述实践中拆出的独立实现，尚未在全新手机 VM 中重新实装验收。自动检查不能替代真机验证。
- 只有遵循代理设置的程序会使用这条路径。它不会接管整个 VM 的 VPN、UDP 或任意 DNS 流量，也不提供系统级断网保护；清除变量或不支持代理的程序仍可能直连。
- 手机代理必须提供无需认证的本地 HTTP CONNECT 或混合入口。其他 VPN 客户端、ROM、设备与提供方需要分别验证。
- Terminal 被系统终止后台运行、VM 停止、无线调试关闭或手机代理停止，都会影响这条链路。systemd 不能让已停止的 VM 继续运行。
- 配对链接、ADB 私钥、代理订阅和账号认证文件不应提交到仓库或 Issue。本项目不收集这些数据。

## 检查与许可

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n scripts/uninstall.sh
bash install.sh --dry-run
python3 scripts/check_public.py
```

自有代码与文档采用 [MIT](LICENSE)，仅使用 Python 标准库和现成的 ADB 命令。转发与配对参数参考 [ADB 官方手册](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/user/adb.1.md)；回环绑定行为参考 [ADB socket 实现](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/socket_spec.cpp)。第三方代理客户端和服务适用各自许可与条款。
