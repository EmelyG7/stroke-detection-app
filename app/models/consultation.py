from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ImageAnalysisBase(BaseModel):
    image_id: str = Field(..., description="ID of the stored image")
    filename: str = Field(..., description="Original filename of the image")
    diagnosis: str = Field(default="Unknown", description="Diagnosis result for this image")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Model confidence score")
    probability: float = Field(default=0.0, ge=0.0, le=1.0, description="Stroke probability")
    url: str = Field(..., description="URL to access the image")

class ImageAnalysisCreate(ImageAnalysisBase):
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")

class ImageAnalysisResponse(ImageAnalysisBase):
    id: str = Field(..., description="Unique identifier for this analysis")
    consultation_id: str = Field(..., description="Related consultation ID")
    created_at: datetime = Field(..., description="Creation timestamp")

class ConsultationBase(BaseModel):
    patient_id: str = Field(..., description="ID of the patient")
    date: str = Field(..., description="Date of consultation in YYYY-MM-DD format")
    notes: Optional[str] = Field(default=None, description="Additional notes")
    diagnosis: str = Field(default="Unknown", description="Final diagnosis")
    probability: float = Field(default=0.0, ge=0.0, le=1.0, description="Average stroke probability")

class ConsultationCreate(ConsultationBase):
    pass

class ConsultationResponse(ConsultationBase):
    id: str = Field(..., description="Unique consultation ID")
    patient_name: Optional[str] = Field(default=None, description="Name of the patient")
    created_at: datetime = Field(..., description="Creation timestamp")
    images: List[ImageAnalysisResponse] = Field(default_factory=list, description="List of image analyses")