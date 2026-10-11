from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.domain.transforms import registry_listing
from app.schemas.api import DatasetSummary, TransformInfo
from app.security import get_current_user
from app.services import inputs

router = APIRouter(prefix="/inputs", tags=["inputs"], dependencies=[Depends(get_current_user)])


@router.get("/source-schema")
def get_source_schema() -> dict[str, Any]:
    return inputs.source_schema()


@router.get("/target-schema")
def get_target_schema() -> dict[str, Any]:
    return inputs.target_schema()


@router.get("/transforms", response_model=list[TransformInfo])
def get_transforms() -> list[dict[str, Any]]:
    return registry_listing()


@router.get("/datasets", response_model=list[DatasetSummary])
def get_datasets() -> list[dict[str, Any]]:
    return inputs.dataset_summaries(get_settings().max_source_records)
