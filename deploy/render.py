"""Render deploy manifests: replace ${KEY} placeholders from --set KEY=VALUE (stdlib only).

Fails (exit 2) if any placeholder is left unreplaced or a --set value is malformed.
Refuses to render a Secret object, so literal secret values can never flow through here.
Only the placeholder NAMES appear in error messages, never values.
"""
import argparse
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
SECRET_KIND = re.compile(r"^kind:\s*Secret\s*$", re.MULTILINE)


def render_text(text: str, values: dict[str, str], name: str = "<input>") -> str:
    if SECRET_KIND.search(text):
        raise ValueError(f"{name}: refusing to render a Secret object")
    missing = sorted({m for m in PLACEHOLDER.findall(text) if m not in values})
    if missing:
        raise ValueError(f"{name}: missing values for {', '.join(missing)}")
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    a = ap.parse_args(argv)
    values: dict[str, str] = {}
    for kv in a.set:
        if "=" not in kv or not kv.split("=", 1)[0]:
            print("error: --set expects KEY=VALUE", file=sys.stderr)
            return 2
        k, v = kv.split("=", 1)
        values[k] = v
    out = []
    try:
        for f in a.files:
            out.append(render_text(Path(f).read_text(), values, f))
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    sys.stdout.write("\n---\n".join(o.strip("\n") + "\n" for o in out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
