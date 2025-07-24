from fastapi import APIRouter, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId
from starlette.responses import StreamingResponse
from app.db import db
from app.utils.validators import validate_object_id
import logging

router = APIRouter(
    prefix="",
    tags=["images"],
    responses={
        404: {"description": "Image not found"},
        400: {"description": "Invalid image ID"},
        500: {"description": "Internal server error"}
    }
)

logger = logging.getLogger(__name__)

async def get_gridfs():
    """Obtiene el bucket de GridFS, conectando a la DB si es necesario"""
    if db.db is None:
        await db.connect()
    return AsyncIOMotorGridFSBucket(db.db, bucket_name="fs")

@router.get(
    "/{id}",
    summary="Obtener imagen",
    description="Recupera una imagen almacenada en GridFS por su ID",
    responses={
        200: {
            "content": {"image/*": {}},
            "description": "Retorna la imagen solicitada"
        }
    }
)
async def get_image(id: str):
    try:
        # Validar el ID de la imagen
        validated_id = validate_object_id(id)

        # Obtener el bucket de GridFS
        fs = await get_gridfs()

        try:
            # Intentar abrir el archivo para descarga
            file = await fs.open_download_stream(validated_id)

            # Verificar si el archivo existe
            if file.length == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Image not found or empty"
                )

            # Obtener metadata del archivo
            metadata = file.metadata or {}
            content_type = metadata.get("content_type", "image/jpeg")
            filename = file.filename or f"image_{id}.jpg"

            # Retornar la imagen como streaming response
            return StreamingResponse(
                file,
                media_type=content_type,
                headers={
                    "Content-Disposition": f"inline; filename={filename}",
                    "Cache-Control": "public, max-age=604800"  # Cache de 1 semana
                }
            )

        except Exception as e:
            logger.error(f"Error retrieving image {id}: {str(e)}")
            if "file not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Image not found"
                )
            raise

    except HTTPException:
        raise

    except ValueError as e:
        logger.error(f"Invalid image ID format: {id} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image ID format"
        )

    except Exception as e:
        logger.error(f"Unexpected error retrieving image {id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving image"
        )