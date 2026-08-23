from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes import api_router
from app.error_handlers import register_error_handlers

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for Healthcare Appointment & Follow-up Manager",
    version="1.0.0",
    debug=settings.DEBUG,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Centralized Error Handlers
register_error_handlers(app)

# Register API Router
app.include_router(api_router)


@app.get("/", summary="Root Endpoint", tags=["Root"])
def root():
    """
    Root endpoint for basic verification.
    """
    return {
        "app": settings.APP_NAME,
        "status": "online",
        "docs_url": "/docs",
        "health_check": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
