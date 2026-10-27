# Android VM Proxy

[中文](README.md)

Let CLI processes inside Android's built-in Linux Terminal explicitly use an existing HTTP proxy on the phone. Same-phone wireless ADB forwards the phone's loopback proxy into the VM; proxy environment variables direct selected processes through it. No Android root or additional proxy core inside the VM is required.

This is an independent, optional companion to [Android Local Agent](https://github.com/RAKiQWQ/android-local-agent) and can also be used on its own. It maintains outbound proxy forwarding only; it does not manage T3 access, login callbacks, or SSH.

## Why it exists

On the tested Pixel 9a / GrapheneOS / Android 17 setup, the phone VPN was connected, but the Linux VM's outbound path did not enter that VPN. The phone's status bar, or including Terminal in per-app VPN settings, does not prove that VM traffic uses the same path.

The solution reuses the HTTP or mixed proxy listener provided by the phone's proxy client. VM programs connect to `http://127.0.0.1:18080`; ADB delivers the connection to the phone's `127.0.0.1:10808`, and the phone client handles outbound routing. `10808` was the port in the original test; replace it with your own HTTP or mixed listener port.

## Install and use

Run these commands as the ordinary user inside the phone's Debian Linux Terminal VM. Wireless debugging must be enabled, and the running phone proxy client must offer a working HTTP CONNECT listener. A VPN alone or a SOCKS-only listener does not meet this requirement. The phone proxy can remain on loopback; LAN sharing is unnecessary. Use the default local ADB server on `5037`; do not start it with `adb -a`.

### 1. Install

```bash
sudo apt-get update
sudo apt-get install -y adb python3 iproute2 curl git
git clone https://github.com/RAKiQWQ/android-vm-proxy.git
cd android-vm-proxy
bash install.sh
export PATH="$HOME/.local/bin:$PATH"
```

The installer adds the command, private configuration, and a systemd user service. Python 3.10+ is required. It does not edit T3, shell startup files, the phone VPN, or routing. A new service must be enabled manually after configuration.

### 2. Pair and configure

Open Developer options → Wireless debugging → Pair device with pairing code. Replace `12345` with the **pairing port** and enter the code at ADB's local prompt:

```bash
phone-vm-proxy pair 12345
```

Return to the main wireless debugging page and replace `54321` with the **connection port**. Replace `10808` with the phone proxy's HTTP or mixed listener port:

```bash
phone-vm-proxy configure 54321 --phone-port 10808 --vm-port 18080
systemctl --user enable --now android-vm-proxy.service
journalctl --user -u android-vm-proxy.service -n 20
```

The phone address defaults to the VM's IPv4 gateway. If that path is unavailable, add `--host PHONE_ADDRESS` to both `pair` and `configure`. Skip pairing if this VM already holds a valid pairing with this phone; new pairing keys are unnecessary.

The service checks the connection and forward every 12 seconds and reconnects after temporary ADB disconnections. `Forward configured` means the mapping exists and its VM listening addresses passed inspection; verify proxy access in the next step. It uses `adb forward --no-rebind` and reports conflicting mappings or listeners instead of replacing them. A newly created mapping is removed if its listener is not restricted to loopback.

### 3. Enable and verify in the shell that runs the CLI

```bash
source "$HOME/.config/android-vm-proxy/env.sh"
curl --fail --head --noproxy '' --proxy http://127.0.0.1:18080 \
  --connect-timeout 10 --max-time 30 https://example.com/
```

After the HTTPS request succeeds, launch your network-dependent CLI from this shell. The `http://` prefix in `HTTPS_PROXY` specifies an HTTP CONNECT proxy; it does not disable TLS verification for the destination. Update the test command if you change the VM port.

Generated settings live in `~/.config/android-vm-proxy/`. `env.sh` sets uppercase and lowercase `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY`. It uses `NO_PROXY=localhost,127.0.0.1,::1` to keep local endpoints and login callbacks direct. To enable it in every new shell, add the `source` line above to `~/.bashrc` yourself.

### 4. Enable it for T3 background processes

```bash
phone-vm-proxy env
```

Add or update the eight printed `KEY=VALUE` entries in T3's `~/.t3/service.env` (use the corresponding file for a custom T3 home). Preserve other settings and keep only one entry per key. Then, while tasks are idle, run:

```bash
t3 service restart
```

The T3 background service does not automatically inherit variables you just set in a terminal. Existing CLI processes, provider processes, and tmux panes also need their environment reloaded or their processes restarted. A new tmux window alone may still inherit the old environment. See the [official T3 environment documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/background-service.md#configure-the-service-environment).

## Maintenance and troubleshooting

When the wireless debugging connection port changes, stop the service, update the configuration, and start it again. Unspecified options retain their previous values:

```bash
systemctl --user stop android-vm-proxy.service
phone-vm-proxy configure 54321
systemctl --user start android-vm-proxy.service
```

Inspect connections, mappings, and listeners:

```bash
adb -H 127.0.0.1 -P 5037 devices
adb -H 127.0.0.1 -P 5037 forward --list
ss -ltn 'sport = :18080'
journalctl --user -u android-vm-proxy.service -n 30
```

VM port `18080` should listen only on `127.0.0.1` / `::1`. Do not add it to Terminal's Port control. If the port is occupied, stop the service and change it with `phone-vm-proxy configure 54321 --vm-port 18081`, then reload the shell and T3 environments. Do not remove all ADB mappings. If a changed phone gateway leaves an old mapping, inspect its device and ports with `forward --list`, then remove that individual mapping using the official ADB commands.

If the mapping exists but `curl` fails, check that the phone proxy is running, its port supports HTTP CONNECT, and its own outbound connection works. A browser callback reaching a CLI and the VM completing an outbound request are separate stages. This project handles outbound proxy access; phone callback forwarding belongs to the original Agent project.

The early deployment's `phone-link.service` managed proxy forwarding together with T3 and other forwards. This installer stops if it finds that controller; migrate and archive it manually first so two controllers do not compete for the proxy port. The current minimal `android-local-agent-link.service` manages reverse forwards only and can be used alongside this project.

## Uninstall

```bash
bash scripts/uninstall.sh
```

Uninstall stops and removes this project's service and command. It removes only the forward matching the configured device, VM port, and phone port. ADB pairing, the phone proxy, unrelated mappings, and private configuration are retained. If cleanup fails, the command is retained for retrying.

Also remove or restore the proxy entries you manually added to T3's `service.env` and shell startup files, then restart affected processes. Clear this set of variables in the current shell with the following command; restore your earlier values instead if you previously used another proxy:

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy NO_PROXY no_proxy
```

## Evidence

The original approach was tested on 2026-10-26 using a Pixel 9a, GrapheneOS `2026102100` / Android 17, Debian 13 ARM64, and a v2rayNG proxy on the phone. The VM reused the phone's local proxy through same-phone wireless ADB. An authentication discovery endpoint returned HTTP 200, and Codex CLI `0.164.0` subsequently signed in. A later fix addressed proxy environment variables being lost when tmux was recreated.

## Limitations

- This repository is a standalone implementation extracted from that deployment. It has not been installed and accepted in a fresh phone VM. Automated checks do not replace device testing.
- Only programs that honor the proxy settings use this path. It does not route the entire VM through a VPN, carry UDP or arbitrary DNS traffic, or provide a system-wide kill switch. Programs without proxy support or with variables cleared may connect directly.
- The phone proxy must provide an unauthenticated local HTTP CONNECT or mixed listener. Other VPN clients, ROMs, devices, and providers require separate verification.
- The system killing Terminal in the background, a stopped VM, disabled wireless debugging, or a stopped phone proxy affects this link. systemd cannot keep a stopped VM running.
- Keep pairing links, ADB private keys, proxy subscriptions, and account authentication files out of the repository and issues. This project does not collect them.

## Checks and license

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n scripts/uninstall.sh
bash install.sh --dry-run
python3 scripts/check_public.py
```

This project's code and documentation use [MIT](LICENSE), Python's standard library, and existing ADB commands. See the [official ADB manual](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/user/adb.1.md) for pairing and forwarding options and the [ADB socket implementation](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/socket_spec.cpp) for loopback binding behavior. Third-party proxy clients and services retain their own licenses and terms.
