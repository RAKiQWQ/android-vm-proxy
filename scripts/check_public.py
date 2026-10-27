#!/usr/bin/env python3
"""Check the complete public source allowlist for accidental private material."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    ".gitattributes", ".gitignore", ".github/workflows/check.yml", "LICENSE",
    "README.md", "README.en.md", "install.sh", "scripts/uninstall.sh",
    "scripts/check_public.py", "src/phone_vm_proxy.py", "tests/test_phone_vm_proxy.py",
    "systemd/android-vm-proxy.service",
}
IGNORED = {".git", "__pycache__", ".venv", "dist"}
PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(rb"\bgh[opusr]_[A-Za-z0-9]{24,}\b"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),
    re.compile(rb"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9_.-]+[\\/]"),
]


def check() -> None:
    found = set()
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in IGNORED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("Unexpected symlink: " + str(relative))
        if path.is_dir():
            continue
        name = relative.as_posix()
        if name not in FILES:
            raise ValueError("Unexpected public file: " + name)
        data = path.read_bytes()
        if b"\0" in data or any(pattern.search(data) for pattern in PATTERNS):
            raise ValueError("Possible private or binary material: " + name)
        found.add(name)
    if FILES != found:
        raise ValueError("Missing public files: " + ", ".join(sorted(FILES - found)))
    print("Public source check passed:", len(found), "files")


if __name__ == "__main__":
    check()
