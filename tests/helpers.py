import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.rulepack import load_rule_pack  # noqa: E402


def load_rules():
    return load_rule_pack(ROOT / "backend" / "rulepacks" / "tz.json")


def load_set(n):
    path = ROOT / "test-data" / f"set{n:02d}" / f"set{n:02d}_expected.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_documents(n):
    return load_set(n)["documents"]
