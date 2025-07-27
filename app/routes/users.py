import hashlib

from fastapi import APIRouter, HTTPException, status
from bson import ObjectId
from pydantic import BaseModel

from app.db import db
from app.models.user import User
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import bcrypt
import logging

router = APIRouter(
    prefix="",
    tags=["users"],
    responses={404: {"description": "Not found"}}
)

# Modelos para autenticación
class LoginRequest(BaseModel):
    username: str
    password: str

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
    if "last_login" in user_data and user_data["last_login"]:
        user_data["last_login"] = user_data["last_login"].isoformat()

    # Renombramos _id a id y eliminamos _id
    if "_id" in user_data:
        user_data["id"] = user_data.pop("_id")

    # Eliminamos el password_hash si existe
    user_data.pop("password_hash", None)

    return user_data

def hash_password(password: str) -> str:
    """Hash seguro de contraseña usando bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed_password: str) -> bool:
    """Verificación segura de contraseña"""
    try:
        return bcrypt.checkpw(password.encode(), hashed_password.encode())
    except Exception:
        return False

# NUEVO ENDPOINT DE AUTENTICACIÓN
@router.post("/login", response_model=dict)
async def login_user(login_data: LoginRequest):
    try:
        if db.db is None:
            await db.connect()

        user = await db.db.users.find_one({"username": login_data.username})

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"success": False, "error": "Usuario no encontrado"}
            )

        # Verificación de contraseña mejorada
        if 'password_hash' not in user or not user['password_hash']:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"success": False, "error": "Configuración de contraseña inválida"}
            )

        if not verify_password(login_data.password, user['password_hash']):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"success": False, "error": "Contraseña incorrecta"}
            )

        # Actualizar último login
        await db.db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.utcnow()}}
        )

        return {
            "success": True,
            "data": serialize_user(user),
            "message": "Login exitoso"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en login: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": "Error interno del servidor"}
        )

@router.get("/", response_model=dict)
async def get_users():
    """
    Obtener todos los usuarios
    Returns:
        {
            "success": bool,
            "data": List[User],
            "message": str (opcional)
        }
    """
    try:
        if db.db is None:
            await db.connect()

        users = await db.db.users.find({}, {"password_hash": 0}).to_list(length=None)

        return {
            "success": True,
            "data": jsonable_encoder([serialize_user(user) for user in users])
        }
    except Exception as e:
        logger.error(f"Error al obtener usuarios: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": f"Error al obtener usuarios: {str(e)}"
            }
        )

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_user(user_data: dict):
    """
    Crear un nuevo usuario
    Expects: {
        "username": str,
        "full_name": str,
        "role": str,
        "password": str
    }
    Returns:
        {
            "success": bool,
            "data": User,
            "message": str (opcional)
        }
    """
    try:
        if db.db is None:
            await db.connect()

        # Validar campos requeridos
        required_fields = ["username", "full_name", "role", "password"]
        for field in required_fields:
            if field not in user_data or not user_data[field]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "success": False,
                        "error": f"El campo '{field}' es requerido"
                    }
                )

        # Verificar si el usuario ya existe
        existing_user = await db.db.users.find_one({"username": user_data["username"]})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "El nombre de usuario ya existe"
                }
            )

        # Hash de la contraseña
        password_hash = hash_password(user_data["password"])

        # Crear documento de usuario
        user_doc = {
            "username": user_data["username"],
            "full_name": user_data["full_name"],
            "role": user_data["role"],
            "password_hash": password_hash,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = await db.db.users.insert_one(user_doc)

        created_user = await db.db.users.find_one(
            {"_id": result.inserted_id},
            {"password_hash": 0}
        )

        return {
            "success": True,
            "data": jsonable_encoder(serialize_user(created_user))
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al crear usuario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": f"Error al crear usuario: {str(e)}"
            }
        )

@router.get("/{id}", response_model=dict)
async def get_user(id: str):
    """
    Obtener un usuario por ID
    Returns:
        {
            "success": bool,
            "data": User,
            "message": str (opcional)
        }
    """
    try:
        if not ObjectId.is_valid(id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "ID de usuario inválido"
                }
            )

        if db.db is None:
            await db.connect()

        user = await db.db.users.find_one(
            {"_id": ObjectId(id)},
            {"password_hash": 0}
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "success": False,
                    "error": "Usuario no encontrado"
                }
            )

        return {
            "success": True,
            "data": jsonable_encoder(serialize_user(user))
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener usuario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": f"Error al obtener usuario: {str(e)}"
            }
        )

@router.put("/{id}", response_model=dict)
async def update_user(id: str, user_data: dict):
    """
    Actualizar un usuario existente
    Expects: {
        "username": str (opcional),
        "full_name": str (opcional),
        "role": str (opcional),
        "password": str (opcional - si se incluye, se actualiza)
    }
    Returns:
        {
            "success": bool,
            "data": User,
            "message": str (opcional)
        }
    """
    try:
        if not ObjectId.is_valid(id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "ID de usuario inválido"
                }
            )

        if db.db is None:
            await db.connect()

        # Verificar que el usuario existe
        existing_user = await db.db.users.find_one({"_id": ObjectId(id)})
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "success": False,
                    "error": "Usuario no encontrado"
                }
            )

        # Preparar datos de actualización
        update_data = {
            "updated_at": datetime.utcnow()
        }

        # Campos permitidos para actualizar
        allowed_fields = ["username", "full_name", "role"]
        for field in allowed_fields:
            if field in user_data and user_data[field]:
                update_data[field] = user_data[field]

        # Si se incluye password, hashearlo
        if "password" in user_data and user_data["password"]:
            update_data["password_hash"] = hash_password(user_data["password"])

        # Verificar username único si se está actualizando
        if "username" in update_data:
            username_exists = await db.db.users.find_one({
                "username": update_data["username"],
                "_id": {"$ne": ObjectId(id)}
            })
            if username_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "success": False,
                        "error": "El nombre de usuario ya existe"
                    }
                )

        result = await db.db.users.update_one(
            {"_id": ObjectId(id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_304_NOT_MODIFIED,
                detail={
                    "success": False,
                    "error": "Usuario no modificado"
                }
            )

        updated_user = await db.db.users.find_one(
            {"_id": ObjectId(id)},
            {"password_hash": 0}
        )

        return {
            "success": True,
            "data": jsonable_encoder(serialize_user(updated_user))
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al actualizar usuario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": f"Error al actualizar usuario: {str(e)}"
            }
        )

@router.delete("/{id}", response_model=dict)
async def delete_user(id: str):
    """
    Eliminar un usuario
    Returns:
        {
            "success": bool,
            "data": {"id": str},
            "message": str (opcional)
        }
    """
    try:
        if not ObjectId.is_valid(id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "ID de usuario inválido"
                }
            )

        if db.db is None:
            await db.connect()

        existing_user = await db.db.users.find_one({"_id": ObjectId(id)})
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "success": False,
                    "error": "Usuario no encontrado"
                }
            )

        result = await db.db.users.delete_one({"_id": ObjectId(id)})

        return {
            "success": True,
            "data": {"id": id}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al eliminar usuario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": f"Error al eliminar usuario: {str(e)}"
            }
        )

