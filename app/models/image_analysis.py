from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from bson import ObjectId

class ImageAnalysis(BaseModel):
    id: str
    consultation_id: str
    image_id: str
    diagnosis: str
    confidence: float
    probability: float
    created_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True

class ConsultationResponse(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    date: str
    notes: Optional[str]
    diagnosis: str
    probability: float
    created_at: str
    images: List[ImageAnalysis]