# -*- coding: utf-8 -*-

import enum

from pydantic import BaseModel
from typing import Any, Union, Dict, Tuple, Optional, List


class Platform(str, enum.Enum):
    ANDROID = "android"
    IOS = "ios"
    HARMONY = "harmony"


class ApiResponse(BaseModel):
    success: bool = True
    data: Any = None
    message: Optional[str] = None

    @classmethod
    def doSuccess(cls, data):
        return ApiResponse(success=True, data=data, message=None)

    @classmethod
    def doError(cls, message):
        return ApiResponse(success=False, data=None, message=message)


class BaseHierarchy(BaseModel):
    jsonHierarchy: Optional[Dict] = None
    windowSize: Tuple[int, int]
    scale: int = 1


class XPathLiteRequest(BaseModel):
    tree_data: Dict[str, Any]
    node_id: str


class TaskFile(BaseModel):
    filename: str
    name: str
    description: str
    platform: str
    step_count: int


class TaskSaveRequest(BaseModel):
    content: str


class TaskRunRequest(BaseModel):
    platform: str
    serial: str
    filename: Optional[str] = None
    content: Optional[str] = None


class TaskStepResult(BaseModel):
    index: int
    action: str
    value: str
    status: str
    detail: Optional[str] = None
    duration: Optional[float] = None


class TaskRunResponse(BaseModel):
    steps: List[TaskStepResult]
    success: bool
    summary: str