"""Compares what an extractor returned with what the document really says (the expected JSON).
Used for the extractor accuracy test: one row per field."""
from decimal import Decimal, InvalidOperation


def flatten(data, prefix=""):
    """Turns nested JSON into {'path': value}. Lists of plain values stay together as one field."""
    out = {}
    if isinstance(data, dict):
        for key, value in data.items():
            out.update(flatten(value, f"{prefix}.{key}" if prefix else key))
    elif isinstance(data, list):
        if all(not isinstance(v, (dict, list)) for v in data):
            out[prefix] = sorted(data, key=str)
        else:
            for i, value in enumerate(data):
                out.update(flatten(value, f"{prefix}[{i}]"))
    else:
        out[prefix] = data
    return out


def _same(expected, actual):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_same(e, a) for e, a in zip(expected, actual))
    return expected == actual


MISSING = "<missing>"


def compare_documents(expected, actual):
    """Returns one row per expected field: {'field', 'expected', 'actual', 'match'}."""
    exp, act = flatten(expected), flatten(actual or {})
    return [{"field": f, "expected": v, "actual": act.get(f, MISSING), "match": f in act and _same(v, act[f])} for f, v in exp.items()]


def summarise(rows):
    correct = sum(1 for r in rows if r["match"])
    return {"correct": correct, "total": len(rows), "wrong": [r for r in rows if not r["match"]]}
