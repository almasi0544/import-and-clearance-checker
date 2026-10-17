"""The audit helper: one row for every important action. Call it inside the same transaction as the action.
Never put full documents, passwords, keys or personal details in `details`.
(Almasi owns this file. This is a minimal version so the endpoints can use it.)"""
from app.db.database import new_id

EVENTS = ("login_success", "login_failed", "shipment_created", "document_uploaded", "extraction_started",
          "extraction_finished", "fields_confirmed", "analysis_run", "finding_updated", "case_approved")


def audit(db, user, action, object_type=None, object_id=None, details=None):
    user_id = user["id"] if user else None
    db.execute("INSERT INTO audit_events (id, user_id, action, object_type, object_id, details) VALUES (?, ?, ?, ?, ?, ?)",
               (new_id(), user_id, action, object_type, object_id, db.json_param(details) if details is not None else None))
