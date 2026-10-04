import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.envfile import parse_env_text, to_app_env  # noqa: E402

root = Path(__file__).resolve().parent.parent
env = to_app_env(parse_env_text((root / "elasticsearch.txt").read_text()))
(root / "backend" / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
print("wrote backend/.env with keys:", ", ".join(sorted(env)))
