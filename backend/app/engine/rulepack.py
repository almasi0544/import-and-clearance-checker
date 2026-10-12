"""Loads the rule pack: the tolerances and thresholds. No number is hard-coded in the checks."""
import json
from pathlib import Path

REQUIRED_KEYS = ("version", "weight_tolerance_percent", "money_tolerance")


def load_rule_pack(path):
    with open(Path(path), encoding="utf-8") as f:
        rules = json.load(f)
    missing = [k for k in REQUIRED_KEYS if k not in rules]
    if missing:
        raise ValueError(f"Rule pack is missing: {', '.join(missing)}")
    return rules
