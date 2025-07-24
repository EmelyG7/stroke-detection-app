from pydantic import BaseModel
from typing import Optional

class PatientCreate(BaseModel):
    name: str
    age: int
    gender: str
    smoker: bool
    alcoholic: bool
    hypertension: bool
    diabetes: bool
    heart_disease: bool