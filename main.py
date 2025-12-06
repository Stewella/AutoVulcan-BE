from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from config import settings
from db import engine, Base, ensure_schema_upgrades
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
# apply light schema upgrades for backwards compatibility
ensure_schema_upgrades()

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

# Customize OpenAPI to clarify OAuth2 login uses email in 'username' field

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=settings.APP_NAME,
        version="v1",
        routes=app.routes,
        description="SEIGE Runner API OpenAPI schema",
    )
    components = openapi_schema.get("components", {})
    security_schemes = components.get("securitySchemes", {})
    if "OAuth2Email" in security_schemes:
        security_schemes["OAuth2Email"]["description"] = (
            "Use your email in the 'username' field when authorizing. "
            "The /auth/token endpoint also accepts an 'email' form field."
        )
    openapi_schema["components"] = components
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi