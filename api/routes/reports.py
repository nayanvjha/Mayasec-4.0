"""FastAPI-compatible reports routes.

This module mirrors the report APIs used in the Flask runtime so teams that
embed MAYASEC into a FastAPI control-plane can mount equivalent endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter, Depends, HTTPException
    from pydantic import BaseModel, EmailStr
except Exception:  # pragma: no cover - optional dependency for compatibility only
    APIRouter = None  # type: ignore
    Depends = None  # type: ignore
    HTTPException = RuntimeError  # type: ignore
    BaseModel = object  # type: ignore
    EmailStr = str  # type: ignore


class GenerateReportRequest(BaseModel):
    tenant_id: str
    start_time: datetime
    end_time: datetime


class ScheduleReportRequest(BaseModel):
    tenant_id: str
    frequency: str
    email: EmailStr


# These callables are injected by host app to keep this module framework-neutral.

def get_report_service() -> Any:  # pragma: no cover
    raise NotImplementedError("Provide report service dependency")


def get_current_tenant_id() -> str:  # pragma: no cover
    raise NotImplementedError("Provide tenant dependency")


router = APIRouter(prefix="/api/v1/reports", tags=["reports"]) if APIRouter else None


if router:
    @router.get("")
    async def list_reports(
        limit: int = 100,
        offset: int = 0,
        tenant_id: str = Depends(get_current_tenant_id),
        service: Any = Depends(get_report_service),
    ) -> Dict[str, Any]:
        return await service.list_reports(tenant_id=tenant_id, limit=limit, offset=offset)


    @router.post("/generate")
    async def generate_report(
        payload: GenerateReportRequest,
        tenant_id: str = Depends(get_current_tenant_id),
        service: Any = Depends(get_report_service),
    ) -> Dict[str, Any]:
        if payload.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.generate_report(
            tenant_id=tenant_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )


    @router.post("/schedule")
    async def schedule_report(
        payload: ScheduleReportRequest,
        tenant_id: str = Depends(get_current_tenant_id),
        service: Any = Depends(get_report_service),
    ) -> Dict[str, Any]:
        if payload.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="forbidden")
        if payload.frequency.lower() != "weekly":
            raise HTTPException(status_code=400, detail="Only weekly frequency is supported")
        return await service.schedule_report(
            tenant_id=tenant_id,
            frequency="weekly",
            email=str(payload.email),
        )
