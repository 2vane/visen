# V-Sentinel — Architecture, Models & Data Flow

> As-built reference for the team. Matches the code on `feat/v-sentinel-mvp` (34 tests passing).

## 1. What it is
A guardrail layer between the user and a Vietnamese chatbot. Every user turn passes through a 5-stage pipeline that decides **ALLOW / REFRAME / BLOCK**, then (for non-blocked turns) generates an answer and re-checks the output. Every decision carries a `DecisionTrace` shown in the UI panel.

## 2. Models & engines (all local)

| Role | Model / engine | How it's used | Fail behavior |
|------|----------------|---------------|---------------|
| **Chatbot** | `qwen2.5` (Ollama) | Generates the answer in Stage 3, with a safety system-prompt + retrieved legal context | On error → Vietnamese fallback message |
| **Safety classifier** | `qwen3guard` / Qwen3Guard-Gen (Ollama) | Stage 1 + Stage 4: returns `safe` / `controversial` / `unsafe` | On error/garbage → `controversial` (fail-safe, never silent `safe`) |
| **Jailbreak rules** | regex/keyword (no model) | Stage 1 **backbone** — decides even if Ollama is offline | Always available |
| **PII** | regex + context-gating (no model) | Stage 2 + Stage 4 (CCCD/CMND/phone/MST/email) | Deterministic |
| **Legal retrieval** | BM25 (`rank_bm25`, no model) | Stage 2 — cites the matching decree article | Deterministic |

**Key design principle:** deterministic layers (rules, PII, BM25) are the backbone; the two LLMs are a *second opinion*. Attacks are blocked even with no LLM running.

## 3. Data flow (per user message)

```
user message
  │
  ▼ STAGE 0  normalize(text) ─────────────► (normalized_text, obfuscation_flags)
  │            NFKC · diacritic-fold · strip zero-width · token-level de-leet · de-space
  │
  ▼ STAGE 1  score_rules(norm, flags) ────► (rule_score, rules_fired[OWASP])   ← backbone
  │          classify(raw, "user") ───────► guard_severity ∈ {safe,controversial,unsafe}
  │
  ▼          categorize(rule_score, rules, severity) ──► category
  │              rule_score ≥ 0.8          → attack
  │              severity == unsafe        → illegal
  │              severity == controversial → sensitive_legal
  │              else                      → benign
  │
  ▼ STAGE 2  decide(category, severity, retriever) ──► (decision, policy{reason,citations}, directive)
  │              attack          → BLOCK   (+ OWASP LLM01 + ND142 citation)
  │              illegal         → BLOCK   (+ ND142 decree citation)
  │              sensitive_legal → REFRAME (+ reframe directive, GDPR Art.9)
  │              benign          → ALLOW   (no citation)
  │
  ├── decision == BLOCK ──► short-circuit: final_message = refusal, return  (NO chatbot call)
  │
  ▼ STAGE 3  retrieve articles (BM25) → answer(msg, directive, articles)  [qwen2.5]
  │            (REFRAME injects the "answer responsibly, don't over-refuse" directive)
  │
  ▼ STAGE 4  check_output(reply)  [qwen3guard + PII]
  │              unsafe → BLOCK (decision overridden to BLOCK)
  │              PII    → REDACT (mask spans)
  │              else   → ALLOW
  │
  ▼ STAGE 5  DecisionTrace → FastAPI /chat (JSON) → UI guardrail panel
```

## 4. Decision states (what the panel shows)
- **ALLOWED** — benign, answered normally
- **BLOCKED (attack)** — jailbreak/injection, rule + OWASP tag
- **BLOCKED (illegal)** — unsafe content, decree citation
- **REFRAMED** — sensitive-but-legal (health/law), answered helpfully instead of refused
- plus the output-check verdict (ALLOW / REDACT / BLOCK) for the generated answer

## 5. Component / file map

```
src/vsentinel/
  schema.py        DecisionTrace + sub-models (shared contract)
  normalize.py     Stage 0
  detect.py        Stage 1 rules        ← config/policy/jailbreak_patterns.yml
  guard_client.py  Stage 1/4 Qwen3Guard (Ollama)
  ollama_client.py Qwen2.5 transport
  pii.py           Stage 2/4 PII        ← config/policy/pii_recognizers.yml
  retrieve.py      Stage 2 BM25         ← data/decree_articles.json
  policy.py        Stage 2 decision     ← config/policy/legal_policy.yml + reframe_templates.yml
  generate.py      Stage 3 (Qwen2.5)
  verify.py        Stage 4
  pipeline.py      orchestrates 0→5
  rails_actions.py NeMo action
api/main.py        POST /chat, GET /
web/index.html     chat + guardrail panel
eval/              run_eval.py · multijail_vi.py · xstest_vi.json
config/config.yml + config/rails/flows.co   NeMo wiring
```

## 6. Who owns what (2-person split)
- **Build (done):** the pipeline, API, UI, eval harness, NeMo wiring.
- **Teammate (data + legal, drops into config — no code):**
  - `config/policy/legal_policy.yml` → exact `Điều/Khoản` from ND-142/2026
  - `data/decree_articles.json` → OCR'd decree articles (for BM25 citation)
  - `eval/multijail_vi.json` (jailbreak set) + `eval/xstest_vi.json` (over-refusal set)
  - the "Policy Leverage" report + demo video

## 7. Honest gaps to discuss
- **Decree articles are seed placeholders** — the 97-page scan needs OCR before real citations appear.
- **Single-message scope** — no multi-turn/crescendo attack detection (deliberate YAGNI for the MVP).
- **`illegal` vs `attack`** currently split on "did a jailbreak rule fire" vs. "just unsafe content" — confirm this heuristic matches how the block should be framed legally.
- Eval numbers need the real MultiJail-vi / XSTest-vi files to be meaningful.

## 8. Run

```bash
# live demo (needs Ollama)
ollama pull qwen2.5 && ollama pull qwen3guard
uv run uvicorn api.main:app --port 8000      # http://localhost:8000

uv run pytest -q                              # 34 tests
uv run python -m eval.run_eval                # metrics
```
