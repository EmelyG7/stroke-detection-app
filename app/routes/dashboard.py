from fastapi import APIRouter, HTTPException
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
        total_patients = await db.db.patients.count_documents({})
        total_consultations = await db.db.consultations.count_documents({})
        stroke_consultations = await db.db.consultations.count_documents({"diagnosis": "Stroke"})
        stroke_rate = (stroke_consultations / total_consultations * 100) if total_consultations > 0 else 0

        monthly_stats = await db.db.consultations.aggregate([
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m", "date": "$date"}},
                    "stroke_count": {"$sum": {"$cond": [{"$eq": ["$diagnosis", "Stroke"]}, 1, 0]}},
                    "avg_probability": {"$avg": {"$cond": [{"$eq": ["$diagnosis", "Stroke"]}, "$probability", None]}},
                }
            },
            {"$project": {"year_month": "$_id", "stroke_count": 1, "avg_probability": 1, "_id": 0}},
            {"$sort": {"year_month": -1}},
            {"$limit": 6},
        ]).to_list(length=6)

        recent_consultations = await db.db.consultations.aggregate([
            {"$lookup": {"from": "patients", "localField": "patient_id", "foreignField": "_id", "as": "patient"}},
            {"$unwind": "$patient"},
            {"$sort": {"created_at": -1}},
            {"$limit": 5},
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                    "diagnosis": 1,
                    "probability": 1,
                    "patient_name": "$patient.name",
                }
            },
        ]).to_list(length=5)

        stroke_stats = await db.db.consultations.aggregate([
            {"$match": {"diagnosis": "Stroke"}},
            {"$lookup": {"from": "patients", "localField": "patient_id", "foreignField": "_id", "as": "patient"}},
            {"$unwind": "$patient"},
            {
                "$group": {
                    "_id": None,
                    "avgStrokeProbability": {"$avg": "$probability"},
                    "avgStrokeAge": {"$avg": "$patient.age"},
                    "ages": {"$push": "$patient.age"},
                }
            },
            {
                "$project": {
                    "avgStrokeProbability": {"$multiply": ["$avgStrokeProbability", 100]},
                    "avgStrokeAge": 1,
                    "riskAgeRange": {"$concat": [{"$toString": {"$min": "$ages"}}, "-", {"$toString": {"$max": "$ages"}}]},
                }
            },
        ]).to_list(length=1)

        stats = stroke_stats[0] if stroke_stats else {"avgStrokeProbability": 0, "avgStrokeAge": 0, "riskAgeRange": "0-0"}

        return {
            "totalPatients": total_patients,
            "totalConsultations": total_consultations,
            "strokeRate": f"{stroke_rate:.1f}",
            "avgStrokeProbability": f"{stats['avgStrokeProbability']:.2f}",
            "avgStrokeAge": f"{stats['avgStrokeAge']:.1f}",
            "riskAgeRange": stats["riskAgeRange"],
            "monthlyStats": monthly_stats,
            "recentConsultations": recent_consultations,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {str(e)}")