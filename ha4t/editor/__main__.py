# -*- coding: utf-8 -*-

import os
import webbrowser
import uvicorn
import threading

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from ha4t.editor.routers import api
from ha4t.editor._models import ApiResponse


app = FastAPI()


current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount Allure reports directory (created on demand when running with --allure)
allure_reports_dir = os.path.join(os.path.expanduser("~"), "Documents", "HA4T", "allure-reports")
os.makedirs(allure_reports_dir, exist_ok=True)
app.mount("/allure-reports", StaticFiles(directory=allure_reports_dir), name="allure-reports")

app.include_router(api.router)


@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=ApiResponse(success=False, message=str(exc)).model_dump()
    )


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(success=False, message=exc.detail).model_dump()
    )


def open_browser(port):
    webbrowser.open_new(f"http://127.0.0.1:{port}")


def run(port=8000, workspace=None):
    if workspace:
        # 提前置入工作区，避免 gate；失败仅打印告警，serve 继续。
        from ha4t.editor._config import EditorConfig
        from ha4t.editor.routers import api as _api
        try:
            EditorConfig().set_workspace(workspace)
        except ValueError as e:
            print(f"[ha4t] --workspace 忽略：{e}")
        else:
            _api._refresh_paths()

    timer = threading.Timer(1.0, open_browser, args=[port])
    timer.daemon = True
    timer.start()

    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(prog="ha4t.editor", description="HA4T editor server")
    parser.add_argument("-p", "--port", type=int, default=8000, help="HTTP 端口（默认 8000）")
    parser.add_argument("-w", "--workspace", default=None, help="预选工作区目录（绝对路径，必须已存在）")
    args = parser.parse_args()
    run(port=args.port, workspace=args.workspace)