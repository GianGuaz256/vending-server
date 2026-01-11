"""Health check endpoint."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database connectivity check."""
    try:
        # Quick database connectivity check
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "degraded"
    
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "time": datetime.now(timezone.utc).isoformat(),
    }

