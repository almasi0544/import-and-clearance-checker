"""The checks. Each check takes the confirmed documents and the rule pack and returns a CheckResult.

`documents` is a dict like the "documents" part of a setNN_expected.json file:
    {"commercial_invoice": {...}, "packing_list": {...}, "bill_of_lading": {...}}
A missing field is never a mismatch: the check is skipped and recorded as "skipped_not_present".
"""
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from itertools import combinations

from .models import CheckResult, Finding

LB_TO_KG = Decimal("0.45359237")
TYPE_SYNONYMS = {"ctn": "carton", "ctns": "carton", "plt": "pallet", "plts": "pallet"}
UNIT_SYNONYMS = {"pc": "piece", "pcs": "piece", "piece": "piece", "pieces": "piece", "unit": "piece", "units": "piece"}
COMPANY_SUFFIXES = {"ltd", "limited", "co", "company", "llc", "inc", "gmbh", "corp", "corporation", "plc"}
DOC_LABEL = {"commercial_invoice": "invoice", "packing_list": "packing list", "bill_of_lading": "bill of lading"}


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


def _norm_word(word, synonyms=None):
    """'Cartons', 'carton' and 'ctns' all become 'carton'. None if the word is missing."""
    if word is None:
        return None
    s = str(word).strip().lower()
    if not s:
        return None
    s = (synonyms or {}).get(s, s)
    if s.endswith("es") and s[:-2].endswith(("x", "s", "ch", "sh")):
        s = s[:-2]
    elif s.endswith("s") and not s.endswith("ss"):
        s = s[:-1]
    return (synonyms or {}).get(s, s)


def _norm_type(package_type):
    return _norm_word(package_type, TYPE_SYNONYMS)


def _norm_unit(unit):
    return _norm_word(unit, UNIT_SYNONYMS)


def _tidy_name(name):
    """Lower case, no punctuation, no company suffix: 'EXAMPLE Imports, Ltd.' -> 'example imports'."""
    if name is None:
        return ""
    words = re.sub(r"[^a-z0-9 ]", " ", str(name).lower()).split()
    return " ".join(w for w in words if w not in COMPANY_SUFFIXES)


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


# ---------- C1 and C2: names of the parties (all three documents) ----------
def _check_names(check_id, label, field, getters, documents, rules):
    """Compare the names on every pair of documents that carry one. A name is tidied first
    (lower case, no punctuation, no company suffix) and must then be similar enough to pass."""
    threshold = float(rules["name_similarity_threshold"])
    names = []
    for doc_key, getter in getters:
        printed = getter(documents.get(doc_key) or {})
        tidy = _tidy_name(printed)
        if tidy:
            names.append((doc_key, str(printed).strip(), tidy))
    if len(names) < 2:
        return CheckResult(check_id, "skipped_not_present", note=f"The {label} name is present on fewer than two documents.")

    findings = []
    for (doc_a, name_a, tidy_a), (doc_b, name_b, tidy_b) in combinations(names, 2):
        if SequenceMatcher(None, tidy_a, tidy_b).ratio() >= threshold:
            continue
        findings.append(Finding(
            check_id, "high", [doc_a, doc_b], field, {doc_a: name_a, doc_b: name_b},
            f'{label.capitalize()} name differs: "{name_a}" on the {DOC_LABEL[doc_a]}, "{name_b}" on the {DOC_LABEL[doc_b]}.'))
    return CheckResult(check_id, "finding" if findings else "pass", findings=findings)


def check_c1(documents, rules):
    """Consignee name. The invoice buyer, packing list consignee and bill of lading consignee
    must be equal or nearly equal after tidying."""
    getters = [("commercial_invoice", lambda d: (d.get("buyer") or {}).get("name")),
               ("packing_list", lambda d: (d.get("consignee") or {}).get("name")),
               ("bill_of_lading", lambda d: (d.get("consignee") or {}).get("name"))]
    return _check_names("C1", "consignee", "consignee.name", getters, documents, rules)


def check_c2(documents, rules):
    """Shipper name. The invoice seller, packing list shipper and bill of lading shipper."""
    getters = [("commercial_invoice", lambda d: (d.get("seller") or {}).get("name")),
               ("packing_list", lambda d: (d.get("shipper") or {}).get("name")),
               ("bill_of_lading", lambda d: (d.get("shipper") or {}).get("name"))]
    return _check_names("C2", "shipper", "shipper.name", getters, documents, rules)


# ---------- C5: quantity in units (invoice against packing list) ----------
def _quantities_by_unit(doc):
    """{'piece': Decimal(5000), ...} from lines[].quantity. None if there are no lines or a quantity is missing."""
    lines = doc.get("lines") or []
    if not lines:
        return None
    totals = {}
    for line in lines:
        q = _num((line or {}).get("quantity"))
        if q is None:
            return None
        unit = _norm_unit((line or {}).get("unit"))
        totals[unit] = totals.get(unit, Decimal(0)) + q
    return totals


def _units_label(totals):
    return ", ".join(_label(v, u) for u, v in sorted(totals.items(), key=lambda kv: str(kv[0])))


def check_c5(documents, rules):
    """Total quantity must be exactly equal on the invoice and the packing list, for the same unit of
    measure. If both documents name their units and the units differ (pieces and sets), the check
    cannot compare them. Several units on one document are compared unit by unit."""
    inv = _quantities_by_unit(documents.get("commercial_invoice") or {})
    pl = _quantities_by_unit(documents.get("packing_list") or {})
    if inv is None or pl is None:
        return CheckResult("C5", "skipped_not_present", note="The quantity is not present on both documents.")

    docs = ["commercial_invoice", "packing_list"]
    all_known = None not in inv and None not in pl
    if all_known and set(inv) != set(pl):
        a, b = _units_label(inv), _units_label(pl)
        finding = Finding("C5", "low", docs, "quantity", {docs[0]: a, docs[1]: b},
                          f"Quantity cannot be compared: {a} on the invoice, {b} on the packing list. Please confirm.")
        return CheckResult("C5", "cannot_compare", finding)

    if all_known:
        pairs = [(unit, inv[unit], pl[unit]) for unit in sorted(inv)]
    else:
        pairs = [(None, sum(inv.values()), sum(pl.values()))]
    findings = []
    for unit, a, b in pairs:
        if a == b:
            continue
        where = f" ({unit})" if unit and len(pairs) > 1 else ""
        findings.append(Finding("C5", "high", docs, "quantity", {docs[0]: _json_num(a), docs[1]: _json_num(b)},
                                f"Quantity differs{where}: {_fmt(a)} on the invoice, {_fmt(b)} on the packing list."))
    return CheckResult("C5", "finding" if findings else "pass", findings=findings)


# ---------- C6: invoice arithmetic (inside the invoice) ----------
def check_c6(documents, rules):
    """Each line total must equal quantity times unit price, and the lines must add up to the stated
    subtotal (or, when there is no subtotal, the stated total value), within the money tolerance.
    A line with a missing number is skipped. If the invoice shows tax or discounts, the extractor
    should return the subtotal, because the total value then includes them."""
    inv = documents.get("commercial_invoice") or {}
    tolerance = Decimal(str(rules["money_tolerance"]))
    lines = inv.get("lines") or []
    findings, compared, line_totals = [], 0, []
    for n, line in enumerate(lines, start=1):
        line = line or {}
        quantity, price, stated = _num(line.get("quantity")), _num(line.get("unit_price")), _num(line.get("line_total"))
        line_totals.append(stated)
        if quantity is None or price is None or stated is None:
            continue
        compared += 1
        expected = quantity * price
        if abs(expected - stated) > tolerance:
            findings.append(Finding(
                "C6", "high", ["commercial_invoice"], f"lines[{n}].line_total",
                {"quantity": _json_num(quantity), "unit_price": _json_num(price), "expected": _json_num(expected), "stated": _json_num(stated)},
                f"Invoice line {n}: {_fmt(quantity)} x {_fmt(price)} is {_fmt(expected)}, but the line total is {_fmt(stated)}."))

    field, reference = "subtotal", _num(inv.get("subtotal"))
    if reference is None:
        field, reference = "total_value", _num(inv.get("total_value"))
    if lines and reference is not None and all(t is not None for t in line_totals):
        compared += 1
        total = sum(line_totals)
        if abs(total - reference) > tolerance:
            word = "subtotal" if field == "subtotal" else "total"
            findings.append(Finding(
                "C6", "high", ["commercial_invoice"], field, {"lines_sum": _json_num(total), "stated": _json_num(reference)},
                f"Invoice lines add up to {_fmt(total)}, but the stated {word} is {_fmt(reference)}."))

    if findings:
        return CheckResult("C6", "finding", findings=findings)
    if compared == 0:
        return CheckResult("C6", "skipped_not_present", note="The invoice has no complete lines or total to check.")
    return CheckResult("C6", "pass")


# ---------- runner ----------
CHECKS = [check_c1, check_c2, check_c3, check_c4, check_c5, check_c6]   # add C7 to C10 here as they are written


def run_checks(documents, rules):
    return [check(documents, rules) for check in CHECKS]


def findings_from(results):
    return [f for r in results for f in r.findings]
