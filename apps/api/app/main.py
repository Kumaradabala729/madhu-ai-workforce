
from fastapi import FastAPI
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.db.session import engine
from app.api.organizations import router as organizations_router


app = FastAPI(
    title="MADHU API",
    version="1.0.0",
)


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(organizations_router)


@app.get("/")
def root():
    return {
        "message": "MADHU API is running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


@app.get("/api/test")
def test_api():
    return {
        "message": "MADHU API connection successful",
    }


@app.get("/api/db-test")
def database_test():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "message": "Database connection successful",
    }

