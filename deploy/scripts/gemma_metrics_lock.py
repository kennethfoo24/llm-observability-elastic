#!/usr/bin/env python3
"""Password-protect the Gemma VM's vLLM /metrics path (Caddy basic_auth) or restore the original startup script.

  gemma_metrics_lock.py apply     read backend/secrets/gemma_metrics_password.txt (generated if missing), bcrypt it
                                  with `htpasswd`, add basic_auth for ONLY /metrics to the Caddyfile section of the
                                  VM startup script and set the `startup-script` metadata key.
  gemma_metrics_lock.py restore   put backend/secrets/gemma_startup_script.orig back.
  gemma_metrics_lock.py status    say whether the live script is locked (read-only).

The original script is saved (mode 600, gitignored) before the first change. Neither the script, the password
nor the hash is ever printed. DRY_RUN=1 builds the new script and stops before writing metadata.
The VM only reads the startup script at boot: the change takes effect on the next start.
"""
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ID = "elastic-sa"
VM = "kenneth-gemma-llm"
VM_ZONE = "asia-southeast1-c"
USER = "metrics"
ROOT = Path(__file__).resolve().parents[2]
PASSWORD_FILE = ROOT / "backend" / "secrets" / "gemma_metrics_password.txt"
ORIG_FILE = ROOT / "backend" / "secrets" / "gemma_startup_script.orig"

_BLOCK = re.compile(r"^(?P<head>[^\n]*\{[ \t]*)\n(?P<body>(?:[^\n]*\n)*?)\}[ \t]*\n(?=EOF\n)", re.M)
_OLD_AUTH = re.compile(r"    @metrics path /metrics\n    basic_auth @metrics \{\n[^\n]*\n    \}\n")


class LockError(Exception):
    pass


def lock_script(script: str, bcrypt_hash: str) -> str:
    """Pure transform. Add basic_auth for /metrics only to the Caddyfile heredoc; replaces a previous lock."""
    if not re.fullmatch(r"\$2[abxy]\$\d\d\$[./A-Za-z0-9]{53}", bcrypt_hash):
        raise LockError("not a bcrypt hash")
    start = script.find("/etc/caddy/Caddyfile <<EOF\n")
    if start < 0:
        raise LockError("Caddyfile heredoc not found in the startup script")
    m = _BLOCK.search(script, start)
    if not m or "reverse_proxy" not in m.group("body"):
        raise LockError("Caddy site block with reverse_proxy not found")
    body = _OLD_AUTH.sub("", m.group("body"))
    # The heredoc is unquoted, so the shell would expand every `$` in the hash: escape them.
    esc = bcrypt_hash.replace("$", "\\$")
    auth = f"    @metrics path /metrics\n    basic_auth @metrics {{\n        {USER} {esc}\n    }}\n"
    return script[:m.start("body")] + auth + body + script[m.end("body"):]


def is_locked(script: str) -> bool:
    return "@metrics path /metrics" in script and "basic_auth @metrics" in script


def _gcloud(*args: str, capture: bool = True) -> str:
    r = subprocess.run(["gcloud", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"gcloud failed: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
    return r.stdout


def _guard() -> None:
    p = _gcloud("config", "get-value", "project").strip()
    if p != PROJECT_ID:
        raise SystemExit(f"gcloud project is '{p}', expected {PROJECT_ID}")


def _live_script() -> str:
    out = _gcloud("compute", "instances", "describe", VM, f"--zone={VM_ZONE}", f"--project={PROJECT_ID}",
                  "--format=value(metadata.items.filter(key:startup-script).extract(value).flatten())")
    return out[:-1] if out.endswith("\n") else out


def _set_script(text: str, dry: bool) -> None:
    if dry:
        print("[dry-run] would set the startup-script metadata (content not printed)")
        return
    fd, name = tempfile.mkstemp(prefix="gemma-startup.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(text)
        _gcloud("compute", "instances", "add-metadata", VM, f"--zone={VM_ZONE}", f"--project={PROJECT_ID}",
                f"--metadata-from-file=startup-script={name}")
    finally:
        os.unlink(name)
    print("startup-script metadata updated (takes effect on the next VM boot)")


def _password() -> str:
    if not PASSWORD_FILE.is_file() or not PASSWORD_FILE.read_text().strip():
        fd = os.open(PASSWORD_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(24) + "\n")
        print(f"generated {PASSWORD_FILE.relative_to(ROOT)} (never printed)")
    return PASSWORD_FILE.read_text().strip()


def hash_password(pw: str) -> str:
    """bcrypt via `htpasswd -niB` (password on stdin, not argv); output is `user:$2y$...`."""
    r = subprocess.run(["htpasswd", "-niB", "-C", "10", USER], input=pw + "\n", capture_output=True, text=True)
    if r.returncode != 0 or ":" not in r.stdout:
        raise SystemExit("htpasswd failed (is it installed?)")
    return r.stdout.strip().split(":", 1)[1]


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    dry = os.environ.get("DRY_RUN", "0")
    if dry not in ("0", "1"):
        raise SystemExit("DRY_RUN must be 0 or 1")
    _guard()
    if cmd == "status":
        print("locked" if is_locked(_live_script()) else "open")
        return 0
    if cmd == "apply":
        live = _live_script()
        if not live:
            raise SystemExit("startup-script metadata not readable")
        if not ORIG_FILE.exists() and not is_locked(live):
            fd = os.open(ORIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(live)
            print(f"saved the original script to {ORIG_FILE.relative_to(ROOT)}")
        elif not ORIG_FILE.exists():
            raise SystemExit("live script is already locked and no .orig exists; refusing")
        new = lock_script(live, hash_password(_password()))
        _set_script(new, dry == "1")
        return 0
    if cmd == "restore":
        if not ORIG_FILE.is_file():
            raise SystemExit(f"{ORIG_FILE.relative_to(ROOT)} missing")
        _set_script(ORIG_FILE.read_text(), dry == "1")
        return 0
    raise SystemExit("usage: gemma_metrics_lock.py apply|restore|status")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
