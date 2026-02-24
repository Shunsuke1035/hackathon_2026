from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.facility import Facility
from app.models.user import User
from app.schemas.facility import FacilityCreateRequest, FacilityResponse, FacilityUpdateRequest

router = APIRouter(prefix="/facility", tags=["facility"])


def _get_facility(db: Session, user_id: int) -> Facility | None:
    return db.execute(select(Facility).where(Facility.user_id == user_id)).scalar_one_or_none()


@router.get("/me", response_model=FacilityResponse)
def get_my_facility(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FacilityResponse:
    facility = _get_facility(db, current_user.id)
    if not facility:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="施設情報が登録されていません")
    return FacilityResponse.model_validate(facility)


@router.post("/me", response_model=FacilityResponse, status_code=status.HTTP_201_CREATED)
def create_my_facility(
    payload: FacilityCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FacilityResponse:
    existing = _get_facility(db, current_user.id)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="施設情報は既に登録されています")

    facility = Facility(user_id=current_user.id, **payload.model_dump())
    db.add(facility)
    db.commit()
    db.refresh(facility)
    return FacilityResponse.model_validate(facility)


@router.patch("/me", response_model=FacilityResponse)
def update_my_facility(
    payload: FacilityUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FacilityResponse:
    facility = _get_facility(db, current_user.id)
    if not facility:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="施設情報が登録されていません")

    update_values = payload.model_dump(exclude_unset=True)
    for key, value in update_values.items():
        setattr(facility, key, value)

    db.add(facility)
    db.commit()
    db.refresh(facility)
    return FacilityResponse.model_validate(facility)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_facility(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    facility = _get_facility(db, current_user.id)
    if not facility:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="施設情報が登録されていません")

    db.delete(facility)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
