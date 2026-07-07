# Planned Incorporation of Local LLM into PDO Dashboard
**Date:** 1 July 2026  
**Author:** Session — Claude Sonnet 4.6  
**Project:** Pune DO Market Share Dashboard  
**Repo:** `D:\Github\PDO-Dashboard-Demo`

---

## Why Local LLM (Not Cloud)

The dashboard works with internal petroleum sales data — district-wise volumes,
market shares, outlet-level figures. This data should not leave the machine.

The user's computer already has the following local LLM tools installed:
- **Ollama** — runs models via REST API at `http://localhost:11434` (recommended)
- **LM Studio** — GUI-based, also exposes an OpenAI-compatible API
- **Jan** — lightweight local LLM runner
- **AnythingLLM** — RAG + chat over documents
- **Open WebUI** — browser frontend for Ollama

No cloud subscription needed. No data leaves the machine. Models run offline.

---

## Recommended Model

**Ollama with Llama 3.2 (3B or 8B)** for the first phase.

```bash
# Install model (run once in terminal)
ollama pull llama3.2
# or for better SQL generation:
ollama pull mistral
ollama pull codellama
```

For SQL generation specifically, `sqlcoder` (by Defog) is purpose-built:
```bash
ollama pull defog/sqlcoder-7b-2
```

---

## Three Layers of AI Integration

### Layer 1 — Monthly Narrative Generator *(Start Here)*
**Effort:** Low (~50 lines of code)  
**Value:** High — saves writing the monthly DO summary  

After the Overview tab computes the OMC-wise market share table, a button
sends the numbers to the local LLM and gets back a plain-English paragraph:

> *"In June 2026, BPCL registered the strongest performance in Pune DO with a
> 10.88% volume growth YoY and a marginal share gain of +0.49 pp. IOCL showed
> robust growth at +13.50% with a +0.82 pp share improvement. HPCL, despite
> a 5.65% volume increase, lost 1.31 pp of market share — the largest share
> decline among the three PSU players. Industry total volume grew by 9.55%
> vs June 2025, indicating healthy overall demand."*

The LLM does not query the DB. It receives a pre-computed summary dict from
the existing dashboard computation and writes the narrative from that.

---

### Layer 2 — Natural Language Query Interface *(Phase 2)*
**Effort:** Medium (~150 lines of code + schema prompt engineering)  
**Value:** High — non-technical users can ask ad-hoc questions  

A new Streamlit tab: **"Ask the Dashboard"**

User types: *"Which 5 trading areas had the biggest IOCL drop in June 2026?"*  
→ LLM converts to SQL using the DB schema as context  
→ SQL runs on `pune_do.db`  
→ Result shown as a table + optional LLM explanation of results  

The LLM never sees raw data — only the schema description and the final
aggregated result. This keeps latency low and avoids context window issues.

---

### Layer 3 — Staging Resolution Assistant *(Phase 3)*
**Effort:** Low-Medium (~80 lines of code)  
**Value:** Saves monthly manual investigation of unmatched SAP codes  

When `staging_unknown_ros` has unmatched codes after an ingestion run, the
LLM looks at: RO name, district, volume pattern, and similar existing entries
in `dim_ro`, then suggests:

- *"This looks like a code change — volume pattern matches sap_code 377124's
  historical profile. Recommend legacy mapping."*
- *"New commissioning likely — no historical data for this code or similar names.
  Add to dim_ro."*
- *"Zero volume — safe to skip this month."*

User confirms or overrides. Resolution is written to `staging_unknown_ros.status`.

---

## Technical Architecture

### Ollama Integration (Python)

```python
# app/llm.py  — create this file

import requests
import json
from typing import Optional

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2"   # change to mistral or sqlcoder as needed

def ask_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
) -> str:
    """
    Send a prompt to the local Ollama instance and return the response text.
    Returns an error string if Ollama is not running or times out.
    """
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "⚠️ Ollama is not running. Start it with: ollama serve"
    except requests.exceptions.Timeout:
        return "⚠️ Ollama timed out. Try a smaller model or shorter prompt."
    except Exception as e:
        return f"⚠️ Error: {e}"


def is_ollama_running() -> bool:
    """Quick health check — show a warning in UI if Ollama is offline."""
    try:
        r = requests.get("http://localhost:11434", timeout=2)
        return r.status_code == 200
    except Exception:
        return False
```

---

### Layer 1 Implementation: Narrative Generator

```python
# In tab_01_overview.py (or wherever the OMC summary table is rendered)

from .llm import ask_ollama, is_ollama_running

def build_narrative_prompt(summary_dict: dict, period: str, fy: str) -> str:
    """
    summary_dict structure:
    {
      "BPCL": {"cy_vol": 18372, "ly_vol": 16569, "gr_pct": 10.88,
               "psu_shr_cy": 40.99, "psu_shr_ly": 40.50, "shr_diff": 0.49},
      "HPCL": {...},
      "IOCL": {...},
      "PSU":  {"cy_vol": 44820, "ly_vol": 40914, "gr_pct": 9.55},
    }
    """
    lines = [
        f"You are an analyst writing a brief performance summary for a petroleum"
        f" Divisional Office (Pune DO) covering districts Pune, Ahmednagar, and Satara.",
        f"",
        f"Period: {period}, FY {fy}",
        f"",
        f"Data:",
    ]
    for omc, d in summary_dict.items():
        if omc == "PSU":
            lines.append(
                f"  PSU Total: CY Vol={d['cy_vol']:,} KL, LY Vol={d['ly_vol']:,} KL,"
                f" Growth={d['gr_pct']:+.2f}%"
            )
        else:
            lines.append(
                f"  {omc}: CY Vol={d['cy_vol']:,} KL, LY={d['ly_vol']:,} KL,"
                f" Growth={d['gr_pct']:+.2f}%,"
                f" PSU Share CY={d['psu_shr_cy']:.2f}%,"
                f" LY={d['psu_shr_ly']:.2f}%,"
                f" Change={d['shr_diff']:+.2f} pp"
            )
    lines += [
        f"",
        f"Write a 3-4 sentence executive summary of this data. Be factual and concise."
        f" Mention who gained/lost share and the overall industry trend."
        f" Do not use bullet points. Do not add any disclaimers.",
    ]
    return "\n".join(lines)


# In the Streamlit tab:
if st.button("🤖 Generate AI Summary", disabled=not is_ollama_running()):
    with st.spinner("Thinking..."):
        prompt = build_narrative_prompt(summary_dict, period_label, fy_code)
        narrative = ask_ollama(prompt)
    st.info(narrative)

if not is_ollama_running():
    st.caption("⚠️ Local AI offline — run `ollama serve` to enable.")
```

---

### Layer 2 Implementation: Text-to-SQL

```python
# app/llm_sql.py

DB_SCHEMA = """
Database: pune_do.db (SQLite)

Tables:

fact_monthly:
  sap_code     TEXT   -- retail outlet identifier
  ta_code      TEXT   -- trading area code (e.g. M06-005)
  rsa_code     TEXT   -- RSA code (e.g. M06)
  omc          TEXT   -- oil company: BPCL, HPCL, IOCL, NEL, RBML, SIMPL
  district     TEXT   -- Pune, Ahmednagar, or Satara
  product      TEXT   -- MS (petrol) or HSD (diesel)
  fy_code      TEXT   -- financial year e.g. '2026-27'
  month_label  TEXT   -- e.g. 'JUN.26'
  month_index  INT    -- 1=Apr, 2=May, 3=Jun ... 12=Mar
  volume_kl    REAL   -- sales volume in kilolitres
  is_negative  INT    -- 1 if negative (returns), else 0

dim_ro:
  sap_code     TEXT PRIMARY KEY
  ro_name      TEXT
  omc          TEXT
  district     TEXT
  rsa_code     TEXT
  rsa_name     TEXT
  trading_area TEXT
  ta_code      TEXT
  com          TEXT   -- commission category
  category     TEXT   -- outlet type
  yoc          TEXT   -- year of commissioning e.g. '2020-21'

Notes:
- Current FY is '2026-27'. June 2026 = month_index=3, month_label='JUN.26'
- PSU = BPCL + HPCL + IOCL
- Market share = OMC volume / PSU total volume * 100
"""

SYSTEM_SQL_PROMPT = f"""
You are a SQL expert. Given the schema below, convert the user's question
into a valid SQLite SELECT query. Return ONLY the SQL query — no explanation,
no markdown, no backticks.

{DB_SCHEMA}
"""

def text_to_sql(question: str) -> str:
    prompt = SYSTEM_SQL_PROMPT + f"\n\nQuestion: {question}\n\nSQL:"
    return ask_ollama(prompt, model="defog/sqlcoder-7b-2")


def run_nl_query(question: str, con) -> tuple[str, pd.DataFrame | None, str]:
    """
    Returns: (sql_generated, result_df, error_message)
    """
    sql = text_to_sql(question)
    # Basic safety check — allow only SELECT
    if not sql.strip().upper().startswith("SELECT"):
        return sql, None, "Only SELECT queries are allowed."
    try:
        df = pd.read_sql(sql, con)
        return sql, df, ""
    except Exception as e:
        return sql, None, str(e)
```

**Streamlit UI for the Query tab:**
```python
st.title("💬 Ask the Dashboard")
st.caption("Powered by local Ollama — no data leaves your machine")

question = st.text_input(
    "Ask a question about the data:",
    placeholder="Which 5 TAs had the biggest IOCL drop in June 2026?",
)

if question and st.button("Run"):
    with st.spinner("Generating SQL..."):
        sql, df, err = run_nl_query(question, con)
    st.code(sql, language="sql")
    if err:
        st.error(f"Query error: {err}")
    elif df is not None:
        st.dataframe(df)
        # Optional: ask LLM to explain result
        explanation = ask_ollama(
            f"The user asked: '{question}'\n"
            f"The result has {len(df)} rows. First few rows:\n{df.head().to_string()}\n\n"
            f"Write one sentence explaining this result plainly."
        )
        st.caption(explanation)
```

---

### Layer 3 Implementation: Staging Resolution Assistant

```python
# In tab_16_ingest.py, staging review section

def classify_unknown_ro(row: dict, similar_ros: list[dict]) -> str:
    """
    row: one record from staging_unknown_ros
    similar_ros: dim_ro records with similar names (fuzzy match)
    """
    similar_text = "\n".join(
        f"  - {r['sap_code']} | {r['ro_name']} | {r['district']} | legacy={r.get('legacy_sap_codes','')}"
        for r in similar_ros[:5]
    ) or "  (none found)"

    prompt = f"""
You are helping classify an unmatched retail outlet SAP code from a petroleum
company's monthly sales file.

Unmatched code details:
  SAP code in file: {row['file_code']}
  Name in file:     {row['ro_name']}
  District:         {row['district']}
  MS volume (KL):   {row['ms_kl']}
  HSD volume (KL):  {row['hsd_kl']}

Similar outlets already in the master database:
{similar_text}

Based on this, classify the unmatched code as ONE of:
  A) NEW_COMMISSIONING  — brand new outlet, add to dim_ro
  B) LEGACY_MAP         — code change; map old code to an existing outlet
  C) SKIP               — zero or negligible volume, safe to ignore this month
  D) UNCLEAR            — cannot determine, needs human review

Reply with the letter (A/B/C/D), then a one-line reason.
Example: "B — volume and name closely match sap_code 377124 (COCO Kokamthan)."
"""
    return ask_ollama(prompt)
```

---

## Suggested New Tab Structure

Add **Tab 17: AI Insights** to the dashboard with three sections:

| Section | Description |
|---------|-------------|
| 📝 Monthly Narrative | Auto-generate performance summary for selected month |
| 💬 Ask the Dashboard | Natural language → SQL → results |
| 🔍 Staging Assistant | Review unmatched codes with AI suggestions |

---

## Implementation Sequence

| Priority | Task | File | Effort |
|----------|------|------|--------|
| 1 | Create `app/llm.py` with Ollama connector + health check | New file | 1 hour |
| 2 | Add Narrative button to Overview tab | `tab_01_overview.py` | 1 hour |
| 3 | Create `app/llm_sql.py` with text-to-SQL | New file | 2 hours |
| 4 | Add "Ask the Dashboard" tab (Tab 17) | New file | 2 hours |
| 5 | Add Staging Resolution Assistant to ingest tab | `tab_16_ingest.py` | 2 hours |
| 6 | Pull and test `defog/sqlcoder-7b-2` for better SQL | Terminal | 30 min |

**Total estimated effort: ~8 hours of focused development**

---

## Dependencies to Add

```txt
# requirements.txt additions
requests>=2.31.0   # already likely present; used for Ollama API calls
```

No new Python packages needed beyond `requests`, which is almost certainly
already installed. Ollama itself is already on the machine.

---

## Important Constraints

1. **Ollama must be running** (`ollama serve`) for AI features to work.
   Dashboard must degrade gracefully when Ollama is offline — hide AI buttons
   or show a clear "AI offline" message. Never block the main dashboard.

2. **LLM output is advisory** — for text-to-SQL especially, always show the
   generated SQL to the user before executing, and catch exceptions.

3. **No raw data to LLM** — always pass aggregated summaries (totals, percentages)
   to the narrative generator, never raw fact_monthly rows. This keeps prompts
   short and avoids leaking individual outlet data.

4. **Model size** — Llama 3.2 3B runs comfortably on most machines. If the
   machine has a GPU (NVIDIA detected in session), Ollama will use it automatically
   for faster inference.

---

## Future Possibilities (Not Planned Yet)

- **Automated monthly report draft** — generate a full Word document report
  using the `docx` skill + LLM narrative layer
- **Anomaly alerts** — LLM flags statistically unusual patterns automatically
- **Competitor intelligence** — integrate web search to pull competitor news
  and cross-reference with market share trends
- **Voice interface** — Whisper (local STT) → question → Ollama → answer,
  all running offline

---

*Document created: 1 July 2026 · To be implemented in next development session*
