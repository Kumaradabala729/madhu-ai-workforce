from fastapi import FastAPI

app = FastAPI(
    title="MADHU API",
    description="AI Workforce Platform API",
    version="0.1.0",
)


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