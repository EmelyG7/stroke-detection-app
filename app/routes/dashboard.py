from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from app.db import db
from bson import ObjectId

router = APIRouter(
    prefix="",
    tags=["dashboard"],
    responses={404: {"description": "Not found"}}
)

@router.get("/stats")
async def get_stats():
    try:
        if db.db is None:
            await db.connect()

        # Basic counts
        total_patients = await db.db.patients.count_documents({})
        total_consultations = await db.db.consultations.count_documents({})
        stroke_consultations = await db.db.consultations.count_documents({"diagnosis": "Stroke"})
        stroke_rate = (stroke_consultations / total_consultations * 100) if total_consultations > 0 else 0

        # Monthly stats for charts
        monthly_stats = await db.db.consultations.aggregate([
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m", "date": "$date"}},
                    "stroke_count": {"$sum": {"$cond": [{"$eq": ["$diagnosis", "Stroke"]}, 1, 0]}},
                    "avg_probability": {"$avg": "$probability"},
                }
            },
            {"$sort": {"_id": 1}},
            {"$limit": 12},
            {
                "$project": {
                    "year_month": "$_id",
                    "stroke_count": 1,
                    "avg_probability": {"$ifNull": ["$avg_probability", 0]},
                    "_id": 0
                }
            }
        ]).to_list(length=None)

        # Recent consultations with patient names
        recent_consultations = await db.db.consultations.aggregate([
            {"$sort": {"date": -1}},
            {"$limit": 5},
            {
                "$lookup": {
                    "from": "patients",
                    "localField": "patient_id",
                    "foreignField": "_id",
                    "as": "patient"
                }
            },
            {"$unwind": {"path": "$patient", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                    "diagnosis": 1,
                    "probability": {"$multiply": ["$probability", 100]},
                    "patient_name": "$patient.name",
                }
            }
        ]).to_list(length=5)

        # Stroke statistics
        stroke_stats = await db.db.consultations.aggregate([
            {"$match": {"diagnosis": "Stroke"}},
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
                "$group": {
                    "_id": None,
                    "avgStrokeProbability": {"$avg": "$probability"},
                    "avgStrokeAge": {"$avg": "$patient.age"},
                    "minAge": {"$min": "$patient.age"},
                    "maxAge": {"$max": "$patient.age"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "avgStrokeProbability": {"$multiply": ["$avgStrokeProbability", 100]},
                    "avgStrokeAge": 1,
                    "riskAgeRange": {
                        "$concat": [
                            {"$toString": "$minAge"},
                            "-",
                            {"$toString": "$maxAge"}
                        ]
                    }
                }
            }
        ]).to_list(length=1)

        # Default values if no stroke cases exist
        stroke_data = stroke_stats[0] if stroke_stats else {
            "avgStrokeProbability": 0,
            "avgStrokeAge": 0,
            "riskAgeRange": "0-0"
        }

        return {
            "totalPatients": total_patients,
            "totalConsultations": total_consultations,
            "strokeRate": f"{stroke_rate:.1f}",
            "avgStrokeProbability": f"{stroke_data['avgStrokeProbability']:.1f}",
            "avgStrokeAge": f"{stroke_data['avgStrokeAge']:.1f}",
            "riskAgeRange": stroke_data["riskAgeRange"],
            "monthlyStats": monthly_stats,
            "recentConsultations": recent_consultations,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving dashboard stats: {str(e)}"
        )