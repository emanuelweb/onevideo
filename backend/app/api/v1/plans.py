from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Plan
from app.schemas import PlanPublic

router = APIRouter()


@router.get("/plans", response_model=list[PlanPublic])
def list_plans(db: Session = Depends(get_db)) -> list[PlanPublic]:
    plans = db.scalars(select(Plan).order_by(Plan.sort_order)).all()
    return [PlanPublic.model_validate(plan) for plan in plans]
