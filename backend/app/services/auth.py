from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any

security = HTTPBearer(auto_error=False)

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Dict[str, Any]:
    """
    Reads and validates the bearer token, returning the current user dictionary.
    Raises a 401 Unauthorized error if the token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # For local development/testing, accept a mock token or decode a JWT
    if token == "mock-token-admin":
        return {
            "id": "user-admin-001",
            "email": "admin@example.com",
            "role": "admin"
        }
    elif token == "mock-token-user":
        return {
            "id": "user-standard-002",
            "email": "user@example.com",
            "role": "user"
        }
    
    # Real JWT or session token decoding can go here:
    # user = decode_jwt_token(token)
    # if not user:
    #     raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    # Fallback for unhandled tokens during testing
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token"
    )

def require_role(required_role: str):
    """
    Dependency generator that checks if the authenticated user has the required role.
    Raises a 403 Forbidden error if the role does not match.
    """
    def role_dependency(current_user: Dict[str, Any] = Security(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role != required_role and user_role != "admin":  # Admins usually bypass role checks
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {required_role}"
            )
        return current_user
    return role_dependency

def get_shipment_for_user(shipment_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetches a shipment by ID and ensures the user has permission to view/modify it.
    """
    from app.db.database import get_db
    db = get_db()
    
    shipments = db.execute_query("SELECT * FROM shipments WHERE id = %s;", (shipment_id,))
    if not shipments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found"
        )
    
    shipment = shipments[0]
    
    # Enforce ownership check (Admins can view any shipment, regular users only their own)
    if shipment.get("owner_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this shipment"
        )
        
    return shipment

def audit(user: Dict[str, Any], action: str, object_type: str, object_id: str):
    """
    Appends an immutable audit event record to the database.
    """
    try:
        from app.db.database import get_db
        db = get_db()
        db.execute_insert(
            """
            INSERT INTO audit_events (user_id, action, object_type, object_id)
            VALUES (%s, %s, %s, %s);
            """,
            (user.get("id"), action, object_type, object_id)
        )
    except Exception as e:
        # Log error quietly or handle it so it doesn't break primary request flows
        print(f"Audit log failed: {str(e)}")