"""Runs the three PDFs of one synthetic test set through the three Evolus extractors,
saves the JSON under .local/extractions/ (ignored by git) and compares it with the expected JSON.

From the repository root:
    python backend/scripts/extract_set.py 1             run set 1
    python backend/scripts/extract_set.py 1 --dry-run   check the setup without calling Evolus
"""
import argparse
import json
import os
import sys
from pathlib import Path

from app.config import load_env_file
from app.services.accuracy import compare_documents, summarise
from app.services.evolus_client import EvolusClient, EvolusError

# (document type, file name part, environment variable holding the extractor id)
DOCUMENTS = [
    ("commercial_invoice", "invoice", "EVOLUS_EXTRACTOR_INVOICE_ID"),
    ("packing_list", "packing_list", "EVOLUS_EXTRACTOR_PACKING_LIST_ID"),
    ("bill_of_lading", "bill_of_lading", "EVOLUS_EXTRACTOR_BILL_OF_LADING_ID"),
]


def run(set_number, env, repo_root, dry_run=False, client=None, out=print):
    repo_root = Path(repo_root)
    set_dir = repo_root / "test-data" / f"set{set_number:02d}"
    expected = json.loads((set_dir / f"set{set_number:02d}_expected.json").read_text(encoding="utf-8"))["documents"]
    missing = [var for _, _, var in DOCUMENTS if not env.get(var)]
    missing += [k for k in ("EVOLUS_API_KEY", "EVOLUS_APPLICATION_ID") if not env.get(k)]
    if dry_run:
        out(f"Set {set_number}: dry run, nothing is sent to Evolus.")
        for doc_type, part, var in DOCUMENTS:
            pdf = set_dir / f"set{set_number:02d}_{part}.pdf"
            out(f"  {doc_type}: file {'found' if pdf.is_file() else 'MISSING'} ({pdf.name}), extractor id {'set' if env.get(var) else 'NOT SET'} ({var})")
        out("  EVOLUS_API_KEY: " + ("set" if env.get("EVOLUS_API_KEY") else "NOT SET") + ", EVOLUS_APPLICATION_ID: " + ("set" if env.get("EVOLUS_APPLICATION_ID") else "NOT SET"))
        return {"dry_run": True, "missing": missing}
    if missing:
        raise EvolusError("Missing environment variables: " + ", ".join(sorted(set(missing))))

    client = client or EvolusClient.from_env(env)
    out_dir = repo_root / ".local" / "extractions" / f"set{set_number:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for doc_type, part, var in DOCUMENTS:
        pdf = set_dir / f"set{set_number:02d}_{part}.pdf"
        data = client.extract(env[var], pdf, shipment_id=f"set{set_number:02d}")
        (out_dir / f"{doc_type}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        summary = summarise(compare_documents(expected[doc_type], data))
        results[doc_type] = {"data": data, "summary": summary}
        out(f"\n=== {doc_type} ===")
        out(json.dumps(data, indent=2))
        out(f"Fields correct: {summary['correct']} of {summary['total']}")
        for row in summary["wrong"]:
            out(f"  WRONG {row['field']}: expected {row['expected']!r}, got {row['actual']!r}")
    out(f"\nSaved under {out_dir}. Calls made: {len(client.calls)}.")
    return {"dry_run": False, "results": results, "calls": [c.to_dict() for c in client.calls]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("set_number", type=int, help="test set number, 1 to 10")
    parser.add_argument("--dry-run", action="store_true", help="check the setup without calling Evolus")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[3]
    load_env_file(repo_root / ".env")
    try:
        run(args.set_number, os.environ, repo_root, dry_run=args.dry_run)
    except EvolusError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
