"""What this server offers beyond the basics.

The SPA (web or the Android app, which can switch between servers) asks
once at start and shows only what the server it talks to can do: an
instance with an LLM shows those features, one without doesn't.
"""

import os

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.database import User
from app.services import llm

router = APIRouter(tags=["Capabilities"])


@router.get("/api/capabilities")
def get_capabilities() -> dict:
    translation = [
        name
        for name, var in (("deepl", "DEEPL_API_KEY"), ("google", "GOOGLE_TRANSLATE_API_KEY"))
        if os.getenv(var)
    ] + ["mymemory"]
    return {"llm": llm.capabilities(), "translation": translation}


@router.post("/api/admin/llm/probe")
async def probe_llm(user: User = Depends(require_admin)) -> dict:
    """Check the LLM endpoint now (admin): reachability, latency, error."""
    _ = user
    st = await llm.probe()
    return {**llm.capabilities(), "latency_ms": st.latency_ms, "error": st.error}
