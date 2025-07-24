from pydantic import BaseModel
from typing import Optional

class ImageAnalysis(BaseModel):
    consultation_id: str
    image_id: str
    filename: str
    diagnosis: str
    confidence: float
    probability: float
    url: str
    created_at: Optional[str] = None