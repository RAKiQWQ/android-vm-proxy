#!/usr/bin/env bash
set -Eeuo pipefail
project_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [[ $# == 1 && $1 == --dry-run ]]; then
  printf '%s\n' 'Install phone-vm-proxy, private config/env.sh and an inactive systemd user service.' \
    'Requires Linux, Python >=3.10, adb, ip, ss and systemd user services.' \
    'Pair, configure and enable the service manually. T3 and shell startup files are not edited.'
  exit 0
fi
if [[ $# != 0 ]]; then printf 'Usage: bash install.sh [--dry-run]\n' >&2; exit 2; fi
[[ $(uname -s) == Linux && $(id -u) != 0 ]] || { printf 'Run as the ordinary Android Linux VM user.\n' >&2; exit 1; }
for tool in python3 adb ip ss systemctl; do
  command -v "$tool" >/dev/null || { printf 'Missing prerequisite: %s\n' "$tool" >&2; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python >=3.10 required"'
systemctl --user show-environment >/dev/null
if [[ -e "$HOME/.config/systemd/user/phone-link.service" ]] || systemctl --user is-active --quiet phone-link.service; then
  printf 'Archive the old combined phone-link controller before installing this standalone service.\n' >&2; exit 1
fi
launcher="$HOME/.local/bin/phone-vm-proxy"
if [[ -e "$launcher" ]] && ! grep -qF "Forward an Android phone's HTTP proxy" "$launcher"; then
  printf 'A different phone-vm-proxy already exists.\n' >&2; exit 1
fi
config_dir="$HOME/.config/android-vm-proxy"
install -d -m 700 "$config_dir"
python3 - "$project_dir/src" "$config_dir" <<'PY'
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from phone_vm_proxy import Config, read_config, save_config
directory = Path(sys.argv[2])
config = read_config(directory) if (directory / 'config.json').exists() else Config()
save_config(directory, config)
PY
install -d -m 755 "$HOME/.local/bin" "$HOME/.config/systemd/user"
install -m 755 "$project_dir/src/phone_vm_proxy.py" "$launcher"
install -m 644 "$project_dir/systemd/android-vm-proxy.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
printf '%s\n' 'Installed. Pair and configure, then enable android-vm-proxy.service; see README.md.'
