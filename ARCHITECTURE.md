# V-Sentinel — Architecture, Models & Data Flow

> As-built reference for the team. Matches the code on `feat/v-sentinel-mvp` (52 tests passing).

## 1. What it is
A guardrail layer between the user and a Vietnamese chatbot. Every user turn passes through a 5-stage pipeline that decides **ALLOW / REFRAME / BLOCK**, then (for non-blocked turns) generates an answer and re-checks the output. Every decision carries a `DecisionTrace` shown in the UI panel.

## 2. Models & engines (all local)

| Role | Model / engine | How it's used | Fail behavior |
|------|----------------|---------------|---------------|
| **Chatbot** | `qwen2.5` (Ollama) | Generates the answer in Stage 3, with a safety system-prompt + retrieved legal context | On error → Vietnamese fallback message |
| **Safety classifier** | `qwen3guard` / Qwen3Guard-Gen (Ollama) | Stage 1 + Stage 4: returns `safe` / `controversial` / `unsafe` | On error/garbage → `controversial` (fail-safe, never silent `safe`) |
| **Jailbreak rules** | regex/keyword (no model) | Stage 1 **backbone** — decides even if Ollama is offline | Always available |
| **PII** | regex + context-gating (no model) | Stage 2 + Stage 4 (CCCD/CMND/phone/MST/email) | Deterministic |
| **Legal retrieval** | BM25 (`rank_bm25`, no model) — *default* | Stage 2 — cites the matching decree article | Deterministic |
| **Legal retrieval (optional)** | `bge-m3` + Neo4j AuraDB + cross-encoder rerank | Stage 2 — real reranked citations over ND-142 + FERPA + COPPA graph | Injected via `Sentinel(retriever=Neo4jRetriever())` |

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

## 5. Framework / public API

V-Sentinel is an importable Python package. `from vsentinel import Sentinel` is
the primary entry point; the FastAPI app and NeMo config are example consumers.

### `Sentinel` facade (`sentinel.py`)

The central class. Accepts optional `config`, `classifier`, and `chatbot`
callables. Exposes three methods: `run(message)`, `check_input(message)`, and
`check_output(answer)` — all returning typed Pydantic models.

### `Classifier` / `Chatbot` protocols (`backends.py`)

Structural protocols (no inheritance required). Any callable that matches the
signature is accepted:

- `Classifier`: `(text: str, role: str = "user") -> "safe" | "controversial" | "unsafe"`
- `Chatbot`: `(user_text: str, safety_directive: str, articles: list) -> str`

`OllamaClassifier` and `OllamaChatbot` are the packaged defaults; inject any
third-party LLM SDK by providing callables that satisfy the same signatures.

### `SentinelConfig` (`config.py`)

Dataclass with sane defaults (`ollama_url`, `chat_model`, `guard_model`,
`attack_threshold`, `retrieve_k`, `articles_path`). The `ollama_url`,
`chat_model`, and `guard_model` fields are ignored when custom backends are
injected.

### Packaged resources (`resources.py`, `resources/`)

Policy YAMLs and decree data are bundled inside the package and resolved via
`importlib.resources` so the library works from any install location. Helper
functions `policy_file(name)` and `data_file(name)` return `Path` objects.

### Decorators / wrappers (`integrations.py`)

`wrap(chat_fn, sentinel=None)` and `@guard(sentinel=None)` add guardrails to
any `f(message) -> reply` function without modifying its signature.

### Example consumers

- `api/main.py` — FastAPI web app (demo UI + `/chat` endpoint)
- `config/config.yml` + `config/rails/flows.co` — NeMo Guardrails wiring (optional)
- `examples/` — runnable standalone examples (see README)

## 6. Component / file map

```
src/vsentinel/
  __init__.py      public API surface (Sentinel, SentinelConfig, guard, wrap, …)
  sentinel.py      Sentinel facade — the main importable class
  backends.py      Classifier / Chatbot protocols + OllamaClassifier / OllamaChatbot
  config.py        SentinelConfig dataclass
  integrations.py  wrap() / @guard() helpers
  resources.py     importlib.resources helpers (policy_file, data_file)
  resources/
    policy/        jailbreak_patterns.yml, legal_policy.yml, pii_recognizers.yml,
                   reframe_templates.yml
    data/          decree_articles.json
  schema.py        DecisionTrace + sub-models (shared contract)
  normalize.py     Stage 0
  detect.py        Stage 1 rules
  guard_client.py  Stage 1/4 Qwen3Guard (Ollama)
  ollama_client.py Qwen2.5 transport
  pii.py           Stage 2/4 PII
  retrieve.py      Stage 2 BM25 (default retriever)
  retrievers/      optional Neo4j backend (bge-m3 + AuraDB + rerank, lazy heavy deps)
    neo4j_retriever.py  Neo4jRetriever facade (.search → list[Article])
    neo4j_config.py     Neo4jConfig (env creds) + corpus/router tables
    embedder.py · translator.py · reranker.py · driver.py · fusion.py · text_utils.py
  policy.py        Stage 2 decision
  generate.py      Stage 3 (Qwen2.5)
  verify.py        Stage 4
  pipeline.py      orchestrates 0→5
  rails_actions.py NeMo action (example consumer)
api/main.py        POST /chat, GET /  ← example consumer
web/index.html     chat + guardrail panel
examples/          quickstart.py · offline_fake_backend.py · custom_backend.py · decorator.py
eval/              run_eval.py · multijail_vi.py · xstest_vi.json
config/config.yml + config/rails/flows.co   NeMo wiring (example consumer)
```

## 7. Who owns what (2-person split)
- **Build (done):** the pipeline, API, UI, eval harness, NeMo wiring.
- **Teammate (data + legal, edits packaged resources — no code):**
  - `src/vsentinel/resources/policy/legal_policy.yml` → exact `Điều/Khoản` from ND-142/2026
  - `src/vsentinel/resources/data/decree_articles.json` → OCR'd decree articles (for BM25 citation)
  - `eval/multijail_vi.json` (jailbreak set) + `eval/xstest_vi.json` (over-refusal set)
  - the "Policy Leverage" report + demo video

## 8. Honest gaps to discuss
- **Default BM25 citations are seed placeholders** — but the optional `Neo4jRetriever` now serves *real* reranked citations over the teammate's ND-142 + FERPA + COPPA knowledge graph (`bge-m3` embeddings in AuraDB). Verified live. Remaining: decide whether Neo4j should back the demo, or fold its articles into the offline BM25 seed so the default also cites real text.
- **AuraDB Cypher uses `db.index.vector.queryNodes`**, which AuraDB now flags as deprecated in favor of `SEARCH` — works today, worth migrating.
- **Single-message scope** — no multi-turn/crescendo attack detection (deliberate YAGNI for the MVP).
- **`illegal` vs `attack`** currently split on "did a jailbreak rule fire" vs. "just unsafe content" — confirm this heuristic matches how the block should be framed legally. (Note: a spurious rule hit shadows `illegal` toward `attack`; keep rule precision high — see the `persona_dan`/"hướng dẫn" fix.)
- **Cross-law retrieval relevance** — *addressed*: uncertain Vietnamese queries now route to the VN decree only (`default_corpus="vn"`, language-gated), and a `min_reranker_score` floor (demo default 0.3 via `VSENTINEL_MIN_RERANK`) drops off-topic hits so an irrelevant question returns *no* citation instead of mislabeled US law. Verified live: health/benign → 0 citations, AI-duty query → ND-142, English FERPA query → FERPA. FERPA/COPPA remain reachable via keywords or explicit `law=`.
- Eval numbers need the real MultiJail-vi / XSTest-vi files to be meaningful.

## 9. Run

```bash
# live demo (needs Ollama)
ollama pull qwen2.5 && ollama pull qwen3guard
uv run uvicorn api.main:app --port 8000      # http://localhost:8000

uv run pytest -q                              # 52 tests

# optional: real reranked citations over the Neo4j legal graph
uv sync --extra neo4j && cp .env.example .env # then fill in NEO4J_* creds
uv run python -m eval.run_eval                # metrics
```
