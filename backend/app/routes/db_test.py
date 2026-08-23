from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from app.database import get_db, engine
from app.config import settings

router = APIRouter(prefix="/db-test", tags=["Database"])


@router.get("", summary="Database Connection Test")
def test_database_connection(db: Session = Depends(get_db)):
    """
    Test connectivity to the MySQL database and report existing tables.
    """
    try:
        # Execute a ping/test query
        db.execute(text("SELECT 1"))

        # Inspect database tables
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        return {
            "success": True,
            "message": "Database connection successful",
            "database": "healthcare_manager",
            "tables": tables
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "message": "Database connection failed",
                "error": str(e)
            }
        )
