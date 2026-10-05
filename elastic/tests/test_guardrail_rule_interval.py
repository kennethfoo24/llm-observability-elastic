import re
from pathlib import Path

from elastic.rules.guardrail_detection import rule_body


def test_ui_detection_interval_matches_the_rule():
    copy = (Path(__file__).resolve().parents[2] / "frontend/src/lib/copy.ts").read_text()
    minutes = int(re.search(r"DETECTION_INTERVAL_MINUTES = (\d+)", copy).group(1))
    assert rule_body()["interval"] == f"{minutes}m"
    assert rule_body()["rule_id"] == "glassbox-flagged-prompts"
