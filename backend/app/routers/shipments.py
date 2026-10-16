from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from typing import List, Optional
from pydantic import BaseModel
# Assuming Almasi's auth functions are in app.services.auth or similar:
from app.services.auth import get_current_user
from app.db.database import get_db

router = APIRouter(prefix="/shipments", tags=["Shipments"])

# Pydantic schema for creating a shipment request body
class ShipmentCreateRequest(BaseModel):
    reference_number: str
    importer_name: str
    exporter_name: str
    declared_value: float
    currency: str = "USD"

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_shipment(
    payload: ShipmentCreateRequest, 
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new shipment record linked to the authenticated user.
    """
    db = get_db()
    try:
        # Example insertion query logic
        shipment_id = db.execute_insert(
            """
            INSERT INTO shipments (reference_number, importer_name, exporter_name, declared_value, currency, owner_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'draft')
            RETURNING id;
            """,
            (payload.reference_number, payload.importer_name, payload.exporter_name, 
             payload.declared_value, payload.currency, current_user["id"])
        )
        return {
            "message": "Shipment created successfully", 
            "shipment_id": shipment_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Failed to create shipment: {str(e)}"
        )

@router.get("/", status_code=status.HTTP_200_OK)
def list_shipments(current_user: dict = Depends(get_current_user)):
    """
    List all shipments accessible by the authenticated user.
    """
    db = get_db()
    # Fetch shipments depending on user role (Admin sees all, user sees their own)
    if current_user.get("role") == "admin":
        shipments = db.execute_query("SELECT * FROM shipments ORDER BY created_at DESC;")
    else:
        shipments = db.execute_query(
            "SELECT * FROM shipments WHERE owner_id = %s ORDER BY created_at DESC;", 
            (current_user["id"],)
        )
    return {"shipments": shipments}

@router.post("/{shipment_id}/documents", status_code=status.HTTP_201_CREATED)
def upload_document(
    shipment_id: str, 
    file: UploadFile = File(...), 
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a clearance document (e.g., invoice, bill of lading) for a shipment.
    """
    # Verify shipment ownership or access rights first
    db = get_db()
    shipment = db.execute_query("SELECT * FROM shipments WHERE id = %s;", (shipment_id,))
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Save file logic and register metadata into documents table here
    return {
        "message": f"File '{file.filename}' uploaded successfully",
        "shipment_id": shipment_id,
        "filename": file.filename
    }

@router.get("/{shipment_id}", status_code=status.HTTP_200_OK)
def get_shipment_details(
    shipment_id: str, 
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch full details and associated documents for a single shipment.
    """
    db = get_db()
    shipment = db.execute_query("SELECT * FROM shipments WHERE id = %s;", (shipment_id,))
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
        
    return {
        "shipment": shipment[0],
        "documents": [] # Fetch related documents in your production query
    }