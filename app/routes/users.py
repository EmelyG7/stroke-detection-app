from fastapi import APIRouter, HTTPException, status
from bson import ObjectId
from app.db import db
from app.models.user import User
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import logging

router = APIRouter(
    prefix="",
    tags=["users"],
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

def serialize_user(user):
    """Helper function to serialize user data"""
    if not user:
        return None

    # Aplicamos serialize_object_ids primero
    user_data = serialize_object_ids(dict(user))

    # Aseguramos el formato de las fechas
    if "created_at" in user_data:
        user_data["created_at"] = user_data["created_at"].isoformat()
    if "updated_at" in user_data:
        user_data["updated_at"] = user_data["updated_at"].isoformat()

    # Renombramos _id a id y eliminamos _id
    if "_id" in user_data:
        user_data["id"] = user_data.pop("_id")

    # Eliminamos el password_hash si existe
    user_data.pop("password_hash", None)

    return user_data

@router.get("/", response_model=list)
async def get_users():
    try:
        if db.db is None:
            await db.connect()

        # Excluimos password_hash desde la consulta
        users = await db.db.users.find({}, {"password_hash": 0}).to_list(length=None)

        # Serializamos cada usuario
        serialized_users = [serialize_user(user) for user in users]

        return jsonable_encoder(serialized_users)
    except Exception as e:
        logger.error(f"Error retrieving users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving users: {str(e)}"
        )

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(user: User):
    try:
        if db.db is None:
            await db.connect()

        # Verificamos si el usuario ya existe
        existing_user = await db.db.users.find_one({"username": user.username})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )

        # Preparamos los datos del usuario
        user_dict = user.dict(exclude_unset=True)
        user_dict["created_at"] = datetime.utcnow()

        # Insertamos el usuario en la base de datos
        result = await db.db.users.insert_one(user_dict)

        # Obtenemos el usuario recién creado (sin password_hash)
        created_user = await db.db.users.find_one(
            {"_id": result.inserted_id},
            {"password_hash": 0}
        )

        # Serializamos la respuesta
        return jsonable_encoder(serialize_user(created_user))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {str(e)}"
        )