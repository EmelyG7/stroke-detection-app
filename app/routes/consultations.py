import io
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, status
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from starlette.responses import StreamingResponse
from app.config import settings
from app.models.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    ConsultationListResponse,
    ImageAnalysisResponse
)
from app.utils.pdf import generate_consultation_pdf
from app.utils.predict import predict_stroke
from app.utils.validators import validate_object_id
from app.db import db
import logging
from fastapi.encoders import jsonable_encoder

router = APIRouter(
    prefix="",
    tags=["consultations"],
    responses={404: {"description": "Not found"}}
)

logger = logging.getLogger(__name__)

async def get_gridfs():
    if db.db is None:
        await db.connect()
    return AsyncIOMotorGridFSBucket(db.db, bucket_name="fs")

@router.post(
    "/",
    response_model=ConsultationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new consultation",
    description="Creates a new consultation with image analysis for stroke detection"
)
async def create_consultation(
        patient_id: str,
        date: str,
        notes: Optional[str] = None,
        images: List[UploadFile] = File(...),
):
    if not images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image is required"
        )
    try:
        validated_patient_id = validate_object_id(patient_id)
        consultation_date = datetime.fromisoformat(date)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    image_analyses = []
    probabilities = []
    fs = await get_gridfs()

    for image in images:
        if not image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {image.filename} is not an image"
            )
        try:
            content = await image.read()
            prediction = await predict_stroke(content)
            gridfs_file = await fs.upload_from_stream(
                filename=image.filename,
                source=content,
                metadata={
                    "content_type": image.content_type,
                    "uploaded_at": datetime.utcnow()
                }
            )

            image_analysis = {
                "image_id": str(gridfs_file),
                "filename": image.filename,
                "diagnosis": prediction["diagnosis"],
                "confidence": prediction["confidence"],
                "probability": prediction["probability"],
                "created_at": datetime.utcnow()
            }
            image_analyses.append(image_analysis)
            probabilities.append(prediction["probability"])
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing image {image.filename}: {str(e)}"
            )

    avg_probability = sum(probabilities) / len(probabilities) if probabilities else 0
    final_diagnosis = "Stroke" if avg_probability >= 0.5 else "Normal"

    consultation_data = {
        "patient_id": validated_patient_id,
        "date": consultation_date,
        "notes": notes,
        "diagnosis": final_diagnosis,
        "probability": avg_probability,
        "created_at": datetime.utcnow(),
        "image_analyses": image_analyses
    }

    try:
        result = await db.db.consultations.insert_one(consultation_data)
        created = await db.db.consultations.find_one({"_id": result.inserted_id})

        # Get patient info
        patient = await db.db.patients.find_one({"_id": validated_patient_id})

        # Build response
        response = {
            "id": str(result.inserted_id),
            "patient_id": str(validated_patient_id),
            "patient_name": patient.get("name", "") if patient else "",
            "date": consultation_date.isoformat(),
            "notes": notes,
            "diagnosis": final_diagnosis,
            "probability": avg_probability,
            "created_at": consultation_data["created_at"].isoformat(),
            "images": [{
                "id": img["image_id"],
                "filename": img["filename"],
                "diagnosis": img["diagnosis"],
                "confidence": img["confidence"],
                "probability": img["probability"],
                "url": f"{settings.API_BASE_URL}/api/images/{img['image_id']}",
                "created_at": img["created_at"].isoformat()
            } for img in image_analyses]
        }

        return jsonable_encoder(response)
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

@router.get("/", response_model=List[dict])
async def get_consultations(limit: int = 100, skip: int = 0):
    try:
        if db.db is None:
            await db.connect()

        # First get raw consultations with patient data
        consultations = await db.db.consultations.find().skip(skip).limit(limit).sort("created_at", -1).to_list(length=None)

        # Process each consultation to ensure proper serialization
        result = []
        for consultation in consultations:
            # Get patient data
            patient = await db.db.patients.find_one({"_id": consultation["patient_id"]})

            # Process images
            images = []
            if "image_analyses" in consultation:
                for img in consultation["image_analyses"]:
                    images.append({
                        "id": str(img["image_id"]),
                        "filename": img["filename"],
                        "diagnosis": img.get("diagnosis", "Unknown"),
                        "confidence": img.get("confidence", 0),
                        "probability": img.get("probability", 0),
                        "url": f"{settings.API_BASE_URL}/api/images/{img['image_id']}",
                        "created_at": img["created_at"].isoformat() if "created_at" in img else None
                    })

            # Build the consultation response
            consultation_data = {
                "id": str(consultation["_id"]),
                "patient_id": str(consultation["patient_id"]),
                "patient": {
                    "id": str(patient["_id"]) if patient else None,
                    "name": patient.get("name", "") if patient else "",
                    "age": patient.get("age", 0) if patient else 0,
                    "gender": patient.get("gender", "") if patient else "",
                    "smoker": patient.get("smoker", False) if patient else False,
                    "alcoholic": patient.get("alcoholic", False) if patient else False,
                    "hypertension": patient.get("hypertension", False) if patient else False,
                    "diabetes": patient.get("diabetes", False) if patient else False,
                    "heart_disease": patient.get("heart_disease", False) if patient else False,
                    "created_at": patient["created_at"].isoformat() if patient and "created_at" in patient else None
                },
                "date": consultation["date"].isoformat(),
                "created_at": consultation["created_at"].isoformat(),
                "notes": consultation.get("notes", ""),
                "diagnosis": consultation.get("diagnosis", "Unknown"),
                "probability": consultation.get("probability", 0),
                "images": images
            }
            result.append(consultation_data)

        return result

    except Exception as e:
        logger.error(f"Error retrieving consultations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving consultations: {str(e)}"
        )

@router.get(
    "/{consultation_id}",
    response_model=ConsultationResponse,
    summary="Get consultation details",
    description="Returns detailed information about a specific consultation"
)
async def get_consultation(consultation_id: str):
    try:
        validated_id = validate_object_id(consultation_id)
        if db.db is None:
            await db.connect()

        pipeline = [
            {"$match": {"_id": validated_id}},
            {
                "$lookup": {
                    "from": "patients",
                    "localField": "patient_id",
                    "foreignField": "_id",
                    "as": "patient"
                }
            },
            {"$unwind": "$patient"},
            {
                "$project": {
                    "id": {"$toString": "$_id"},
                    "patient_id": {"$toString": "$patient_id"},
                    "patient_name": "$patient.name",
                    "patient_age": "$patient.age",
                    "patient_gender": "$patient.gender",
                    "date": {
                        "$dateToString": {
                            "format": "%Y-%m-%dT%H:%M:%SZ",
                            "date": "$date"
                        }
                    },
                    "created_at": {
                        "$dateToString": {
                            "format": "%Y-%m-%dT%H:%M:%SZ",
                            "date": "$created_at"
                        }
                    },
                    "notes": {"$ifNull": ["$notes", ""]},
                    "diagnosis": {"$ifNull": ["$diagnosis", "Unknown"]},
                    "probability": {"$ifNull": ["$probability", 0]},
                    "images": {
                        "$map": {
                            "input": {"$ifNull": ["$image_analyses", []]},
                            "as": "img",
                            "in": {
                                "id": {"$toString": "$$img.image_id"},
                                "image_id": {"$toString": "$$img.image_id"},
                                "filename": "$$img.filename",
                                "diagnosis": {"$ifNull": ["$$img.diagnosis", "Unknown"]},
                                "confidence": {"$ifNull": ["$$img.confidence", 0]},
                                "probability": {"$ifNull": ["$$img.probability", 0]},
                                "url": {
                                    "$concat": [
                                        settings.API_BASE_URL,
                                        "/api/images/",
                                        {"$toString": "$$img.image_id"}
                                    ]
                                },
                                "consultation_id": {"$toString": "$_id"},
                                "created_at": {
                                    "$dateToString": {
                                        "format": "%Y-%m-%dT%H:%M:%SZ",
                                        "date": "$$img.created_at"
                                    }
                                } if "$$img.created_at" else None
                            }
                        }
                    }
                }
            }
        ]

        consultation = await db.db.consultations.aggregate(pipeline).to_list(length=1)

        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found"
            )

        return consultation[0]

    except Exception as e:
        logger.error(f"Error retrieving consultation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving consultation: {str(e)}"
        )

@router.get(
    "/{consultation_id}/report",
    response_class=StreamingResponse,
    summary="Generate consultation report",
    description="Generates a PDF report for the consultation"
)
async def generate_consultation_report(consultation_id: str):
    try:
        validated_id = validate_object_id(consultation_id)
        if db.db is None:
            await db.connect()

        consultation = await db.db.consultations.aggregate([
            {"$match": {"_id": validated_id}},
            {
                "$lookup": {
                    "from": "patients",
                    "localField": "patient_id",
                    "foreignField": "_id",
                    "as": "patient"
                }
            },
            {"$unwind": "$patient"}
        ]).to_list(length=1)

        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found"
            )

        consultation_data = consultation[0]

        consultation_data["consultation_id"] = str(consultation_data["_id"])
        consultation_data["patient_id"] = str(consultation_data["patient_id"])
        consultation_data["patient"]["_id"] = str(consultation_data["patient"]["_id"])

        if "image_analyses" in consultation_data:
            for img in consultation_data["image_analyses"]:
                img["image_id"] = str(img["image_id"])

        pdf_buffer = generate_consultation_pdf(consultation_data, consultation_data.get("image_analyses", []))

        return StreamingResponse(
            io.BytesIO(pdf_buffer),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=consultation_report_{consultation_id}.pdf"
            }
        )
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating report: {str(e)}"
        )

@router.delete(
    "/{consultation_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a consultation",
    description="Deletes a consultation and its associated images"
)
async def delete_consultation(consultation_id: str):
    try:
        validated_id = validate_object_id(consultation_id)
        if db.db is None:
            await db.connect()

        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found"
            )

        fs = await get_gridfs()
        if "image_analyses" in consultation:
            for image in consultation["image_analyses"]:
                try:
                    await fs.delete(ObjectId(image["image_id"]))
                except Exception as e:
                    logger.error(f"Error deleting image {image['image_id']}: {str(e)}")

        result = await db.db.consultations.delete_one({"_id": validated_id})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found"
            )

        return {"success": True, "message": "Consultation deleted successfully"}

    except Exception as e:
        logger.error(f"Error deleting consultation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting consultation: {str(e)}"
        )