"""Маршрути для HTML сторінок"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from config import INDEX_FILE

router = APIRouter(tags=["Pages"])


@router.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    """Головна сторінка"""
    return HTMLResponse(
        """
        <html>
            <body>
                <h1>ESP32 Real-time Monitor</h1>
                <p>Open <a href="/monitor">/monitor</a> to see real-time data</p>
            </body>
        </html>
        """
    )


@router.get("/monitor", response_class=HTMLResponse)
async def monitor() -> HTMLResponse:
    """Сторінка моніторингу"""
    with open(INDEX_FILE, encoding="utf-8") as file:
        return HTMLResponse(file.read())