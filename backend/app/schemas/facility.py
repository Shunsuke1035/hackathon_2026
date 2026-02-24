from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FacilityCreateRequest(BaseModel):
    facility_name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=512)
    prefecture_code: str | None = Field(default=None, max_length=32)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class FacilityUpdateRequest(BaseModel):
    facility_name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=512)
    prefecture_code: str | None = Field(default=None, max_length=32)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class FacilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    facility_name: str | None
    address: str | None
    prefecture_code: str | None
    latitude: float | None
    longitude: float | None
    created_at: datetime
    updated_at: datetime
