from dataclasses import dataclass, asdict
from typing import Optional

# What one check can say about one shipment:
#   pass                 the check ran and found no difference
#   finding              the check ran and found a difference
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


@dataclass
class CheckResult:
    check_id: str
    outcome: str
    finding: Optional[Finding] = None
    note: Optional[str] = None
