import logging
import sys
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
import uvicorn
from app.api.endpoints import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("hr_pro.main")

app = FastAPI(
    title="HR-Pro API",
    description="Microservice API for HR-Pro core logic and parser orchestration.",
    version="1.0.0",
)

# Include the endpoints
app.include_router(api_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    logger.info("Starting HR-Pro API server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
