from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging

from app.config import settings
from app.db import db

# Disable TensorFlow warnings
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Suppress TensorFlow info messages

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Stroke Detection API",
    description="API para el sistema de detección de stroke mediante imágenes médicas",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    redirect_slashes=True
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Especifica tu frontend exacto
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]  # Añade esto
)

# Import and include routers AFTER app creation
from app.routes.dashboard import router as dashboard_router
from app.routes.patients import router as patients_router
from app.routes.consultations import router as consultations_router
from app.routes.images import router as images_router
from app.routes.users import router as users_router

app.include_router(dashboard_router, prefix="/api/dashboard")
app.include_router(patients_router, prefix="/api/patients")
app.include_router(consultations_router, prefix="/api/consultations")
app.include_router(images_router, prefix="/api/images")
app.include_router(users_router, prefix="/api/users")

@app.on_event("startup")
async def startup():
    try:
        from app.utils.predict import load_stroke_model
        model_path = os.path.join("models", "best_fold_5_el_mejor_de_los_5_folds.h5")
        load_stroke_model(model_path)
        logger.info("Model loaded successfully!")

        # Connect to database
        await db.connect()
        logger.info(f"Connected to MongoDB database: {settings.MONGODB_NAME}")
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown():
    try:
        if db.client:  # Only try to close if client exists
            await db.close()
            logger.info("Database connection closed.")
    except Exception as e:
        logger.error(f"Error closing database connection: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Stroke Detection API"}

for route in app.routes:
    print(f"{route.path} -> {route.name}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        log_level="info"
    )