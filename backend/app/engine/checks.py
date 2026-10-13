"""The checks. Each check takes the confirmed documents and the rule pack and returns a CheckResult.

`documents` is a dict like the "documents" part of a setNN_expected.json file:
    {"commercial_invoice": {...}, "packing_list": {...}, "bill_of_lading": {...}}
A missing field is never a mismatch: the check is skipped and recorded as "skipped_not_present".
"""
from decimal import Decimal, InvalidOperation

from .models import CheckResult, Finding

LB_TO_KG = Decimal("0.45359237")
TYPE_SYNONYMS = {"ctn": "carton", "ctns": "carton", "plt": "pallet", "plts": "pallet"}


# ---------- small helpers ----------
def _num(value):
    """A JSON number as a Decimal, or None if it is missing or not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _fmt(d):
    """Format a Decimal for a message: 2500 -> '2500', 45.359237 -> '45.36'."""
    s = format(d.quantize(Decimal("0.01")), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _json_num(d):
    """A Decimal as a plain JSON number: int when whole, otherwise rounded to 2 decimals."""
    q = d.quantize(Decimal("0.01"))
    return int(q) if q == q.to_integral_value() else float(q)


def _to_kg(value, unit):
    """Convert a weight to kilograms. Returns None if the unit is missing or not recognised."""
    n = _num(value)
    u = (unit or "").strip().lower()
    if n is None:
        return None
    if u in ("kg", "kgs", "kilogram", "kilograms"):
        return n
    if u in ("lb", "lbs", "pound", "pounds"):
        return n * LB_TO_KG
    return None


def _norm_type(package_type):
    """'Cartons', 'carton' and 'ctns' all become 'carton'. None if the type is missing."""
    if package_type is None:
        return None
    s = str(package_type).strip().lower()
    if not s:
        return None
    s = TYPE_SYNONYMS.get(s, s)
    if s.endswith("es") and s[:-2].endswith(("x", "s", "ch", "sh")):
        s = s[:-2]
    elif s.endswith("s") and not s.endswith("ss"):
        s = s[:-1]
    return s


def _label(count, package_type):
    """'2 pallets', '1 pallet', '25 cartons'."""
    if package_type is None:
        return _fmt(count)
    if count != 1:
        package_type += "es" if package_type.endswith(("s", "x", "ch", "sh")) else "s"
    return f"{_fmt(count)} {package_type}"


# ---------- C3: gross weight (packing list against bill of lading) ----------
def check_c3(documents, rules):
    """Gross weights must be equal within the tolerance in the rule pack (1 percent to start).
    The percentage is measured against the packing list value. Invoices are left out
    because their weight is not labelled gross or net."""
    pl = documents.get("packing_list") or {}
    bl = documents.get("bill_of_lading") or {}
    raw_a, raw_b = pl.get("total_gross_weight"), bl.get("gross_weight")
    if _num(raw_a) is None or _num(raw_b) is None:
        return CheckResult("C3", "skipped_not_present", note="Gross weight is not present on both documents.")

    a = _to_kg(raw_a, pl.get("weight_unit"))
    b = _to_kg(raw_b, bl.get("weight_unit"))
    if a is None or b is None:
        finding = Finding(
            "C3", "low", ["packing_list", "bill_of_lading"], "gross_weight",
            {"packing_list": f"{raw_a} {pl.get('weight_unit')}", "bill_of_lading": f"{raw_b} {bl.get('weight_unit')}"},
            "Gross weight cannot be compared because the weight unit is missing or not recognised. Please confirm.")
        return CheckResult("C3", "cannot_compare", finding)

    tolerance = Decimal(str(rules["weight_tolerance_percent"]))
    difference = abs(a - b)
    reference = a if a != 0 else b
    if reference == 0 or difference <= reference * tolerance / Decimal(100):
        return CheckResult("C3", "pass")

    percent = (difference / reference * 100).quantize(Decimal("0.1"))
    finding = Finding(
        "C3", "high", ["packing_list", "bill_of_lading"], "gross_weight",
        {"packing_list": _json_num(a), "bill_of_lading": _json_num(b)},
        f"Gross weight differs by {_fmt(difference)} kg ({_fmt(percent)} percent): "
        f"{_fmt(a)} kg on the packing list, {_fmt(b)} kg on the bill of lading.")
    return CheckResult("C3", "finding", finding)


# ---------- C4: number of packages (packing list against bill of lading) ----------
def check_c4(documents, rules):
    """Package counts must match exactly, but only when the package type is the same.
    If both types are known and differ (pallets and cartons), the check cannot compare them
    and returns a Low finding asking for confirmation. If a type is missing, the counts are
    compared as they are."""
    pl = documents.get("packing_list") or {}
    bl = documents.get("bill_of_lading") or {}
    a, b = _num(pl.get("packages")), _num(bl.get("packages"))
    if a is None or b is None:
        return CheckResult("C4", "skipped_not_present", note="The number of packages is not present on both documents.")

    type_a, type_b = _norm_type(pl.get("package_type")), _norm_type(bl.get("package_type"))
    if type_a and type_b and type_a != type_b:
        label_a, label_b = _label(a, type_a), _label(b, type_b)
        finding = Finding(
            "C4", "low", ["packing_list", "bill_of_lading"], "packages",
            {"packing_list": label_a, "bill_of_lading": label_b},
            f"Packages cannot be compared: {label_a} on the packing list, {label_b} on the bill of lading. Please confirm.")
        return CheckResult("C4", "cannot_compare", finding)

    if a == b:
        return CheckResult("C4", "pass")

    finding = Finding(
        "C4", "high", ["packing_list", "bill_of_lading"], "packages",
        {"packing_list": _json_num(a), "bill_of_lading": _json_num(b)},
        f"Number of packages differs: {_fmt(a)} on the packing list, {_fmt(b)} on the bill of lading.")
    return CheckResult("C4", "finding", finding)


# ---------- runner ----------
CHECKS = [check_c3, check_c4]   # add the other checks here as they are written


def run_checks(documents, rules):
    return [check(documents, rules) for check in CHECKS]


def findings_from(results):
    return [r.finding for r in results if r.finding is not None]
