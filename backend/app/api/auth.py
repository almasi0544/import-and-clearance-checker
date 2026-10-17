"""POST /auth/login: email and password in, a short-lived token out."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_db
from app.db.database import Database
from app.services.auth import login

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)

@router.post("/login")
def do_login(body: LoginIn, db: Database = Depends(get_db)):
    return {"access_token": login(db, body.email, body.password), "token_type": "bearer"}