# Scrapper Tool

**Track:** Part 1 — Getting Data Out of a Platform That Doesn't Want You To  
**Stack:** Python (FastAPI, HTTPX, BeautifulSoup4)
---

### 1. Why this ingestion strategy over the obvious alternative rejected?

**The Obvious Alternative:** Spinning up a headless browser cluster (Playwright / Puppeteer / Selenium).

**Why I Rejected It:**
Headless browsers are the standard go-to, but they are heavy and fragile. A single Chromium tab easily eats ~150MB RAM and significant CPU. More importantly, default headless instances leave massive detection footprints (DevTools protocol hooks, `navigator.webdriver = true`, missing audio/video codecs, WebGL shader anomalies) that modern anti-bot systems flag within seconds.

**What I Built Instead:**
A **Tiered Stealth HTTP Client paired with Structured Schema Extraction**:
1. **Low Footprint & High Speed:** Pure async HTTP/2 requests with realistic Chrome/Safari header ordering, platform hints (`Sec-CH-UA`), and Box-Muller Gaussian jitter (800ms–2500ms) to avoid robotic timing patterns.
2. **Resilience to Markup Drift:** Instead of relying on fragile CSS classes that change weekly, the parser prioritizes embedded Schema.org `<script type="application/ld+json">` tags (which sites maintain for Google SEO) and falls back to semantic heuristic clustering.
3. **Graceful Degradation:** When a 429 or 403 occurs, a domain-level circuit breaker quarantines the target and backs off rather than hammering the server or attempting brittle hacks.

---

### 2. One trade-off made under the time limit, and what I'd do with a real week.

**The Trade-off:**
To keep the application zero-dependency and runnable on free cloud instances, state management (rate limiter tokens, proxy health scoring, and circuit breaker status) is stored in-memory in the Python process rather than backed by a distributed database.

**What I'd Build with a Full Week:**
1. **Durable Distributed Queues:** Replace in-memory state with Celery/Temporal + Redis for fault-tolerant worker distribution and scheduled retries.
2. **Socket-Level TLS Fingerprinting:** Use `curl_cffi` to replicate exact browser JA3/TLS ClientHello handshakes.
3. **Rotating Residential IP Pool:** Integrate back-connect residential proxy providers with ASN reputation tracking.
4. **Micro-LLM Extraction Fallback:** Add a quantized local model (e.g. Llama 3 8B) to infer structured job data from completely unstructured DOM snippets when regex heuristics fail.

---

### 3. Where did you use AI tools, and what did you personally verify or change afterward?

**Where AI was used:**
- Generating initial boilerplate for HTML/CSS dashboard layouts.
- Drafting starting regex patterns for salary and job title extraction.

**What I personally designed, verified, and changed:**
- **Replaced Uniform Delays with Gaussian Jitter:** AI initially suggested standard `random.uniform()`. I replaced this with a Box-Muller transform because uniform distributions trigger bot behavior heuristics.
- **Engineered Circuit Breaker State Machine:** Implemented the `CLOSED -> OPEN -> HALF_OPEN` transitions with canary recovery probes so transient blocks don't cause permanent pipeline failures.
- **Implemented Payload Anomaly Scoring:** Wrote confidence checks (0–100%) to ensure empty or truncated HTML responses trigger alarms instead of silently corrupting downstream data.
- **Audited Client Hints:** Manually inspected real Chrome 124 network traces to ensure `Sec-CH-UA`, platform versions, and accept headers strictly matched.
