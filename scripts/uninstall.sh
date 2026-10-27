#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $# != 0 ]]; then printf 'Usage: bash scripts/uninstall.sh\n' >&2; exit 2; fi
[[ $(uname -s) == Linux && $(id -u) != 0 ]] || { printf 'Run as the ordinary Linux VM user.\n' >&2; exit 1; }
launcher="$HOME/.local/bin/phone-vm-proxy"
[[ -f "$launcher" ]] && grep -qF "Forward an Android phone's HTTP proxy" "$launcher" || {
  printf 'Managed launcher not found; no files changed.\n' >&2; exit 1;
}
systemctl --user disable --now android-vm-proxy.service
python3 "$launcher" cleanup
rm -- "$launcher" "$HOME/.config/systemd/user/android-vm-proxy.service"
systemctl --user daemon-reload
printf '%s\n' 'Removed proxy forwarding integration. Private config/env.sh retained.' \
  'Remove proxy entries from T3 service.env and your shell startup files if you added them; restart affected processes.'
