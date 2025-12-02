from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from db import engine, Base
from routers import analysis as analysis_router, status as status_router, result as result_router, core_engine as core_router, auth as auth_router
import models

app = FastAPI(title=settings.APP_NAME)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

# Public health endpoint (for API contract)
@app.get("/health", tags=["System"], summary="Server health check")
def root_health():
    return {"status": "ok", "app": settings.APP_NAME}

# Versioned health endpoint (kept for backward compatibility)
@app.get(settings.API_V1_STR + "/health", tags=["System"], summary="Server health check (versioned)")
def health():
    return {"status": "ok", "app": settings.APP_NAME}

app.include_router(auth_router.router, prefix=settings.API_V1_STR)
app.include_router(analysis_router.router, prefix=settings.API_V1_STR)
app.include_router(status_router.router, prefix=settings.API_V1_STR + "/analysis")
app.include_router(result_router.router, prefix=settings.API_V1_STR + "/analysis")
app.include_router(core_router.router, prefix=settings.API_V1_STR)