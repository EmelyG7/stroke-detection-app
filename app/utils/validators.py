# app/utils/validators.py
from bson import ObjectId
from fastapi import HTTPException
from fastapi import status

def validate_object_id(object_id: str) -> ObjectId:
    """Validate a MongoDB ObjectId"""
    try:
        return ObjectId(object_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ID format: {object_id}"
        )