from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.db.session import engine


app = FastAPI(
    title="MADHU API",
    description="AI Workforce Platform API",
    version="0.1.0",
)

app.include_router(auth_router)


@app.get("/")
def root():
    return {
        "name": "MADHU",
        "message": "AI Employees. Real Work.",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/api/test")
def test_connection():
    return {
        "message": "Frontend connected to MADHU backend successfully!",
        "backend": "FastAPI",
        "status": "connected",
    }
@app.get("/api/db-test")
def database_test():
    try:
        with engine.connect() as connection:
            return {
                "database": "PostgreSQL",
                "status": "connected",
                "message": "MADHU database connection successful!",
            }
    except Exception as e:
        return {
            "database": "PostgreSQL",
            "status": "error",
            "message": str(e),
        }