from pydantic import BaseModel, Field
from typing import Optional

class Patient(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique patient ID")
    name: str = Field(..., min_length=2, max_length=100, description="Patient full name")
    age: int = Field(..., gt=0, lt=120, description="Patient age in years")
    gender: str = Field(..., description="Patient gender")
    smoker: bool = Field(default=False, description="Smoking status")
    alcoholic: bool = Field(default=False, description="Alcohol consumption status")
    hypertension: bool = Field(default=False, description="Hypertension status")
    diabetes: bool = Field(default=False, description="Diabetes status")
    heart_disease: bool = Field(default=False, description="Heart disease status")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")