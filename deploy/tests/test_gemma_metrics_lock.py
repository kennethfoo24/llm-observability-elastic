import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gemma_metrics_lock", ROOT / "deploy" / "scripts" / "gemma_metrics_lock.py")
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)

HASH = "$2y$10$" + "a" * 53
FAKE = """#!/bin/bash
LLM_HOSTNAME=llm.example.test
docker run -d --name vllm --network llm-net vllm/vllm-openai --api-key FAKEKEY
cat > /etc/caddy/Caddyfile <<EOF
${LLM_HOSTNAME} {
    reverse_proxy vllm:8000
}
EOF
docker run -d --name caddy caddy:2
"""


def test_adds_basic_auth_for_metrics_only():
    out = lock.lock_script(FAKE, HASH)
    assert "@metrics path /metrics" in out and "basic_auth @metrics {" in out
    assert "reverse_proxy vllm:8000" in out and "${LLM_HOSTNAME} {" in out
    assert out.count("basic_auth") == 1
    assert out.startswith(FAKE.split("cat > /etc/caddy")[0]) and out.endswith("docker run -d --name caddy caddy:2\n")


def test_hash_dollars_are_escaped_for_the_unquoted_heredoc():
    out = lock.lock_script(FAKE, HASH)
    assert "metrics \\$2y\\$10\\$" in out
    assert not re.search(r"(?<!\\)\$2y", out)


def test_idempotent_and_replaces_previous_hash():
    once = lock.lock_script(FAKE, HASH)
    assert lock.lock_script(once, HASH) == once
    other = "$2y$10$" + "b" * 53
    twice = lock.lock_script(once, other)
    assert twice.count("basic_auth") == 1 and "bbbb" in twice and "aaaa" not in twice
    assert lock.is_locked(twice) and not lock.is_locked(FAKE)


def test_fails_loudly_without_caddy_block():
    with pytest.raises(lock.LockError):
        lock.lock_script("#!/bin/bash\necho hi\n", HASH)
    with pytest.raises(lock.LockError):
        lock.lock_script(FAKE.replace("reverse_proxy vllm:8000", "respond ok"), HASH)


def test_rejects_non_bcrypt_hash():
    with pytest.raises(lock.LockError):
        lock.lock_script(FAKE, "plaintext")


def test_no_secret_printing_in_source():
    src = (ROOT / "deploy" / "scripts" / "gemma_metrics_lock.py").read_text()
    assert "print(new" not in src and "print(live" not in src
