from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", summary="API Health Check")
def health_check():
    """
    Health check endpoint returning service status.
    """
    return {
        "success": True,
        "message": "Healthcare Appointment Manager API is running"
    }
