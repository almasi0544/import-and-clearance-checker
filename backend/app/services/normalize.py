"""Turns what an Evolus extractor returns into schema v1, the shape the check engine reads.
It fixes the shape only: snake_case names, numbers as numbers, parties as {name, address}, constants added.
It never invents a value. A field that is missing stays missing, and text it cannot read stays as it was."""
import re

SCHEMA_VERSION = "1"
PACKAGE_TYPES = {"cartons": "carton", "pallets": "pallet", "boxes": "box", "crates": "crate",
                 "bags": "bag", "drums": "drum", "packages": "package", "bundles": "bundle"}
HS_IN_TEXT = re.compile(r"\s*\(?\bHS\s*Code\s*:?\s*([0-9][0-9. ]{3,}[0-9])\)?", re.I)
NUMBER_FIELDS = ("packages", "gross_weight", "net_weight", "total_net_weight", "total_gross_weight", "declared_value")


def snake(key):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()


def _keys(value):
    if isinstance(value, dict):
        return {snake(k): _keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_keys(v) for v in value]
    return value


def number(value):
    """5,000 -> 5000 and 4,200.00 -> 4200.0. Anything that is not a plain number stays unchanged."""
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace(" ", "")
        if re.fullmatch(r"-?\d+(\.\d+)?", text):
            return float(text) if "." in text else int(text)
    return value


def party(value):
    """A text blob 'Name\nAddress' becomes {name, address}. A dict or None stays as it is."""
    if isinstance(value, str):
        lines = [x.strip() for x in value.splitlines() if x.strip()]
        if not lines:
            return None
        return {"name": lines[0], "address": ", ".join(lines[1:]) or None}
    return value


def package_type(value):
    if isinstance(value, str):
        text = value.strip().lower()
        return PACKAGE_TYPES.get(text, text)
    return value


def _invoice(d):
    for key in ("subtotal", "total_value"):
        if key in d:
            d[key] = number(d[key])
    for line in d.get("lines") or []:
        if isinstance(line, dict):
            for key in ("quantity", "unit_price", "line_total"):
                if key in line:
                    line[key] = number(line[key])


def _packing(d):
    codes = []
    for line in d.get("lines") or []:
        if not isinstance(line, dict):
            continue
        text = line.get("description")
        if isinstance(text, str):
            for m in HS_IN_TEXT.finditer(text):
                code = re.sub(r"\D", "", m.group(1))
                if code and code not in codes:
                    codes.append(code)
            line["description"] = HS_IN_TEXT.sub("", text).strip()
        for key in ("quantity", "net_weight"):
            if key in line:
                line[key] = number(line[key])
    d.setdefault("hs_codes", codes)


def normalize(doc_type, data):
    if not isinstance(data, dict):
        return data
    d = _keys(data)
    d["schema_version"] = SCHEMA_VERSION
    d["document_type"] = doc_type
    for key in ("shipper", "consignee", "seller", "buyer", "importer"):
        if key in d:
            d[key] = party(d[key])
    if isinstance(d.get("notify_party"), str) and d["notify_party"].strip().lower().startswith("same as"):
        d["notify_party"] = None
    if "package_type" in d:
        d["package_type"] = package_type(d["package_type"])
    for key in NUMBER_FIELDS:
        if key in d:
            d[key] = number(d[key])
    if doc_type == "commercial_invoice":
        _invoice(d)
    elif doc_type == "packing_list":
        _packing(d)
    return d
