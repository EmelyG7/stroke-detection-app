import io
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, status
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from starlette.responses import StreamingResponse
from app.config import settings
from app.models.consultation import ConsultationCreate, ConsultationResponse, ImageAnalysisResponse
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
                "url": f"{settings.API_BASE_URL}/api/images/{img['image_id']}"
            } for img in image_analyses]
        }

        return jsonable_encoder(response)
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

@router.get(
    "/",
    response_model=List[ConsultationResponse],
    summary="List all consultations",
    description="Returns a list of all consultations with patient information"
)
async def get_consultations(limit: int = 100, skip: int = 0):
    try:
        if db.db is None:
            await db.connect()

        pipeline = [
            {
                "$lookup": {
                    "from": "patients",
                    "localField": "patient_id",
                    "foreignField": "_id",
                    "as": "patient"
                }
            },
            {"$unwind": "$patient"},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$project": {
                    "id": {"$toString": "$_id"},
                    "patient_id": {"$toString": "$patient_id"},
                    "patient_name": "$patient.name",
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                    "notes": {"$ifNull": ["$notes", ""]},
                    "diagnosis": {"$ifNull": ["$diagnosis", "Unknown"]},
                    "probability": {"$ifNull": ["$probability", 0]},
                    "images": {
                        "$map": {
                            "input": {"$ifNull": ["$image_analyses", []]},
                            "as": "img",
                            "in": {
                                "id": {"$toString": "$$img.image_id"},
                                "filename": "$$img.filename",
                                "diagnosis": {"$ifNull": ["$$img.diagnosis", "Unknown"]},
                                "confidence": {"$ifNull": ["$$img.confidence", 0]},
                                "probability": {"$ifNull": ["$$img.probability", 0]},
                                "url": f"{settings.API_BASE_URL}/api/images/$$img.image_id"
                            }
                        }
                    }
                }
            }
        ]

        consultations = await db.db.consultations.aggregate(pipeline).to_list(length=None)

        return {
            "success": True,
            "data": consultations,
            "message": "Consultations retrieved successfully"
        }
    except Exception as e:
        logger.error(f"Error retrieving consultations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve consultations"
            }
        )

@router.get(
    "/{consultation_id}",
    response_model=ConsultationResponse,
    summary="Get consultation details",
    description="Returns detailed information about a specific consultation"
)
async def get_consultation(consultation_id: str):
    """
    Obtiene los detalles completos de una consulta médica específica

    Args:
        consultation_id: ID de la consulta a recuperar

    Returns:
        ConsultationResponse: Detalles completos de la consulta
    """
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
                    "notes": {"$ifNull": ["$notes", ""]},
                    "diagnosis": {"$ifNull": ["$diagnosis", "Unknown"]},
                    "probability": {"$ifNull": ["$probability", 0]},
                    "created_at": {
                        "$dateToString": {
                            "format": "%Y-%m-%dT%H:%M:%SZ",
                            "date": "$created_at"
                        }
                    },
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
                                }
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
    """
    Genera un reporte PDF de la consulta médica

    Args:
        consultation_id: ID de la consulta para generar el reporte

    Returns:
        StreamingResponse: PDF del reporte de consulta
    """
    try:
        validated_id = validate_object_id(consultation_id)
        if db.db is None:
            await db.connect()

        # Obtener datos de la consulta
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

        # Serializar ObjectIds
        consultation_data["consultation_id"] = str(consultation_data["_id"])
        consultation_data["patient_id"] = str(consultation_data["patient_id"])
        consultation_data["patient"]["_id"] = str(consultation_data["patient"]["_id"])

        # Serializar imágenes si existen
        if "image_analyses" in consultation_data:
            for img in consultation_data["image_analyses"]:
                img["image_id"] = str(img["image_id"])

        # Generar PDF
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
    """
    Elimina una consulta médica y sus imágenes asociadas

    Args:
        consultation_id: ID de la consulta a eliminar

    Returns:
        dict: Mensaje de confirmación
    """
    try:
        validated_id = validate_object_id(consultation_id)
        if db.db is None:
            await db.connect()

        # Obtener consulta para eliminar imágenes asociadas
        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found"
            )

        # Eliminar imágenes de GridFS
        fs = await get_gridfs()
        if "image_analyses" in consultation:
            for image in consultation["image_analyses"]:
                try:
                    await fs.delete(ObjectId(image["image_id"]))
                except Exception as e:
                    logger.error(f"Error deleting image {image['image_id']}: {str(e)}")

        # Eliminar la consulta
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