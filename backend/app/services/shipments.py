"""The shipment endpoints' logic: create, list, show one, upload a document.
Plain functions, no web framework, so they are easy to test. The three checks are applied here:
who are you (the user passed in), what is your role, and is this case yours."""
import uuid

from app.db.database import new_id, utc_now
from app.errors import BadRequest, Conflict, Forbidden, NotFound
from app.services.audit import audit
from app.services.uploads import check_upload, max_upload_bytes, remove_file, save_file

DOC_TYPES = ("commercial_invoice", "packing_list", "bill_of_lading")
CREATE_ROLES = ("importer", "clearing_agent")
UPLOAD_ROLES = ("importer", "clearing_agent")
DEFAULT_COUNTRY = "TZ"
MAX_REFERENCE = 100


# ---------- who may see which shipment ----------
def _visibility(user):
    """SQL condition and parameters for the shipments this user may see."""
    role = user["role"]
    if role in ("reviewer", "admin"):
        return "1 = 1", ()
    if role == "clearing_agent":
        return "(owner_id = ? OR assigned_agent_id = ?)", (user["id"], user["id"])
    return "owner_id = ?", (user["id"],)


def _valid_id(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def get_shipment_for_user(db, shipment_id, user):
    """The shipment row, or NotFound. A case that does not exist and a case that is not yours give the same
    answer, so nobody learns that someone else's case exists."""
    if not _valid_id(shipment_id):
        raise NotFound("Shipment not found.")
    condition, params = _visibility(user)
    row = db.query_one(f"SELECT * FROM shipments WHERE id = ? AND {condition}", (shipment_id, *params))
    if row is None:
        raise NotFound("Shipment not found.")
    return row


def _summary(row):
    return {k: row[k] for k in ("id", "reference", "country", "status", "owner_id", "assigned_agent_id", "created_at", "updated_at")}


# ---------- create ----------
def create_shipment(db, user, reference, country=None):
    """The owner comes from the logged-in user, and the status, id and times come from the server.
    There is no way to pass them in."""
    if user["role"] not in CREATE_ROLES:
        raise Forbidden("Your role cannot create a shipment.")
    reference = (reference or "").strip()
    if not reference:
        raise BadRequest("Enter a reference for the shipment.")
    if len(reference) > MAX_REFERENCE:
        raise BadRequest(f"The reference is too long. The limit is {MAX_REFERENCE} characters.")
    country = (country or DEFAULT_COUNTRY).strip().upper()
    if len(country) != 2 or not country.isalpha():
        raise BadRequest("The country must be a two-letter code, for example TZ.")

    shipment_id = new_id()
    with db.transaction():
        db.execute("INSERT INTO shipments (id, reference, country, owner_id) VALUES (?, ?, ?, ?)",
                   (shipment_id, reference, country, user["id"]))
        audit(db, user, "shipment_created", "shipment", shipment_id, {"reference": reference})
    return _summary(db.query_one("SELECT * FROM shipments WHERE id = ?", (shipment_id,)))


# ---------- list ----------
def list_shipments(db, user):
    condition, params = _visibility(user)
    rows = db.query(f"SELECT * FROM shipments WHERE {condition} ORDER BY created_at DESC, id", params)
    return [_summary(r) for r in rows]


# ---------- show one ----------
def get_shipment(db, user, shipment_id):
    shipment = get_shipment_for_user(db, shipment_id, user)
    documents = db.query("SELECT id, doc_type, mime_type, size_bytes, file_hash, uploaded_at FROM documents "
                         "WHERE shipment_id = ? ORDER BY uploaded_at, id", (shipment["id"],))
    return {**_summary(shipment), "documents": documents}      # the stored file path is never shown


# ---------- upload ----------
def upload_document(db, user, shipment_id, doc_type, content, upload_dir, max_bytes=None):
    shipment = get_shipment_for_user(db, shipment_id, user)           # 404 first: not yours or missing
    if user["role"] not in UPLOAD_ROLES:
        raise Forbidden("Your role cannot upload documents.")
    if doc_type not in DOC_TYPES:
        raise BadRequest("The document type must be commercial_invoice, packing_list or bill_of_lading.")
    if shipment["status"] == "approved":
        raise Conflict("This case is already approved, so documents can no longer be changed.")
    mime, ext = check_upload(content, max_bytes if max_bytes is not None else max_upload_bytes())

    stored_name, file_hash = save_file(upload_dir, content, ext)
    old = db.query_one("SELECT id, file_path FROM documents WHERE shipment_id = ? AND doc_type = ?", (shipment["id"], doc_type))
    document_id = new_id()
    try:
        with db.transaction():
            if old:      # uploading again replaces the document and clears its old extraction
                db.execute("DELETE FROM extractions WHERE document_id = ?", (old["id"],))
                db.execute("DELETE FROM documents WHERE id = ?", (old["id"],))
            db.execute("INSERT INTO documents (id, shipment_id, doc_type, file_path, file_hash, mime_type, size_bytes, uploaded_by) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (document_id, shipment["id"], doc_type, stored_name, file_hash, mime, len(content), user["id"]))
            present = {r["doc_type"] for r in db.query("SELECT doc_type FROM documents WHERE shipment_id = ?", (shipment["id"],))}
            status = "documents_uploaded" if present == set(DOC_TYPES) else "created"
            db.execute("UPDATE shipments SET status = ?, updated_at = ? WHERE id = ?", (status, utc_now(), shipment["id"]))
            audit(db, user, "document_uploaded", "document", document_id,
                  {"shipment_id": shipment["id"], "doc_type": doc_type, "size_bytes": len(content), "replaced": bool(old)})
    except Exception:
        remove_file(upload_dir, stored_name)          # do not leave an orphan file behind
        raise
    if old:
        remove_file(upload_dir, old["file_path"])
    return {"id": document_id, "doc_type": doc_type, "mime_type": mime, "size_bytes": len(content),
            "file_hash": file_hash, "replaced": bool(old), "shipment_status": status}
