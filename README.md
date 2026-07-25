# Page Pulse

A small web tool that audits any URL: HTTP status, response time, page title,
meta description, H1 count, images missing `alt` text, and approximate word count.

Built for the Digital Heroes SDE training task ("Build Page Pulse").

## Stack
- **Backend:** FastAPI (Python), async requests via `httpx`, HTML parsing via `BeautifulSoup`
- **Frontend:** Static HTML/CSS/vanilla JS, served by FastAPI itself (no build step)

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000

## API

`POST /api/audit`

Request body:
```json
{ "url": "example.com" }
```
(Scheme is optional — `https://` is added automatically if missing.)

Response body (200):
```json
{
  "url": "https://example.com",
  "status_code": 200,
  "response_time_ms": 184,
  "title": "Example Domain",
  "meta_description": null,
  "h1_count": 1,
  "images_missing_alt": 0,
  "total_images": 0,
  "word_count": 28,
  "error": null
}
```

Error handling:
- Invalid/empty URL → `422` with a validation message
- Connection failure (bad domain, DNS, refused) → `502`
- Timeout (10s) → `408`
- Non-HTML response (e.g. a JSON API, an image) → `200` with `error` set, no crash
- Upstream page returns 4xx/5xx → `200` with `error` set, status/time still reported
- Anything unexpected → caught by a global handler, returns `500` JSON — the server never crashes

`GET /api/health` → `{"status": "ok"}`, useful for uptime checks on free-tier hosts.

## Deploy (free tier)

**Render** (recommended, no config file needed beyond what's here):
1. Push this repo to GitHub.
2. On [render.com](https://render.com) → New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Deploy. Render assigns a `*.onrender.com` URL — that's your live link.

**Railway** works the same way and also reads the included `Procfile` automatically.

## Notes
- CORS is wide open (`*`) since this is a small public utility with no auth or user data.
- Redirects are followed (max 5); a redirect loop or too-long chain returns a `502` instead of hanging.
- Word count is an approximation: script/style tags are stripped, then whitespace-delimited word tokens are counted.
