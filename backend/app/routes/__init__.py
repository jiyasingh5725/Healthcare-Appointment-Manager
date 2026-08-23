from fastapi import APIRouter
from app.routes.health import router as health_router
from app.routes.db_test import router as db_test_router
from app.routes.auth import router as auth_router
from app.routes.doctors import router as doctors_router
from app.routes.admin import router as admin_router
from app.routes.doctor_schedule import router as doctor_schedule_router
from app.routes.appointments import router as appointments_router
from app.routes.doctor_portal import router as doctor_portal_router
from app.routes.notifications import router as notifications_router
from app.routes.ai_summary import router as ai_summary_router
from app.routes.prescriptions import router as prescriptions_router
from app.routes.tasks import router as tasks_router
from app.routes.patient_portal import router as patient_portal_router
from app.routes.calendar import router as calendar_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(db_test_router)
api_router.include_router(auth_router)
api_router.include_router(doctors_router)
api_router.include_router(admin_router)
api_router.include_router(doctor_schedule_router)
api_router.include_router(appointments_router)
api_router.include_router(doctor_portal_router)
api_router.include_router(notifications_router)
api_router.include_router(ai_summary_router)
api_router.include_router(prescriptions_router)
api_router.include_router(tasks_router)
api_router.include_router(patient_portal_router)
api_router.include_router(calendar_router)





