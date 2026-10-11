# SmogGuard AI 🛡️🌫️ — Predict. Explain. Protect.

**SmogGuard AI** is a policy-grounded air quality advisory engine and intelligence platform built for Lahore, Pakistan (Loopverse 3.0 Challenge). It combines statistical machine learning, domain-specific rule evaluation engines, and safety-guarded Large Language Models (LLMs) to deliver deterministic, verifiable decision support for public health alerts, school closures, vehicle restrictions, and industrial emissions controls.

---

## 🏛️ System Architecture

SmogGuard AI operates on a **Direct-Answer First** intelligence pipeline designed to eliminate ambiguity in public safety messaging. Every query flows through multi-stage guardrails before rendering a decision.

```
                    ┌───────────────────────────┐
                    │       User Query          │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Prompt Injection Filter   │
                    │   & Scope Sanitizer       │
                    └─────────────┬─────────────┘
                                  │
                      ┌───────────┴───────────┐
                      ▼                       ▼
           ┌─────────────────────┐ ┌─────────────────────┐
           │ Document Retrieval  │ │ PM2.5 Ridge Model   │
           │ (BM25 Engine)       │ │ (15 Lahore Sensors) │
           └──────────┬──────────┘ └──────────┬──────────┘
                      │                       │
                      └───────────┬───────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Rule Engine & Threshold   │
                    │   Evaluator (DOC-03, etc) │
                    └─────────────┬─────────────┘
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
            ┌────────────────────┐ ┌────────────────────┐
            │ Groq LLM Rephraser │ │ Deterministic      │
            │ (Strict Grounding) │ │ Fallback Generator │
            └──────────┬─────────┘ └─────────┬──────────┘
                       │                     │
                       └──────────┬──────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Citation & Grounding      │
                    │ Verification Guardrail    │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Direct Answer First Output│
                    └───────────────────────────┘
```

---

## 🎯 Solved Logic Traps & Safety Traps

SmogGuard AI natively resolves 7 core edge cases and logic traps embedded in complex air quality policy management:

| # | Challenge Trap | Resolution & Implementation |
|---|---|---|
| **1** | **Future Leakage Prevention** | All features use `.shift(1)`. Model trained on Sep backtests, tested on Oct. Holdout rows feed predictions forward recursively without accessing future sensor data. |
| **2** | **Network Mismatch & Alignment** | Realigns UTC timestamps to PKT (Asia/Karachi) and converts AQI to PM2.5 mass concentration ($\mu\text{g/m}^3$) using EPA breakpoints before daily area averaging. |
| **3** | **Broken & Flatline Values** | Sentinel values (`-999`) filled across networks; S07 3-day flatline fault confirmed and interpolated cleanly. |
| **4** | **Policy Versioning (`DOC-03` vs `DOC-02`)** | Explicitly overrides superseded 2023 regulations (`DOC-02`, $300\text{ }\mu\text{g/m}^3$) with active Version 2 policies (`DOC-03`, effective 2026-09-20). |
| **5** | **Prompt Injection Defense (`DOC-07`)** | Strips hidden HTML comment attacks and quarantines visible prompt injections using `_INJECTION_RE` regex and evidence-only system prompts. |
| **6** | **Consecutive-Day Vehicle Rules (`DOC-05`)** | Evaluates multi-day forecast matrices to ensure odd-even vehicle rotation triggers *only* on **2+ consecutive hazardous days** ($\ge 165\text{ }\mu\text{g/m}^3$). |
| **7** | **Out-of-Scope Geographic Refusal (`DOC-13`)** | Rejects speculative queries for unmonitored locations (e.g., Karachi, Islamabad, Faisalabad) with explicit scope refusals citing `DOC-13`. |

---

## ⚡ Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Rebuild predictions & data pipeline (~6s)
python run_pipeline.py

# 3. Launch application server (Dashboard on http://localhost:8002)
python -m uvicorn app.server:app --port 8002

# 4. Single-question terminal query
python ask.py "Will schools in Gulberg close tomorrow?"

# 5. Run test suite (123 tests)
pytest -v
```

---

## 🛠️ API & Endpoint Documentation

### 1. `POST /api/ask`
Submits a query to the advisory engine.

**Request Body:**
```json
{
  "question": "Will schools in Wagah remain open tomorrow?",
  "lang": "en"
}
```

**Response:**
```json
{
  "answer": "Direct Answer: Yes, schools in Wagah will remain open with normal timings.\nEvidence: The forecasted PM2.5 level (109 µg/m³) is below the 165 µg/m³ restriction threshold.\nCitations: DOC-03 (Version 2).\n\nForecast for Wagah, tomorrow (2026-10-29): about 109 µg/m³ PM2.5 — not hazardous (below the 165 µg/m³ threshold).\nSource: SmogGuard team model (Ridge regression), not an official forecast.\n- Decisions are made the evening before, using the next-day forecast for the school's area. [DOC-03]\nThis is the current school policy (DOC-03, Version 2, effective 2026-09-20). It replaced DOC-02, so the older thresholds no longer apply. [DOC-03]",
  "sources": ["DOC-03"],
  "forecast_called": true,
  "groq_status": "accepted"
}
```

### 2. `GET /api/overview`
Returns live system health, sensor network status, and recent model accuracy metrics.

---

## 🤖 LLM Rephraser & Guardrails

An optional LLM (Groq free tier) rephrases answers when `GROQ_API_KEY` is set in the environment. Every LLM output is strictly validated and rejected if it:
* Adds an ungrounded number not present in retrieved evidence or forecast tool output.
* Cites an unretrieved document tag or drops a `[DOC-XX]` citation string.
* Claims the air is safe or attempts instruction overriding.
* Fails network calls, rate limits, or validation checks (falling back instantly to the deterministic composer).

---

## 📂 Repository Layout

```
smogguard/
  assistant.py        Core ask() decision engine & deterministic template composer
  llm.py              Groq LLM integration & safety validator
  documents.py        Sanitizer, chunker, & BM25 document retriever
  forecast_tool.py    forecast(location, target_date) query tool
  data_pipeline.py    Timezone alignment, AQI conversion, sentinel/flatline cleaner
  model.py            Feature engineering, Ridge regression model, recursive forecast
app/
  server.py           FastAPI server (/api/ask, /api/overview, /api/forecast)
  static/             Local dashboard interface with voice speech input
tests/                Automated test suite (123 pytest cases)
run_pipeline.py       Rebuilds predictions.csv and pipeline artifacts
ask.py                Command line query interface
validate_submission.py Verifies submission format and prediction shapes
```# SmogGuard AI 🛡️🌫️ — Predict. Explain. Protect.

**SmogGuard AI** is a policy-grounded air quality advisory engine and intelligence platform built for Lahore, Pakistan (Loopverse 3.0 Challenge). It combines statistical machine learning, domain-specific rule evaluation engines, and safety-guarded Large Language Models (LLMs) to deliver deterministic, verifiable decision support for public health alerts, school closures, vehicle restrictions, and industrial emissions controls.

---

## 🏛️ System Architecture

SmogGuard AI operates on a **Direct-Answer First** intelligence pipeline designed to eliminate ambiguity in public safety messaging. Every query flows through multi-stage guardrails before rendering a decision.

```
                    ┌───────────────────────────┐
                    │       User Query          │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Prompt Injection Filter   │
                    │   & Scope Sanitizer       │
                    └─────────────┬─────────────┘
                                  │
                      ┌───────────┴───────────┐
                      ▼                       ▼
           ┌─────────────────────┐ ┌─────────────────────┐
           │ Document Retrieval  │ │ PM2.5 Ridge Model   │
           │ (BM25 Engine)       │ │ (15 Lahore Sensors) │
           └──────────┬──────────┘ └──────────┬──────────┘
                      │                       │
                      └───────────┬───────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Rule Engine & Threshold   │
                    │   Evaluator (DOC-03, etc) │
                    └─────────────┬─────────────┘
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
            ┌────────────────────┐ ┌────────────────────┐
            │ Groq LLM Rephraser │ │ Deterministic      │
            │ (Strict Grounding) │ │ Fallback Generator │
            └──────────┬─────────┘ └─────────┬──────────┘
                       │                     │
                       └──────────┬──────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Citation & Grounding      │
                    │ Verification Guardrail    │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │ Direct Answer First Output│
                    └───────────────────────────┘
```

---

## 🎯 Solved Logic Traps & Safety Traps

SmogGuard AI natively resolves 7 core edge cases and logic traps embedded in complex air quality policy management:

| # | Challenge Trap | Resolution & Implementation |
|---|---|---|
| **1** | **Future Leakage Prevention** | All features use `.shift(1)`. Model trained on Sep backtests, tested on Oct. Holdout rows feed predictions forward recursively without accessing future sensor data. |
| **2** | **Network Mismatch & Alignment** | Realigns UTC timestamps to PKT (Asia/Karachi) and converts AQI to PM2.5 mass concentration ($\mu\text{g/m}^3$) using EPA breakpoints before daily area averaging. |
| **3** | **Broken & Flatline Values** | Sentinel values (`-999`) filled across networks; S07 3-day flatline fault confirmed and interpolated cleanly. |
| **4** | **Policy Versioning (`DOC-03` vs `DOC-02`)** | Explicitly overrides superseded 2023 regulations (`DOC-02`, $300\text{ }\mu\text{g/m}^3$) with active Version 2 policies (`DOC-03`, effective 2026-09-20). |
| **5** | **Prompt Injection Defense (`DOC-07`)** | Strips hidden HTML comment attacks and quarantines visible prompt injections using `_INJECTION_RE` regex and evidence-only system prompts. |
| **6** | **Consecutive-Day Vehicle Rules (`DOC-05`)** | Evaluates multi-day forecast matrices to ensure odd-even vehicle rotation triggers *only* on **2+ consecutive hazardous days** ($\ge 165\text{ }\mu\text{g/m}^3$). |
| **7** | **Out-of-Scope Geographic Refusal (`DOC-13`)** | Rejects speculative queries for unmonitored locations (e.g., Karachi, Islamabad, Faisalabad) with explicit scope refusals citing `DOC-13`. |

---

## ⚡ Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Rebuild predictions & data pipeline (~6s)
python run_pipeline.py

# 3. Launch application server (Dashboard on http://localhost:8002)
python -m uvicorn app.server:app --port 8002

# 4. Single-question terminal query
python ask.py "Will schools in Gulberg close tomorrow?"

# 5. Run test suite (123 tests)
pytest -v
```

---

## 🛠️ API & Endpoint Documentation

### 1. `POST /api/ask`
Submits a query to the advisory engine.

**Request Body:**
```json
{
  "question": "Will schools in Wagah remain open tomorrow?",
  "lang": "en"
}
```

**Response:**
```json
{
  "answer": "Direct Answer: Yes, schools in Wagah will remain open with normal timings.\nEvidence: The forecasted PM2.5 level (109 µg/m³) is below the 165 µg/m³ restriction threshold.\nCitations: DOC-03 (Version 2).\n\nForecast for Wagah, tomorrow (2026-10-29): about 109 µg/m³ PM2.5 — not hazardous (below the 165 µg/m³ threshold).\nSource: SmogGuard team model (Ridge regression), not an official forecast.\n- Decisions are made the evening before, using the next-day forecast for the school's area. [DOC-03]\nThis is the current school policy (DOC-03, Version 2, effective 2026-09-20). It replaced DOC-02, so the older thresholds no longer apply. [DOC-03]",
  "sources": ["DOC-03"],
  "forecast_called": true,
  "groq_status": "accepted"
}
```

### 2. `GET /api/overview`
Returns live system health, sensor network status, and recent model accuracy metrics.

---

## 🤖 LLM Rephraser & Guardrails

An optional LLM (Groq free tier) rephrases answers when `GROQ_API_KEY` is set in the environment. Every LLM output is strictly validated and rejected if it:
* Adds an ungrounded number not present in retrieved evidence or forecast tool output.
* Cites an unretrieved document tag or drops a `[DOC-XX]` citation string.
* Claims the air is safe or attempts instruction overriding.
* Fails network calls, rate limits, or validation checks (falling back instantly to the deterministic composer).

---

## 📂 Repository Layout

```
smogguard/
  assistant.py        Core ask() decision engine & deterministic template composer
  llm.py              Groq LLM integration & safety validator
  documents.py        Sanitizer, chunker, & BM25 document retriever
  forecast_tool.py    forecast(location, target_date) query tool
  data_pipeline.py    Timezone alignment, AQI conversion, sentinel/flatline cleaner
  model.py            Feature engineering, Ridge regression model, recursive forecast
app/
  server.py           FastAPI server (/api/ask, /api/overview, /api/forecast)
  static/             Local dashboard interface with voice speech input
tests/                Automated test suite (123 pytest cases)
run_pipeline.py       Rebuilds predictions.csv and pipeline artifacts
ask.py                Command line query interface
validate_submission.py Verifies submission format and prediction shapes
```