"""Matters (explicit field allow-list — no raw dict inserts)."""
import re

from fastapi import APIRouter, Depends, HTTPException

from api.auth import verify_token
from api.deps import get_db
from api.schemas import MatterCreate

router = APIRouter(prefix="/matters", tags=["Matters"], dependencies=[Depends(verify_token)])


@router.post("")
def create_matter(body: MatterCreate, db=Depends(get_db)):
    r = db.table("matters").insert(body.model_dump()).execute()
    return r.data[0] if r.data else {}


@router.get("/{matter_id}")
def get_matter(matter_id: str, db=Depends(get_db)):
    if not re.match(r"^[0-9a-fA-F-]{36}$", matter_id):
        raise HTTPException(400, "matter_id must be a UUID")
    r = db.table("matters").select("*").eq("id", matter_id).execute()
    if not r.data:
        raise HTTPException(404, "Matter not found")
    return r.data[0]
