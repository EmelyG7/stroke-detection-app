from fastapi import APIRouter, HTTPException, status
from bson import ObjectId
from app.db import db
from app.models.patient import Patient
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import logging

router = APIRouter(
    prefix="",
    tags=["patients"],
    responses={404: {"description": "Not found"}}
)

logger = logging.getLogger(__name__)

def serialize_object_ids(data):
    """Convierte todos los ObjectId a strings en una estructura de datos"""
    if isinstance(data, dict):
        return {k: serialize_object_ids(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_object_ids(v) for v in data]
    elif isinstance(data, ObjectId):
        return str(data)
    return data

def serialize_patient(patient):
    """Helper function to serialize patient data"""
    if not patient:
        return None

    # Primero aplicamos serialize_object_ids para manejar cualquier ObjectId
    patient_data = serialize_object_ids(dict(patient))

    # Aseguramos el formato de las fechas
    if "created_at" in patient_data:
        patient_data["created_at"] = patient_data["created_at"].isoformat()
    if "updated_at" in patient_data:
        patient_data["updated_at"] = patient_data["updated_at"].isoformat()

    # Renombramos _id a id si existe
    if "_id" in patient_data:
        patient_data["id"] = patient_data.pop("_id")

    return patient_data

@router.get("/", response_model=dict)
async def get_patients():
    try:
        if db.db is None:
            await db.connect()
        patients = await db.db.patients.find().to_list(length=None)
        return {
            "success": True,
            "data": jsonable_encoder([serialize_patient(p) for p in patients])
        }
    except Exception as e:
        logger.error(f"Error retrieving patients: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(e)}
        )

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_patient(patient: Patient):
    try:
        if db.db is None:
            await db.connect()
        patient_data = patient.dict(exclude_unset=True)
        patient_data["created_at"] = datetime.utcnow()
        result = await db.db.patients.insert_one(patient_data)
        created_patient = await db.db.patients.find_one({"_id": result.inserted_id})
        return {
            "success": True,
            "data": jsonable_encoder(serialize_patient(created_patient))
        }
    except Exception as e:
        logger.error(f"Error creating patient: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(e)}
        )

@router.get("/{id}", response_model=dict)
async def get_patient(id: str):
    try:
        if not ObjectId.is_valid(id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "error": "Invalid patient ID"}
            )
        if db.db is None:
            await db.connect()
        patient = await db.db.patients.find_one({"_id": ObjectId(id)})
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"success": False, "error": "Patient not found"}
            )
        return {
            "success": True,
            "data": jsonable_encoder(serialize_patient(patient))
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving patient: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(e)}
        )

@router.put("/{id}", response_model=dict)
async def update_patient(id: str, patient: Patient):
    try:
        if not ObjectId.is_valid(id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "error": "Invalid patient ID"}
            )
        if db.db is None:
            await db.connect()

        patient_data = patient.dict(exclude_unset=True)
        patient_data["updated_at"] = datetime.utcnow()

        result = await db.db.patients.update_one(
            {"_id": ObjectId(id)},
            {"$set": patient_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"success": False, "error": "Patient not found or no changes made"}
            )

        updated_patient = await db.db.patients.find_one({"_id": ObjectId(id)})
        return {
            "success": True,
            "data": jsonable_encoder(serialize_patient(updated_patient))
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating patient: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(e)}
        )

@router.delete("/{id}", response_model=dict)
async def delete_patient(id: str):
    try:
        if not ObjectId.is_valid(id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "error": "Invalid patient ID"}
            )
        if db.db is None:
            await db.connect()

        result = await db.db.patients.delete_one({"_id": ObjectId(id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"success": False, "error": "Patient not found"}
            )

        return {
            "success": True,
            "data": {"id": id}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting patient: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(e)}
        )