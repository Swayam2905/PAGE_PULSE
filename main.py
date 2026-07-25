"""
Page Pulse — a small web tool that audits any URL.

POST /api/audit  {"url": "https://example.com"}
  -> {status_code, response_time_ms, title, meta_description,
      h1_count, images_missing_alt, total_images, word_count, error}

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload
Then open http://127.0.0.1:8000
"""

import re
import time
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

app = FastAPI(
    title="Page Pulse",
    description="Audits any URL and returns an HTTP/SEO/accessibility health report.",
    version="1.0.0",
)

# Wide-open CORS since this is a small public utility hit from a static frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 5
USER_AGENT = "PagePulse/1.0 (+https://digitalheroesco.com)"


# ---------- Schemas ----------

class AuditRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def normalize_url(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("URL cannot be empty.")
        if not re.match(r"^https?://", v, flags=re.IGNORECASE):
            v = "https://" + v
        parsed = urlparse(v)
        if not parsed.netloc or "." not in parsed.netloc:
            raise ValueError("That doesn't look like a valid URL.")
        return v


class AuditReport(BaseModel):
    url: str
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    title: Optional[str] = None
    meta_description: Optional[str] = None
    h1_count: Optional[int] = None
    images_missing_alt: Optional[int] = None
    total_images: Optional[int] = None
    word_count: Optional[int] = None
    error: Optional[str] = None


# ---------- Error handling: never crash, always return sensible JSON ----------

@app.exception_handler(Exception)
async def catch_all_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Unexpected server error: {exc.__class__.__name__}"},
    )


# ---------- Routes ----------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/audit", response_model=AuditReport)
async def audit_url(payload: AuditRequest):
    url = payload.url
    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=408,
            detail=f"Request to {url} timed out after {TIMEOUT_SECONDS:.0f}s.",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to {url}. Check the domain and try again.",
        )
    except httpx.TooManyRedirects:
        raise HTTPException(status_code=502, detail="Too many redirects.")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Request failed: {e}")

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return AuditReport(
            url=url,
            status_code=response.status_code,
            response_time_ms=elapsed_ms,
            error=f"Response is not HTML (content-type: {content_type or 'unknown'}).",
        )

    if response.status_code >= 400:
        return AuditReport(
            url=url,
            status_code=response.status_code,
            response_time_ms=elapsed_ms,
            error=f"Page returned HTTP {response.status_code}.",
        )

    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        return AuditReport(
            url=url,
            status_code=response.status_code,
            response_time_ms=elapsed_ms,
            error=f"Failed to parse HTML: {e}",
        )

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_description = None
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_description = meta_desc_tag.get("content").strip()

    h1_count = len(soup.find_all("h1"))

    images = soup.find_all("img")
    total_images = len(images)
    images_missing_alt = sum(1 for img in images if not (img.get("alt") or "").strip())

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    word_count = len(re.findall(r"\b[\w'-]+\b", text))

    return AuditReport(
        url=url,
        status_code=response.status_code,
        response_time_ms=elapsed_ms,
        title=title,
        meta_description=meta_description,
        h1_count=h1_count,
        images_missing_alt=images_missing_alt,
        total_images=total_images,
        word_count=word_count,
    )


# ---------- Static frontend (must be mounted last) ----------
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
