from pydantic import BaseModel
from typing import Optional, List

class ImageAnalysisCreate(BaseModel):
    image_id: str
    filename: str
    diagnosis: str
    confidence: float
    probability: float
    url: str

class ConsultationCreate(BaseModel):
    patient_id: str
    date: str
    notes: Optional[str] = None
    images: List[ImageAnalysisCreate]