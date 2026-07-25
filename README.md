# Page Pulse

A small web tool that audits any URL: HTTP status, response time, page title,
meta description, H1 count, images missing `alt` text, and approximate word count.

Built for the Digital Heroes SDE training task.

**Live demo:** https://page-pulse.fastapicloud.dev/
**Repo:** https://github.com/Swayam2905/PAGE_PULSE

## Stack

- **Backend:** FastAPI (Python), async requests via `httpx`, HTML parsing via `BeautifulSoup`
- **Frontend:** Static HTML/CSS/vanilla JS, served by FastAPI itself (no build step, no framework)
- **Tests:** `pytest`, with `httpx.AsyncClient` mocked so the suite never touches the real network

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000

### Running tests

```bash
pip install pytest
pytest -v
```

8 tests: the happy path, both required failure cases (connection error, timeout),
plus empty-URL validation, a non-HTML response, an upstream 4xx, and a health check.
All network calls are mocked, so the suite runs in under a second and never depends
on any real site being up.

## API Contract

### `POST /api/audit`

Audits a single URL and returns a health report.

**Request body:**
```json
{ "url": "example.com" }
```
`url` is required. A missing `https://` scheme is added automatically — you can
pass `example.com` or `https://example.com` interchangeably.

**Response body — success (`200`):**
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

| Field | Type | Notes |
|---|---|---|
| `url` | string | The normalized URL that was actually fetched |
| `status_code` | int \| null | HTTP status the target page returned |
| `response_time_ms` | int \| null | Time to fetch the page, in milliseconds |
| `title` | string \| null | Contents of `<title>`, if present |
| `meta_description` | string \| null | Contents of `<meta name="description">`, if present |
| `h1_count` | int \| null | Number of `<h1>` tags found |
| `images_missing_alt` | int \| null | `<img>` tags with no (or empty) `alt` attribute |
| `total_images` | int \| null | Total `<img>` tags found |
| `word_count` | int \| null | Approximate word count of visible text (scripts/styles stripped) |
| `error` | string \| null | Set when something went wrong; other fields may be partially filled |

**Error handling — the endpoint never crashes, it always returns structured JSON:**

| Situation | Response |
|---|---|
| Empty or malformed URL | `422` — FastAPI validation error |
| Connection failure (bad domain, DNS, refused) | `502` with a `detail` message |
| Timeout (10s) | `408` with a `detail` message |
| Too many redirects (>5) | `502` with a `detail` message |
| Response is not HTML (e.g. a JSON API, an image) | `200` with `error` set, no crash |
| Target page returns 4xx/5xx | `200` with `error` set — `status_code`/`response_time_ms` still reported |
| Anything unexpected | Caught by a global exception handler → `500` JSON, server stays up |

### `GET /api/health`

Returns `{"status": "ok"}`. Useful for uptime checks on free-tier hosts that spin down when idle.

## Design Decisions

**1. Upstream page errors (4xx/5xx) return `200` with an `error` field, not a `4xx` from Page Pulse itself.**
The distinction that matters to a caller is "did *my* API call fail" vs. "did the *page I asked about*
have a problem." If `leetcode.com` returns a 403 because it blocked the request, that's information
about leetcode.com, not a failure of Page Pulse's own contract — so Page Pulse still successfully
did its job (it audited the URL) and reports what it found. Reserving `4xx`/`5xx` from Page Pulse's own
endpoint for genuine request problems (bad input, connection failure, timeout) keeps the two failure
modes distinguishable for anyone consuming the API programmatically.

**2. `httpx.AsyncClient` is mocked in tests rather than hitting real websites.**
Testing against live URLs makes the suite flaky (a real site being slow, rate-limiting requests,
or changing its markup shouldn't break a CI run) and slow. Mocking the client at the same
seam the code already uses (`main.httpx.AsyncClient`) means the tests exercise the actual parsing
and error-handling logic — the part that's actually worth testing — without any network dependency.

**3. The frontend is a single static HTML file with vanilla JS, served directly by FastAPI, instead of
a separate frontend framework/build step.**
This is a small internal audit tool, not a product with a growing UI surface — there's no state
management complexity or component reuse that would justify React/Vue overhead. Serving the static
file via `StaticFiles` means one process, one deploy, one URL, which matters more for a small
tool than framework conveniences would.

## Deploy (free tier, no credit card)

**FastAPI Cloud** (built by the FastAPI team, genuinely free Hobby tier):
1. Install the CLI: `pip install "fastapi[standard]"`
2. `fastapi login`
3. `fastapi deploy`

Or **Render**:
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Free tiers on most hosts spin down after inactivity — the first request after idle can take
30-60s to wake back up. Not a bug, just how free hosting works.

## Notes

- CORS is wide open (`*`) since this is a small public utility with no auth or user data.
- Redirects are followed (max 5); a redirect loop or too-long chain returns a `502` instead of hanging.
- Word count is an approximation: script/style tags are stripped, then whitespace-delimited word
  tokens are counted via regex.
