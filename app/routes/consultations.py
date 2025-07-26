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
# Script de debug para verificar dónde están las imágenes
from bson import ObjectId
import asyncio
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

            # Upload to GridFS with proper stream handling
            gridfs_file = await fs.upload_from_stream(
                filename=image.filename,
                source=io.BytesIO(content),  # Use BytesIO for proper stream handling
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
            logger.error(f"Error processing image {image.filename}: {str(e)}")
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
        "image_analyses": image_analyses  # Store images in consultation document
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

# En tu archivo de rutas de consultas (consultations.py)

@router.get("/{consultation_id}", response_model=ConsultationResponse)
async def get_consultation(consultation_id: str):
    try:
        validated_id = validate_object_id(consultation_id)

        # Obtener la consulta principal
        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

        # Obtener información del paciente
        patient = await db.db.patients.find_one({"_id": consultation["patient_id"]})

        processed_images = []
        fs = AsyncIOMotorGridFSBucket(db.db)

        # OPCIÓN 1: Verificar si las imágenes están en el documento de consulta
        if "image_analyses" in consultation and consultation["image_analyses"]:
            logger.info(f"Found {len(consultation['image_analyses'])} images in consultation document")

            for img in consultation["image_analyses"]:
                try:
                    # En el documento de consulta, image_id ES el ID de GridFS
                    gridfs_id = ObjectId(img["image_id"]) if isinstance(img["image_id"], str) else img["image_id"]
                    await fs.open_download_stream(gridfs_id)
                    image_url = f"/api/images/{img['image_id']}"

                    processed_images.append({
                        "id": str(img["image_id"]),  # ID de GridFS
                        "filename": img.get("filename", f"image_{str(img['image_id'])[:6]}.jpg"),
                        "diagnosis": img.get("diagnosis", "Unknown"),
                        "confidence": img.get("confidence", 0),
                        "probability": img.get("probability", 0),
                        "url": image_url,
                        "created_at": img.get("created_at", datetime.utcnow()).isoformat()
                    })

                except Exception as e:
                    logger.warning(f"Image {img['image_id']} not accessible: {str(e)}")

        # OPCIÓN 2: Si no hay imágenes en el documento, buscar en la colección separada
        else:
            logger.info("No images in consultation document, checking separate collection")
            separate_images = await db.db.image_analyses.find({"consultation_id": validated_id}).to_list(100)
            logger.info(f"Found {len(separate_images)} images in separate collection")

            for img in separate_images:
                try:
                    # IMPORTANTE: En la colección separada, necesitamos usar el campo correcto para GridFS
                    # Vamos a verificar qué campos tiene el documento
                    logger.info(f"Image document keys: {list(img.keys())}")

                    # El ID real de GridFS debería estar en img["image_id"]
                    # Pero necesitamos verificar si es un ObjectId válido
                    gridfs_id = None

                    # Intentar diferentes campos posibles
                    if "image_id" in img:
                        try:
                            gridfs_id = ObjectId(img["image_id"]) if isinstance(img["image_id"], str) else img["image_id"]
                            await fs.open_download_stream(gridfs_id)
                            logger.info(f"✅ Found image in GridFS with image_id: {gridfs_id}")
                        except Exception as e:
                            logger.warning(f"❌ image_id {img['image_id']} not found in GridFS: {str(e)}")
                            gridfs_id = None

                    # Si image_id no funciona, tal vez el ID de GridFS esté en otro campo
                    if gridfs_id is None and "gridfs_id" in img:
                        try:
                            gridfs_id = ObjectId(img["gridfs_id"]) if isinstance(img["gridfs_id"], str) else img["gridfs_id"]
                            await fs.open_download_stream(gridfs_id)
                            logger.info(f"✅ Found image in GridFS with gridfs_id: {gridfs_id}")
                        except:
                            gridfs_id = None

                    if gridfs_id:
                        processed_images.append({
                            "id": str(gridfs_id),  # CORREGIDO: Usar GridFS ID como ID principal
                            "consultation_id": str(img["consultation_id"]),
                            "image_id": str(gridfs_id),  # ID real de GridFS
                            "filename": img.get("filename", f"image_{str(gridfs_id)[:6]}.jpg"),
                            "diagnosis": img.get("diagnosis", "Unknown"),
                            "confidence": img.get("confidence", 0),
                            "probability": img.get("probability", 0),
                            "url": f"/api/images/{gridfs_id}",  # Usar el ID correcto de GridFS
                            "created_at": img.get("created_at", datetime.utcnow()).isoformat()
                        })
                    else:
                        logger.error(f"Could not find GridFS file for image document {img['_id']}")
                        # Agregar sin URL para mostrar que existe pero no está disponible
                        processed_images.append({
                            "id": str(img.get("image_id", img["_id"])),  # CORREGIDO: Usar image_id si existe
                            "consultation_id": str(img["consultation_id"]),
                            "image_id": str(img.get("image_id", "")),
                            "filename": img.get("filename", f"image_{str(img['_id'])[:6]}.jpg"),
                            "diagnosis": img.get("diagnosis", "Unknown"),
                            "confidence": img.get("confidence", 0),
                            "probability": img.get("probability", 0),
                            "url": None,  # Sin URL porque no se encontró en GridFS
                            "created_at": img.get("created_at", datetime.utcnow()).isoformat()
                        })

                except Exception as e:
                    logger.error(f"Error processing separate image {img.get('_id', 'unknown')}: {str(e)}")

        logger.info(f"Successfully processed {len(processed_images)} images for consultation {consultation_id}")

        return {
            "id": str(consultation["_id"]),
            "patient_id": str(consultation["patient_id"]),
            "patient_name": patient.get("name", "") if patient else "Unknown",
            "date": consultation.get("date", datetime.utcnow()).isoformat(),
            "notes": consultation.get("notes", ""),
            "diagnosis": consultation.get("diagnosis", "Unknown"),
            "probability": consultation.get("probability", 0),
            "created_at": consultation.get("created_at", datetime.utcnow()).isoformat(),
            "images": processed_images
        }

    except Exception as e:
        logger.error(f"Error retrieving consultation {consultation_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving consultation: {str(e)}")

@router.get("/{consultation_id}/report", response_class=StreamingResponse)
async def generate_consultation_report(consultation_id: str):
    try:
        validated_id = validate_object_id(consultation_id)

        # Get consultation with patient data
        consultation = await db.db.consultations.aggregate([
            {"$match": {"_id": validated_id}},
            {"$lookup": {
                "from": "patients",
                "localField": "patient_id",
                "foreignField": "_id",
                "as": "patient"
            }},
            {"$unwind": "$patient"}
        ]).to_list(length=1)

        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

        consultation_data = consultation[0]

        # Convert ObjectId and dates to strings
        consultation_data["consultation_id"] = str(consultation_data["_id"])
        consultation_data["patient"]["_id"] = str(consultation_data["patient"]["_id"])
        consultation_data["date"] = consultation_data["date"].isoformat()
        consultation_data["created_at"] = consultation_data["created_at"].isoformat()

        # Process images
        image_analyses = []
        if "image_analyses" in consultation_data:
            for img in consultation_data["image_analyses"]:
                img["image_id"] = str(img["image_id"])
                img["created_at"] = img.get("created_at", datetime.utcnow()).isoformat()
                image_analyses.append(img)

        # Generate PDF
        pdf_buffer = generate_consultation_pdf(consultation_data, image_analyses)

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
            status_code=500,
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

async def debug_consultation_images(consultation_id: str):
    """Debug function to check where images are stored"""

    validated_id = ObjectId(consultation_id)

    print(f"=== DEBUGGING CONSULTATION {consultation_id} ===")

    # 1. Verificar el documento de consulta
    consultation = await db.db.consultations.find_one({"_id": validated_id})
    if consultation:
        print("✅ Consultation found in database")
        print(f"Keys in consultation: {list(consultation.keys())}")

        if "image_analyses" in consultation:
            print(f"✅ image_analyses found in consultation document")
            print(f"Number of images: {len(consultation['image_analyses'])}")
            for i, img in enumerate(consultation['image_analyses']):
                print(f"  Image {i}: {img}")
        else:
            print("❌ No image_analyses in consultation document")
    else:
        print("❌ Consultation not found")
        return

    # 2. Verificar la colección image_analyses separada
    separate_images = await db.db.image_analyses.find({"consultation_id": validated_id}).to_list(100)
    if separate_images:
        print(f"✅ Found {len(separate_images)} images in separate image_analyses collection")
        for i, img in enumerate(separate_images):
            print(f"  Separate Image {i}: {img}")
    else:
        print("❌ No images found in separate image_analyses collection")

    # 3. Verificar GridFS
    fs = AsyncIOMotorGridFSBucket(db.db)
    gridfs_files = []
    async for file_info in fs.find():
        gridfs_files.append({
            "id": str(file_info._id),
            "filename": file_info.filename,
            "metadata": file_info.metadata
        })

    print(f"GridFS files found: {len(gridfs_files)}")
    for file_info in gridfs_files:
        print(f"  GridFS file: {file_info}")

    # 4. Verificar si las imágenes de la consulta existen en GridFS
    if "image_analyses" in consultation:
        for img in consultation["image_analyses"]:
            image_id = img["image_id"]
            try:
                grid_out = await fs.open_download_stream(ObjectId(image_id))
                print(f"✅ Image {image_id} exists in GridFS")
            except Exception as e:
                print(f"❌ Image {image_id} NOT found in GridFS: {str(e)}")

# Función para usar en el endpoint
@router.get("/{consultation_id}/debug")
async def debug_consultation(consultation_id: str):
    """Debug endpoint to check consultation images"""
    try:
        await debug_consultation_images(consultation_id)
        return {"message": "Check server logs for debug information"}
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        return {"error": str(e)}

# Agregar este endpoint temporal para debug
@router.get("/{consultation_id}/debug-images")
async def debug_images(consultation_id: str):
    """Endpoint temporal para debuggear imágenes"""
    try:
        validated_id = validate_object_id(consultation_id)

        # 1. Obtener consulta
        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            return {"error": "Consultation not found"}

        result = {
            "consultation_id": consultation_id,
            "consultation_keys": list(consultation.keys()),
            "has_image_analyses_in_doc": "image_analyses" in consultation,
            "image_analyses_in_doc": [],
            "separate_image_analyses": [],
            "gridfs_files": []
        }

        # 2. Verificar imágenes en documento
        if "image_analyses" in consultation:
            result["image_analyses_in_doc"] = consultation["image_analyses"]
            result["image_count_in_doc"] = len(consultation["image_analyses"])

        # 3. Verificar colección separada
        separate_images = await db.db.image_analyses.find({"consultation_id": validated_id}).to_list(100)
        result["separate_image_analyses"] = [
            {
                "id": str(img["_id"]),
                "image_id": str(img["image_id"]),
                "filename": img.get("filename"),
                "consultation_id": str(img["consultation_id"])
            } for img in separate_images
        ]
        result["separate_image_count"] = len(separate_images)

        # 4. Verificar GridFS
        fs = AsyncIOMotorGridFSBucket(db.db)
        gridfs_files = []
        async for file_info in fs.find():
            gridfs_files.append({
                "id": str(file_info._id),
                "filename": file_info.filename,
                "length": file_info.length,
                "metadata": file_info.metadata
            })
        result["gridfs_files"] = gridfs_files
        result["gridfs_count"] = len(gridfs_files)

        return result

    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        return {"error": str(e)}

# Agrega este endpoint temporal para ver la estructura exacta
@router.get("/{consultation_id}/debug-structure")
async def debug_image_structure(consultation_id: str):
    """Debug endpoint para ver la estructura exacta de las imágenes"""
    try:
        validated_id = validate_object_id(consultation_id)

        # 1. Obtener consulta
        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            return {"error": "Consultation not found"}

        # 2. Obtener imágenes de la colección separada
        separate_images = await db.db.image_analyses.find({"consultation_id": validated_id}).to_list(100)

        # 3. Obtener todos los archivos de GridFS para comparar
        fs = AsyncIOMotorGridFSBucket(db.db)
        gridfs_files = []
        async for file_info in fs.find():
            gridfs_files.append({
                "gridfs_id": str(file_info._id),
                "filename": file_info.filename,
                "length": file_info.length,
                "metadata": file_info.metadata
            })

        return {
            "consultation_id": consultation_id,
            "consultation_has_images": "image_analyses" in consultation,
            "consultation_images": consultation.get("image_analyses", []),
            "separate_images_count": len(separate_images),
            "separate_images": [
                {
                    "document_id": str(img["_id"]),
                    "image_id": str(img.get("image_id", "NO_IMAGE_ID")),
                    "filename": img.get("filename", "NO_FILENAME"),
                    "consultation_id": str(img.get("consultation_id", "NO_CONSULTATION_ID")),
                    "all_keys": list(img.keys()),
                    "full_document": img  # Para ver todo el documento
                } for img in separate_images
            ],
            "gridfs_files_count": len(gridfs_files),
            "gridfs_files": gridfs_files
        }

    except Exception as e:
        logger.error(f"Debug structure error: {str(e)}")
        return {"error": str(e)}