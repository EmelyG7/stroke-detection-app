import io
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
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
        patient_id: str = Form(..., description="Patient ID"),
        date: str = Form(..., description="Consultation date in YYYY-MM-DD format"),
        notes: Optional[str] = Form(None, description="Optional consultation notes"),
        images: List[UploadFile] = File(..., description="DWI images for analysis"),
):
    """
    Create a new consultation with image analysis.

    - **patient_id**: The ID of the patient
    - **date**: Date of consultation in YYYY-MM-DD format
    - **notes**: Optional medical notes
    - **images**: List of DWI images for stroke detection
    """

    # Log received data for debugging
    logger.info(f"Creating consultation - Patient ID: {patient_id}, Date: {date}, Images: {len(images)}")

    # Validate inputs
    if not patient_id or not patient_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Patient ID is required"
        )

    if not date or not date.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date is required"
        )

    if not images or len(images) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image is required"
        )

    # Validate image files
    for image in images:
        if not image.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All uploaded files must have filenames"
            )

        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {image.filename} is not a valid image"
            )

    try:
        # Validate patient ID format
        validated_patient_id = validate_object_id(patient_id.strip())

        # Validate date format
        consultation_date = datetime.fromisoformat(date.strip())

        # Check if patient exists
        patient = await db.db.patients.find_one({"_id": validated_patient_id})
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found"
            )

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid input: {str(e)}"
        )

    # Create consultation document first to get consultation_id
    consultation_data = {
        "patient_id": validated_patient_id,
        "date": consultation_date,
        "notes": notes.strip() if notes and notes.strip() else None,
        "diagnosis": "Processing...",  # Temporary value
        "probability": 0.0,  # Temporary value
        "created_at": datetime.utcnow(),
        "image_analyses": []  # Will be populated below
    }

    try:
        # Insert consultation to get ID
        result = await db.db.consultations.insert_one(consultation_data)
        consultation_id = result.inserted_id
        logger.info(f"Created consultation {consultation_id}")

    except Exception as e:
        logger.error(f"Database error creating consultation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    image_analyses = []
    probabilities = []
    fs = await get_gridfs()

    # Process each image
    for idx, image in enumerate(images):
        try:
            logger.info(f"Processing image {idx + 1}/{len(images)}: {image.filename}")

            # Read image content
            content = await image.read()

            if len(content) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Image {image.filename} is empty"
                )

            # Check file size (10MB limit)
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Image {image.filename} is too large (max 10MB)"
                )

            # Predict stroke
            prediction = await predict_stroke(content)

            # Upload to GridFS
            gridfs_file = await fs.upload_from_stream(
                filename=image.filename,
                source=io.BytesIO(content),
                metadata={
                    "content_type": image.content_type,
                    "uploaded_at": datetime.utcnow(),
                    "size": len(content),
                    "consultation_id": str(consultation_id)  # Add consultation reference
                }
            )

            # Create image analysis record - with required fields for Pydantic model
            image_analysis = {
                "image_id": str(gridfs_file),
                "consultation_id": str(consultation_id),  # Required by Pydantic model
                "filename": image.filename,
                "diagnosis": prediction["diagnosis"],
                "confidence": prediction["confidence"],
                "probability": prediction["probability"],
                "created_at": datetime.utcnow()
            }

            image_analyses.append(image_analysis)
            probabilities.append(prediction["probability"])

            logger.info(f"Successfully processed image {image.filename}")

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            await db.db.consultations.delete_one({"_id": consultation_id})
            raise
        except Exception as e:
            logger.error(f"Error processing image {image.filename}: {str(e)}", exc_info=True)
            # Clean up consultation if image processing fails
            await db.db.consultations.delete_one({"_id": consultation_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing image {image.filename}: {str(e)}"
            )

    # Calculate final diagnosis
    avg_probability = sum(probabilities) / len(probabilities) if probabilities else 0
    final_diagnosis = "Stroke" if avg_probability >= 0.5 else "Normal"

    logger.info(f"Final diagnosis: {final_diagnosis} (probability: {avg_probability})")

    # Update consultation with final results
    try:
        update_result = await db.db.consultations.update_one(
            {"_id": consultation_id},
            {
                "$set": {
                    "diagnosis": final_diagnosis,
                    "probability": avg_probability,
                    "image_analyses": image_analyses
                }
            }
        )

        if update_result.modified_count == 0:
            logger.error("Failed to update consultation with results")
            await db.db.consultations.delete_one({"_id": consultation_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update consultation with results"
            )

        # Build response with proper structure matching Pydantic models
        response_images = []
        for img in image_analyses:
            response_images.append({
                "id": img["image_id"],  # This becomes the id field
                "image_id": img["image_id"],  # Required by model
                "consultation_id": img["consultation_id"],  # Required by model
                "filename": img["filename"],
                "diagnosis": img["diagnosis"],
                "confidence": img["confidence"],
                "probability": img["probability"],
                "url": f"{settings.API_BASE_URL}/api/images/{img['image_id']}",
                "created_at": img["created_at"]
            })

        response = ConsultationResponse(
            id=str(consultation_id),
            patient_id=str(validated_patient_id),
            patient_name=patient.get("name", ""),
            date=consultation_date.isoformat(),
            notes=consultation_data["notes"],
            diagnosis=final_diagnosis,
            probability=avg_probability,
            created_at=consultation_data["created_at"],
            images=response_images
        )

        return response

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Database error updating consultation: {str(e)}", exc_info=True)
        # Clean up consultation if update fails
        await db.db.consultations.delete_one({"_id": consultation_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

@router.get("/", response_model=List[dict])
async def get_consultations(limit: int = 100, skip: int = 0):
    """
    Get all consultations with patient information and images
    """
    try:
        if db.db is None:
            await db.connect()

        # Get consultations with patient data
        consultations = await db.db.consultations.find().skip(skip).limit(limit).sort("created_at", -1).to_list(length=None)

        # Process each consultation to ensure proper serialization
        result = []
        for consultation in consultations:
            # Get patient data
            patient = await db.db.patients.find_one({"_id": consultation["patient_id"]})

            # Process images with proper structure
            images = []
            if "image_analyses" in consultation:
                for img in consultation["image_analyses"]:
                    images.append({
                        "id": str(img["image_id"]),
                        "image_id": str(img["image_id"]),  # Required field
                        "consultation_id": str(consultation["_id"]),  # Required field
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

@router.get("/{consultation_id}", response_model=ConsultationResponse)
async def get_consultation(consultation_id: str):
    """
    Get a specific consultation by ID
    """
    try:
        validated_id = validate_object_id(consultation_id)

        # Get the consultation
        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

        # Get patient information
        patient = await db.db.patients.find_one({"_id": consultation["patient_id"]})

        processed_images = []
        fs = AsyncIOMotorGridFSBucket(db.db)

        # Check if images are in the consultation document
        if "image_analyses" in consultation and consultation["image_analyses"]:
            logger.info(f"Found {len(consultation['image_analyses'])} images in consultation document")

            for img in consultation["image_analyses"]:
                try:
                    # In consultation document, image_id IS the GridFS ID
                    gridfs_id = ObjectId(img["image_id"]) if isinstance(img["image_id"], str) else img["image_id"]
                    await fs.open_download_stream(gridfs_id)
                    image_url = f"{settings.API_BASE_URL}/api/images/{img['image_id']}"

                    processed_images.append({
                        "id": str(img["image_id"]),  # GridFS ID
                        "image_id": str(img["image_id"]),  # Required field
                        "consultation_id": str(consultation["_id"]),  # Required field
                        "filename": img.get("filename", f"image_{str(img['image_id'])[:6]}.jpg"),
                        "diagnosis": img.get("diagnosis", "Unknown"),
                        "confidence": img.get("confidence", 0),
                        "probability": img.get("probability", 0),
                        "url": image_url,
                        "created_at": img.get("created_at", datetime.utcnow()).isoformat()
                    })

                except Exception as e:
                    logger.warning(f"Image {img['image_id']} not accessible: {str(e)}")

        # If no images in document, check separate collection (fallback)
        else:
            logger.info("No images in consultation document, checking separate collection")
            separate_images = await db.db.image_analyses.find({"consultation_id": validated_id}).to_list(100)
            logger.info(f"Found {len(separate_images)} images in separate collection")

            for img in separate_images:
                try:
                    gridfs_id = None

                    # Try different possible fields
                    if "image_id" in img:
                        try:
                            gridfs_id = ObjectId(img["image_id"]) if isinstance(img["image_id"], str) else img["image_id"]
                            await fs.open_download_stream(gridfs_id)
                            logger.info(f"✅ Found image in GridFS with image_id: {gridfs_id}")
                        except Exception as e:
                            logger.warning(f"❌ image_id {img['image_id']} not found in GridFS: {str(e)}")
                            gridfs_id = None

                    # If image_id doesn't work, maybe GridFS ID is in another field
                    if gridfs_id is None and "gridfs_id" in img:
                        try:
                            gridfs_id = ObjectId(img["gridfs_id"]) if isinstance(img["gridfs_id"], str) else img["gridfs_id"]
                            await fs.open_download_stream(gridfs_id)
                            logger.info(f"✅ Found image in GridFS with gridfs_id: {gridfs_id}")
                        except:
                            gridfs_id = None

                    if gridfs_id:
                        processed_images.append({
                            "id": str(gridfs_id),
                            "consultation_id": str(img["consultation_id"]),
                            "image_id": str(gridfs_id),  # Required field
                            "filename": img.get("filename", f"image_{str(gridfs_id)[:6]}.jpg"),
                            "diagnosis": img.get("diagnosis", "Unknown"),
                            "confidence": img.get("confidence", 0),
                            "probability": img.get("probability", 0),
                            "url": f"{settings.API_BASE_URL}/api/images/{gridfs_id}",
                            "created_at": img.get("created_at", datetime.utcnow()).isoformat()
                        })
                    else:
                        logger.error(f"Could not find GridFS file for image document {img['_id']}")
                        processed_images.append({
                            "id": str(img.get("image_id", img["_id"])),
                            "consultation_id": str(img["consultation_id"]),
                            "image_id": str(img.get("image_id", "")),  # Required field
                            "filename": img.get("filename", f"image_{str(img['_id'])[:6]}.jpg"),
                            "diagnosis": img.get("diagnosis", "Unknown"),
                            "confidence": img.get("confidence", 0),
                            "probability": img.get("probability", 0),
                            "url": None,
                            "created_at": img.get("created_at", datetime.utcnow()).isoformat()
                        })

                except Exception as e:
                    logger.error(f"Error processing separate image {img.get('_id', 'unknown')}: {str(e)}")

        logger.info(f"Successfully processed {len(processed_images)} images for consultation {consultation_id}")

        return ConsultationResponse(
            id=str(consultation["_id"]),
            patient_id=str(consultation["patient_id"]),
            patient_name=patient.get("name", "") if patient else "Unknown",
            date=consultation.get("date", datetime.utcnow()).isoformat(),
            notes=consultation.get("notes", ""),
            diagnosis=consultation.get("diagnosis", "Unknown"),
            probability=consultation.get("probability", 0),
            created_at=consultation.get("created_at", datetime.utcnow()),
            images=processed_images
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error retrieving consultation {consultation_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving consultation: {str(e)}")

@router.put("/{consultation_id}")
async def update_consultation(
        consultation_id: str,
        patient_id: str = Form(..., description="Patient ID"),
        date: str = Form(..., description="Consultation date in YYYY-MM-DD format"),
        notes: Optional[str] = Form(None, description="Optional consultation notes"),
):
    """
    Update an existing consultation (images cannot be updated)
    """
    try:
        validated_id = validate_object_id(consultation_id)
        validated_patient_id = validate_object_id(patient_id.strip())
        consultation_date = datetime.fromisoformat(date.strip())

        # Check if consultation exists
        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

        # Check if patient exists
        patient = await db.db.patients.find_one({"_id": validated_patient_id})
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Update consultation
        update_data = {
            "patient_id": validated_patient_id,
            "date": consultation_date,
            "notes": notes.strip() if notes and notes.strip() else None,
            "updated_at": datetime.utcnow()
        }

        result = await db.db.consultations.update_one(
            {"_id": validated_id},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Consultation not found or no changes made")

        # Get updated consultation
        updated_consultation = await db.db.consultations.find_one({"_id": validated_id})

        return {
            "success": True,
            "message": "Consultation updated successfully",
            "data": {
                "id": str(updated_consultation["_id"]),
                "patient_id": str(updated_consultation["patient_id"]),
                "patient_name": patient.get("name", ""),
                "date": updated_consultation["date"].isoformat(),
                "notes": updated_consultation.get("notes", ""),
                "diagnosis": updated_consultation.get("diagnosis", "Unknown"),
                "probability": updated_consultation.get("probability", 0),
                "created_at": updated_consultation.get("created_at", datetime.utcnow()).isoformat(),
                "updated_at": updated_consultation.get("updated_at", datetime.utcnow()).isoformat()
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error updating consultation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating consultation: {str(e)}")

@router.get("/{consultation_id}/report", response_class=StreamingResponse)
async def generate_consultation_report(consultation_id: str):
    """
    Generate a PDF report for a consultation
    """
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

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
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
    """
    Delete a consultation and its associated images
    """
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

        # Delete associated images from GridFS
        if "image_analyses" in consultation:
            for image in consultation["image_analyses"]:
                try:
                    await fs.delete(ObjectId(image["image_id"]))
                    logger.info(f"Deleted image {image['image_id']} from GridFS")
                except Exception as e:
                    logger.error(f"Error deleting image {image['image_id']}: {str(e)}")

        # Delete the consultation document
        result = await db.db.consultations.delete_one({"_id": validated_id})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found"
            )

        return {"success": True, "message": "Consultation deleted successfully"}

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error deleting consultation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting consultation: {str(e)}"
        )

# Debug endpoints (remove in production)
@router.get("/{consultation_id}/debug")
async def debug_consultation(consultation_id: str):
    """Debug endpoint to check consultation images"""
    try:
        validated_id = validate_object_id(consultation_id)

        # 1. Get consultation
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

        # 2. Check images in document
        if "image_analyses" in consultation:
            result["image_analyses_in_doc"] = consultation["image_analyses"]
            result["image_count_in_doc"] = len(consultation["image_analyses"])

        # 3. Check separate collection
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

        # 4. Check GridFS
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