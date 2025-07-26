from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId
from app.db import db
from app.utils.validators import validate_object_id
import logging
from io import BytesIO
from PIL import Image
import time

router = APIRouter(
    prefix="",
    tags=["images"],
    responses={404: {"description": "Image not found"}}
)

logger = logging.getLogger(__name__)

async def get_gridfs_bucket():
    """Get GridFS bucket instance with connection handling"""
    try:
        if db.db is None:
            await db.connect()
        # CRITICAL FIX: Use the same bucket name as in consultations.py
        return AsyncIOMotorGridFSBucket(db.db, bucket_name="fs")
    except Exception as e:
        logger.error(f"Error connecting to GridFS: {str(e)}")
        raise HTTPException(status_code=500, detail="Database connection error")

@router.get("/{image_id}")
async def get_image(image_id: str):
    try:
        logger.info(f"🔍 Starting image request for: {image_id}")

        # Validate ObjectId
        object_id = validate_object_id(image_id)
        logger.info(f"✅ Valid ObjectId created: {object_id}")

        # Get GridFS bucket
        fs = await get_gridfs_bucket()
        logger.info(f"✅ GridFS bucket obtained successfully")

        # Initialize grid_out outside try block to ensure it's in scope for finally
        grid_out = None
        try:
            logger.info(f"🔍 Attempting to open download stream for: {object_id}")
            grid_out = await fs.open_download_stream(object_id)

            # Read all content first
            image_content = await grid_out.read()
            logger.info(f"✅ Read {len(image_content)} bytes from GridFS")

            # Get filename and content type
            filename = getattr(grid_out, 'filename', 'image.jpg')
            content_type = getattr(grid_out, 'content_type', 'image/jpeg')

            # Use metadata if available
            if hasattr(grid_out, 'metadata') and grid_out.metadata:
                content_type = grid_out.metadata.get('content_type', content_type)

            return Response(
                content=image_content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f"inline; filename={filename}",
                    "Cache-Control": "public, max-age=3600",
                    "Content-Length": str(len(image_content))
                }
            )

        except Exception as gridfs_error:
            logger.error(f"❌ GridFS error for {image_id}: {str(gridfs_error)}", exc_info=True)

            if "file not found" in str(gridfs_error).lower():
                raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

            # Generate placeholder image
            img = Image.new('RGB', (300, 200), color=(220, 220, 220))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            buffer.seek(0)

            return Response(
                content=buffer.getvalue(),
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": "inline; filename=placeholder.jpg",
                    "X-Image-Error": f"Original image error: {str(gridfs_error)}"
                }
            )

        finally:
            # Safely close the stream if it exists
            if grid_out is not None:
                try:
                    await grid_out.close()
                    logger.info("✅ Stream closed successfully")
                except Exception as close_error:
                    logger.warning(f"⚠️ Non-critical error closing stream: {str(close_error)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error with image {image_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/upload/{consultation_id}")
async def upload_consultation_image(
        consultation_id: str,
        file: UploadFile = File(...),
        diagnosis: str = Form("Unknown"),
        confidence: float = Form(0.0),
        probability: float = Form(0.0)
):
    try:
        # Validación de la consulta
        validated_consultation_id = validate_object_id(consultation_id)
        consultation = await db.db.consultations.find_one({"_id": validated_consultation_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

        # Validar el archivo de imagen
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image files are allowed")

        # Configurar GridFS with the same bucket name
        fs = await get_gridfs_bucket()

        # Leer y validar la imagen
        contents = await file.read()
        try:
            # Validar que es una imagen válida
            Image.open(BytesIO(contents)).verify()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image file: {str(e)}")

        # Subir a GridFS con metadata
        upload_time = datetime.utcnow()
        file_id = await fs.upload_from_stream(
            filename=file.filename,
            source=BytesIO(contents),  # Usar BytesIO para re-leer
            metadata={
                "consultation_id": str(validated_consultation_id),
                "original_filename": file.filename,
                "content_type": file.content_type,
                "uploaded_at": upload_time,
                "size_bytes": len(contents)
            }
        )

        # Guardar metadatos en MongoDB
        image_record = {
            "consultation_id": validated_consultation_id,
            "image_id": file_id,
            "filename": file.filename,
            "content_type": file.content_type,
            "diagnosis": diagnosis,
            "confidence": float(confidence),
            "probability": float(probability),
            "created_at": upload_time,
            "status": "uploaded"
        }

        result = await db.db.image_analyses.insert_one(image_record)

        return {
            "success": True,
            "image_id": str(file_id),
            "consultation_id": str(validated_consultation_id),
            "filename": file.filename,
            "size_bytes": len(contents),
            "url": f"/api/images/{file_id}",
            "created_at": upload_time.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading image: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload image")

# Debug endpoint to list all GridFS files
@router.get("/debug/gridfs-files")
async def debug_gridfs_files():
    """Debug endpoint to list all files in GridFS"""
    try:
        fs = await get_gridfs_bucket()
        files = []

        async for file_info in fs.find():
            files.append({
                "id": str(file_info._id),
                "filename": file_info.filename,
                "length": file_info.length,
                "upload_date": file_info.upload_date.isoformat(),
                "metadata": file_info.metadata
            })

        return {
            "success": True,
            "count": len(files),
            "files": files
        }

    except Exception as e:
        logger.error(f"Error listing GridFS files: {str(e)}")
        return {"success": False, "error": str(e)}

# NUEVO: Endpoint para verificar si un image_id específico existe
@router.get("/debug/check/{image_id}")
async def check_image_exists(image_id: str):
    """Check if an image exists in GridFS and related collections"""
    try:
        object_id = validate_object_id(image_id)
        fs = await get_gridfs_bucket()

        result = {
            "image_id": image_id,
            "object_id": str(object_id),
            "exists_in_gridfs": False,
            "exists_in_image_analyses": False,
            "exists_in_consultations": False,
            "gridfs_info": None,
            "image_analyses_info": None,
            "consultation_info": None
        }

        # Check GridFS
        try:
            file_cursor = fs.find({"_id": object_id})
            file_list = await file_cursor.to_list(1)
            if file_list:
                file_info = file_list[0]
                result["exists_in_gridfs"] = True
                result["gridfs_info"] = {
                    "id": str(file_info._id),
                    "filename": file_info.filename,
                    "length": file_info.length,
                    "upload_date": file_info.upload_date.isoformat(),
                    "metadata": file_info.metadata
                }
        except Exception as gridfs_error:
            result["gridfs_error"] = str(gridfs_error)

        # Check image_analyses collection
        image_doc = await db.db.image_analyses.find_one({"image_id": object_id})
        if image_doc:
            result["exists_in_image_analyses"] = True
            result["image_analyses_info"] = {
                "document_id": str(image_doc["_id"]),
                "consultation_id": str(image_doc["consultation_id"]),
                "filename": image_doc.get("filename"),
                "diagnosis": image_doc.get("diagnosis")
            }

        # Check consultations collection
        consultation = await db.db.consultations.find_one({
            "image_analyses.image_id": {"$in": [str(object_id), image_id]}
        })
        if consultation:
            result["exists_in_consultations"] = True
            result["consultation_info"] = {
                "consultation_id": str(consultation["_id"]),
                "patient_id": str(consultation["patient_id"]),
                "image_count": len(consultation.get("image_analyses", []))
            }

        return result

    except Exception as e:
        return {"error": str(e), "image_id": image_id}

# NUEVO: Endpoint para intentar reparar imágenes faltantes
@router.post("/debug/repair/{consultation_id}")
async def repair_consultation_images(consultation_id: str):
    """Attempt to repair missing images for a consultation"""
    try:
        validated_id = validate_object_id(consultation_id)

        # Get consultation
        consultation = await db.db.consultations.find_one({"_id": validated_id})
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

        fs = await get_gridfs_bucket()
        repair_results = []

        # Check images in consultation document
        if "image_analyses" in consultation:
            for i, img in enumerate(consultation["image_analyses"]):
                image_id = img.get("image_id")
                if image_id:
                    try:
                        object_id = ObjectId(image_id) if isinstance(image_id, str) else image_id

                        # Try to open the image
                        grid_out = await fs.open_download_stream(object_id)
                        await grid_out.close()

                        repair_results.append({
                            "index": i,
                            "image_id": str(image_id),
                            "status": "OK",
                            "message": "Image exists and is accessible"
                        })
                    except Exception as e:
                        repair_results.append({
                            "index": i,
                            "image_id": str(image_id),
                            "status": "ERROR",
                            "message": f"Image not accessible: {str(e)}"
                        })

        return {
            "consultation_id": consultation_id,
            "repair_results": repair_results,
            "total_images": len(repair_results)
        }

    except Exception as e:
        logger.error(f"Repair error: {str(e)}")
        return {"error": str(e), "consultation_id": consultation_id}