# app/models/consultation.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Union
from datetime import datetime

class ImageAnalysisBase(BaseModel):
    image_id: str = Field(..., description="ID of the stored image in GridFS")
    filename: str = Field(..., description="Original filename of the image")
    diagnosis: str = Field(default="Unknown", description="Diagnosis result for this image")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Model confidence score")
    probability: float = Field(default=0.0, ge=0.0, le=1.0, description="Stroke probability")
    url: str = Field(..., description="URL to access the image")

class ImageAnalysisCreate(ImageAnalysisBase):
    consultation_id: str = Field(..., description="Related consultation ID")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="Creation timestamp")

class ImageAnalysisResponse(ImageAnalysisBase):
    id: str = Field(..., description="Unique identifier (same as image_id)")
    consultation_id: str = Field(..., description="Related consultation ID")
    created_at: Union[datetime, str] = Field(..., description="Creation timestamp")

    @validator('created_at', pre=True)
    def parse_created_at(cls, v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                return datetime.utcnow()
        return v if isinstance(v, datetime) else datetime.utcnow()

    class Config:
        # Allow datetime serialization
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class PatientInfo(BaseModel):
    """Patient information for consultation responses"""
    id: Optional[str] = None
    name: str = ""
    age: int = 0
    gender: str = ""
    smoker: bool = False
    alcoholic: bool = False
    hypertension: bool = False
    diabetes: bool = False
    heart_disease: bool = False
    created_at: Optional[str] = None

class ConsultationBase(BaseModel):
    patient_id: str = Field(..., description="ID of the patient")
    date: str = Field(..., description="Date of consultation in YYYY-MM-DD format")
    notes: Optional[str] = Field(default=None, description="Additional notes")
    diagnosis: str = Field(default="Unknown", description="Final diagnosis")
    probability: float = Field(default=0.0, ge=0.0, le=1.0, description="Average stroke probability")

    @validator('date')
    def validate_date_format(cls, v):
        try:
            # Try to parse the date to ensure it's valid
            datetime.fromisoformat(v.split('T')[0])
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format or ISO format')

    @validator('notes', pre=True)
    def clean_notes(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v.strip() if isinstance(v, str) else v

class ConsultationCreate(ConsultationBase):
    """Model for creating a new consultation"""
    pass

class ConsultationResponse(ConsultationBase):
    """Model for consultation API responses"""
    id: str = Field(..., description="Unique consultation ID")
    patient_name: Optional[str] = Field(default=None, description="Name of the patient")
    created_at: Union[datetime, str] = Field(..., description="Creation timestamp")
    images: List[ImageAnalysisResponse] = Field(default_factory=list, description="List of image analyses")

    @validator('created_at', pre=True)
    def parse_created_at(cls, v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                return datetime.utcnow()
        return v if isinstance(v, datetime) else datetime.utcnow()

    class Config:
        # Allow datetime serialization
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ConsultationWithPatient(ConsultationResponse):
    """Extended consultation model with full patient information"""
    patient: PatientInfo = Field(..., description="Full patient information")

class ConsultationListResponse(BaseModel):
    """Wrapper for consultation list responses"""
    success: bool = Field(True, description="Indicates if the request was successful")
    data: List[Union[ConsultationResponse, ConsultationWithPatient]] = Field(..., description="List of consultations")
    message: Optional[str] = Field(None, description="Optional message")
    total: Optional[int] = Field(None, description="Total number of consultations")
    page: Optional[int] = Field(None, description="Current page number")
    limit: Optional[int] = Field(None, description="Results per page")

class ConsultationUpdateRequest(BaseModel):
    """Model for updating consultation data"""
    patient_id: str = Field(..., description="ID of the patient")
    date: str = Field(..., description="Date of consultation in YYYY-MM-DD format")
    notes: Optional[str] = Field(default=None, description="Additional notes")

    @validator('date')
    def validate_date_format(cls, v):
        try:
            datetime.fromisoformat(v.split('T')[0])
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format or ISO format')

    @validator('notes', pre=True)
    def clean_notes(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v.strip() if isinstance(v, str) else v

class ConsultationUpdateResponse(BaseModel):
    """Response model for consultation updates"""
    success: bool = Field(True, description="Indicates if the update was successful")
    message: str = Field(..., description="Success or error message")
    data: Optional[dict] = Field(None, description="Updated consultation data")

# Error response models
class ErrorDetail(BaseModel):
    """Individual error detail"""
    loc: List[Union[str, int]] = Field(..., description="Location of the error")
    msg: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type")

class ValidationErrorResponse(BaseModel):
    """Response model for validation errors"""
    detail: List[ErrorDetail] = Field(..., description="List of validation errors")

class APIErrorResponse(BaseModel):
    """Generic API error response"""
    detail: str = Field(..., description="Error message")
    error_type: Optional[str] = Field(None, description="Type of error")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }