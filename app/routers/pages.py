from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.paths import TEMPLATES_DIR
from app.state import hsk_vocab

router = APIRouter(tags=["Pages"])

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "vocab_count": len(hsk_vocab)}
    )


@router.get("/admin")
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})
