"""The shipment endpoints (Step 1.5). Thin: all the rules are in app/services/shipments.py."""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db, upload_dir
from app.services import shipments as service
from app.services.uploads import max_upload_bytes

router = APIRouter(prefix="/shipments", tags=["shipments"])


class ShipmentIn(BaseModel):
    reference: str
    country: str | None = None        # any other field in the request (owner_id, status) is ignored


@router.post("", status_code=201)
def create(body: ShipmentIn, user=Depends(get_current_user), db=Depends(get_db)):
    return service.create_shipment(db, user, body.reference, body.country)


@router.get("")
def list_all(user=Depends(get_current_user), db=Depends(get_db)):
    return service.list_shipments(db, user)


@router.get("/{shipment_id}")
def show(shipment_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    return service.get_shipment(db, user, shipment_id)


@router.post("/{shipment_id}/documents", status_code=201)
def upload(shipment_id: str, doc_type: str = Form(...), file: UploadFile = File(...),
           user=Depends(get_current_user), db=Depends(get_db)):
    limit = max_upload_bytes()
    content = file.file.read(limit + 1)        # read one byte more than the limit, so a too-large file is noticed
    return service.upload_document(db, user, shipment_id, doc_type, content, upload_dir(), limit)
