import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.envfile import parse_env_text, to_app_env  # noqa: E402

root = Path(__file__).resolve().parent.parent
src = root / "elasticsearch.txt"
if not src.is_file():
    sys.exit(f"error: {src} not found; create it with the Elastic deployment endpoints and keys first")
env = to_app_env(parse_env_text(src.read_text()))
dest = root / "backend" / ".env"
# 0600 from creation; fchmod also tightens a pre-existing file that was created with looser bits.
fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("".join(f"{k}={v}\n" for k, v in env.items()))
print("wrote backend/.env (mode 600) with keys:", ", ".join(sorted(env)))
