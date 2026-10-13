from dataclasses import dataclass, asdict

# What one check can say about one shipment:
#   pass                 the check ran and found no difference
#   finding              the check ran and found at least one difference
#   skipped_not_present  a field is missing, so the check was skipped (never an error)
#   cannot_compare       both fields exist but cannot be compared (for example pallets and cartons)
OUTCOMES = ("pass", "finding", "skipped_not_present", "cannot_compare")


@dataclass
class Finding:
    check_id: str
    severity: str          # "high", "medium" or "low"
    documents: list        # the documents involved
    field: str
    values: dict           # the values side by side
    message: str           # fixed wording written by the engine

    def to_dict(self):
        return asdict(self)


class CheckResult:
    """The result of one check. A check can produce several findings (for example one for each
    pair of documents, or one for each wrong invoice line). `finding` is the first one."""

    def __init__(self, check_id, outcome, finding=None, note=None, findings=None):
        self.check_id = check_id
        self.outcome = outcome
        self.note = note
        self.findings = list(findings) if findings is not None else ([finding] if finding is not None else [])

    @property
    def finding(self):
        return self.findings[0] if self.findings else None

    def __repr__(self):
        return f"CheckResult({self.check_id!r}, {self.outcome!r}, findings={len(self.findings)})"
