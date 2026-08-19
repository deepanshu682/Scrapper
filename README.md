# Aegis - Resilient Job Ingestion Engine

A production-grade, unauthenticated job ingestion pipeline built in Python to reliably extract job listings from platforms that actively defend against automated clients (such as LinkedIn, RemoteOK, and HackerNews) without getting IPs burned, crashing on markup changes, or violating ethical boundaries.

 
🌐 **Live Demo:** [https://aegis-scraper-engine.onrender.com/](https://aegis-scraper-engine.onrender.com/)

---

## What This Project Solves

Most web scrapers break within a week because:
1. **Robotic Pacing:** Fixed request intervals trigger behavioral anomaly detection.
2. **Brittle CSS Selectors:** Weekly frontend changes or obfuscated CSS classes (`_8x9z_item`) silently return empty data.
3. **Cascading IP Bans:** Continued requests after a 429 (Too Many Requests) or 403 (Forbidden) response get the client's IP blacklisted.
4. **Heavyweight Overkill:** Spinning up headless Chromium instances uses huge memory and leaves obvious DevTools fingerprint flags.

**Aegis solves this with a lightweight, multi-tiered architecture:**
- **Pacing with Gaussian Jitter:** Uses the Box-Muller transform to create natural, human-like request intervals (800ms–2500ms).
- **Domain Circuit Breaker:** Automatically trips on 429/403 errors, quarantines the domain, and tests recovery with canary probes.
- **4-Tier Resilient Parser:** Falls back from CSS selectors to embedded Schema.org JSON-LD, then to heuristic content-density clustering, backed by a payload quality confidence score.
- **Real-Time Telemetry:** Streams live HTTP events, header configurations, and circuit state transitions over Server-Sent Events (SSE) to an interactive dashboard.

---

## Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- `pip`

### 2. Installation
Clone the repository and install the dependencies:
```bash
git clone https://github.com/deepanshu682/Scrapper.git
cd Scrapper
pip install -r requirements.txt
```

### 3. Run the Server
Start the FastAPI server:
```bash
python run.py
```
Open your browser and navigate to:
```
http://localhost:3000
```

### 4. Run the Test Suite
Run the unit tests to verify the rate limiter, circuit breaker, JSON-LD fallback, heuristic extraction, and challenge detection:
```bash
python -m unittest discover -s tests
```

---

## Supported Sources & Test Scenarios

The engine includes both live public sources and controlled sandbox environments:

| Source / Scenario | Description | Strategy Used |
| :--- | :--- | :--- |
| **Jobicy** | Live remote tech job feed | Direct API with structured payload validation |
| **RemoteOK** | Live developer job board | Multi-tier DOM parser with Schema.org fallback |
| **HackerNews** | Live "Who is Hiring?" thread | Unstructured text parser with regex entity extraction |
| **LinkedIn (Public)** | Public unauthenticated search (`/jobs-guest/...`) | Realistic Client Hints + JSON-LD extraction (no login required) |
| **Sandbox: Schema Drift** | Simulates complete CSS class obfuscation | Recovers data via Tier 2 (JSON-LD) and Tier 3 (Heuristics) |
| **Sandbox: Rate Limit Storm** | Simulates receiving consecutive 429 errors | Trips the Circuit Breaker into `OPEN` quarantine state |
| **Sandbox: Anti-Bot Challenge** | Simulates a Cloudflare challenge page | Detects challenge signature, halts requests, and backs off |

---

## Project Structure

```
.
├── server/
│   ├── main.py                  # FastAPI application & SSE telemetry stream
│   ├── stealth/
│   │   ├── fingerprints.py      # Browser profile rotation & Sec-CH-UA client hints
│   │   ├── rate_limiter.py      # Box-Muller Gaussian jitter & token bucket rate limiter
│   │   └── stealth_client.py    # Async HTTPX client, cookie jar, & challenge detector
│   └── engine/
│       ├── circuit_breaker.py   # Domain circuit breaker (CLOSED -> OPEN -> HALF_OPEN)
│       ├── parser.py            # 4-tier parser (CSS -> JSON-LD -> Heuristics -> Scorer)
│       ├── orchestrator.py      # Ingestion pipeline coordinator
│       └── sources/             # Source handlers (Jobicy, RemoteOK, HN, LinkedIn, Sandbox)
├── public/                      # Dashboard UI (HTML, CSS, JavaScript)
├── tests/
│   └── test_engine.py           # Automated unit test suite
├── ARCHITECTURE.md              # In-depth technical architecture & detection surface analysis
├── DECISIONS.md                 # 1-page design decisions & trade-offs document
├── Dockerfile                   # Container build definition
├── requirements.txt             # Python dependencies
└── run.py                       # Server entrypoint
```

---

## Ethical & Operational Boundaries

How Aegis defines its personal and technical boundaries:
- **Zero Authenticated Harvesting:** Aegis operates strictly on unauthenticated, public job listings. It never attempts to bypass login screens, store user session cookies, or touch private accounts.
- **No PII Collection:** The engine extracts public job metadata only (title, company, salary, location, description). It strictly ignores and never collects candidate profiles, resumes, personal emails, or phone numbers.
- **Respectful Server Load:** Aegis enforces token bucket rate caps, Gaussian pacing intervals, and honors exponential backoff when a server signals rate limits to ensure zero degradation of upstream capacity.

---

## Deployment & Live Demo

- **Live Deployed URL (Render):** [https://aegis-scraper-engine.onrender.com/](https://aegis-scraper-engine.onrender.com/)

The application is containerized and ready to deploy on any cloud platform:

- **Docker:**
  ```bash
  docker build -t aegis-scraper .
  docker run -p 3000:3000 aegis-scraper
  ```
- **Render / Railway:** Preconfigured with `render.yaml` and `railway.json` in the root directory.
