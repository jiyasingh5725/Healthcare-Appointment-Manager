import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

# Mount Frontend Static Files (Serves index.html, portals, css, js in one unified service)
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)

