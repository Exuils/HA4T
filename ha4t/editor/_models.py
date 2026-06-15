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


class CurrentApp(BaseModel):
    """当前前台应用的标识 —— 给 UI 显示"现在在哪"用，不进 selector/POM 字段。

    package    包名 / bundleId（Android: package；iOS: bundleId；Harmony: bundleName）
    activity   Android Activity 短名（如 .LoginActivity）或 Harmony ability；
               iOS / Flutter / Compose 单 Activity 项目可能为空
    """
    package: Optional[str] = None
    activity: Optional[str] = None


class BaseHierarchy(BaseModel):
    jsonHierarchy: Optional[Dict] = None
    windowSize: Tuple[int, int]
    scale: int = 1
    currentApp: Optional[CurrentApp] = None


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