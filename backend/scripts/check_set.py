"""Demo: the three documents of one test set -> Evolus output -> schema v1 -> the checks -> findings.
From the repository root:
    python backend/scripts/check_set.py 5           uses the saved extraction (no Evolus calls)
    python backend/scripts/check_set.py 5 --live    extracts again from the PDFs first
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_env_file  # noqa: E402
from app.engine.checks import findings_from, run_checks  # noqa: E402
from app.engine.rulepack import load_rule_pack  # noqa: E402
from app.services.normalize import normalize  # noqa: E402

TYPES = ("commercial_invoice", "packing_list", "bill_of_lading")
KEY = {"pass": "pass", "FINDING": "finding", "skip": "skipped_not_present"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("set_number", type=int, help="test set number, 1 to 10")
    ap.add_argument("--live", action="store_true", help="extract again from the PDFs first (uses Evolus credits)")
    args = ap.parse_args(argv)
    n = args.set_number
    load_env_file(ROOT / ".env")

    if args.live:
        from app.services.run_extraction import run
        done = run(n, os.environ, ROOT, out=lambda *a: None)
        raw = {t: r["data"] for t, r in done["results"].items()}
    else:
        local = ROOT / ".local" / "extractions" / f"set{n:02d}"
        saved = ROOT / "test-data" / "saved_extractions" / f"set{n:02d}"
        folder = local if local.is_dir() else saved
        if not folder.is_dir():
            print(f"No saved extraction for set {n}. Run:  python backend/scripts/extract_set.py {n}")
            return 1
        raw = {t: json.loads((folder / f"{t}.json").read_text(encoding="utf-8")) for t in TYPES}

    documents = {t: normalize(t, raw[t]) for t in TYPES}
    rules = load_rule_pack(ROOT / "backend" / "rulepacks" / "tz.json")
    results = run_checks(documents, rules)

    key_file = ROOT / "test-data" / f"set{n:02d}" / f"set{n:02d}_expected.json"
    key = json.loads(key_file.read_text(encoding="utf-8")).get("expected_check_outcomes", {})
    print(f"Set {n}: extracted by Evolus, normalized, checked by code")
    for r in results:
        want = KEY.get(key.get(r.check_id))
        mark = "" if want is None else ("   [matches the answer key]" if want == r.outcome else f"   [ANSWER KEY SAYS {want}]")
        print(f"  {r.check_id}: {r.outcome}{mark}")
    findings = findings_from(results)
    print(f"{len(findings)} finding(s)")
    for f in findings:
        print("  " + json.dumps(f.to_dict(), default=str))
    print("The AI extracts, the code checks, a person decides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

