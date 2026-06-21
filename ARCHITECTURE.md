# V-Sentinel — Architecture, Models & Data Flow

> As-built reference for the team. Matches the code on `dev`/`main` (144 tests passing).

## 1. What it is
A guardrail layer between the user and a Vietnamese chatbot. Every user turn passes through a 5-stage pipeline that decides **ALLOW / REFRAME / BLOCK**, then (for non-blocked turns) generates an answer and re-checks the output. Every decision carries a `DecisionTrace` shown in the UI panel.

## 2. Models & engines (all local)

| Role | Model / engine | How it's used | Fail behavior |
|------|----------------|---------------|---------------|
| **Chatbot** | `qwen2.5` (Ollama) | Generates the answer in Stage 3, with a safety system-prompt + retrieved legal context | On error → Vietnamese fallback message |
| **Safety classifier** | `qwen2.5` (Ollama); pluggable via `VSENTINEL_GUARD_MODEL` | Stage 1 + Stage 4: returns `safe` / `controversial` / `unsafe` | On error/garbage → `controversial` (fail-safe, never silent `safe`) |
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
  │            NFKC · diacritic-fold · strip zero-width · de-space · FLAG leet (never rewrite —
  │            so "70kg" stays "70kg"; leet is decoded for matching in Stage 1, not in the text)
  │
  ▼ STAGE 1  score_rules(norm, flags) ────► (rule_score, rules_fired[OWASP])   ← backbone
  │            scans the text + scan-only variants (base64-decoded, leet-decoded)
  │          classify(raw, "user") ───────► guard_severity ∈ {safe,controversial,unsafe}
  │          detect_domain(norm) ─────────► domain ∈ {public_service,education,healthcare,general}
  │
  ▼          categorize(rule_score, rules, severity) ──► category
  │              rule_score ≥ 0.8          → attack
  │              severity == unsafe        → illegal
  │              severity == controversial → sensitive_legal
  │              else                      → benign
  │
  ▼ STAGE 2  decide(category, severity, retriever, domain) ─► (decision, policy{reason,citations}, directive)
  │              attack          → BLOCK   (+ OWASP LLM01 + ND142 — domain-agnostic)
  │              illegal         → BLOCK   (+ ND142 + per-domain framework)
  │              sensitive_legal → REFRAME (+ reframe directive + per-domain framework)
  │              benign          → ALLOW   (no citation)
  │            per-domain framework: education→FERPA/COPPA · health→GDPR/PDPD · public-service→PDPD/ND142
  │
  ├── decision == BLOCK ──► short-circuit: final_message = refusal, return  (NO chatbot call)
  │
  ▼ STAGE 3  retrieve articles (BM25) → answer(msg, directive, articles)  [qwen2.5]
  │            (REFRAME injects the "answer responsibly, don't over-refuse" directive)
  │
  ▼ STAGE 4  check_output(reply)  [qwen2.5 classifier + PII]
  │              unsafe → BLOCK (decision overridden to BLOCK)
  │              PII    → REDACT (mask spans)
  │              else   → ALLOW
  │
  ▼ STAGE 5  DecisionTrace → FastAPI → UI guardrail panel
               /chat (built-in UI)  ·  /v1/chat/completions (OpenAI-compatible proxy)
               every decision recorded to /recent for the live-monitor dashboard
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

- `api/main.py` — thin demo: wraps the library service (`vsentinel.server.create_app`) and adds the browser UI at `/`
- `vsentinel.server.create_app()` / `vsentinel serve` — the guardrail HTTP service itself (`/chat`, OpenAI + Ollama proxy, `/recent`), part of the SDK
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
    policy/        jailbreak_patterns.yml, legal_policy.yml, domain_policy.yml,
                   pii_recognizers.yml, reframe_templates.yml
    data/          decree_articles.json
  schema.py        DecisionTrace + sub-models (shared contract)
  normalize.py     Stage 0 (flags leet; never rewrites the text)
  detect.py        Stage 1 rules (base64 + leet decoded as scan-only targets)
  domains.py       Stage 1 domain routing (public_service/education/healthcare)
  guard_client.py  Stage 1/4 safety classifier (Ollama; qwen2.5, pluggable)
  ollama_client.py Qwen2.5 transport
  pii.py           Stage 2/4 PII
  retrieve.py      Stage 2 BM25 (default retriever)
  retrievers/      optional Neo4j backend (bge-m3 + AuraDB + rerank, lazy heavy deps)
    neo4j_retriever.py  Neo4jRetriever facade (.search → list[Article])
    neo4j_config.py     Neo4jConfig (env creds) + corpus/router tables
    embedder.py · translator.py · reranker.py · driver.py · fusion.py · text_utils.py
  policy.py        Stage 2 decision (domain-aware citations via domain_policy.yml)
  generate.py      Stage 3 (Qwen2.5)
  verify.py        Stage 4
  pipeline.py      orchestrates 0→5
  rails_actions.py NeMo action (example consumer)
  cli.py           `vsentinel` CLI (check / serve / version)
  client.py        VSentinelClient — HTTP client for a running service
  py.typed         PEP 561 marker (ships type hints)
  server/          the guardrail HTTP service (part of the SDK)
    app.py            create_app() + build_default_sentinel() + auth/rate-limit
    openai_compat.py  OpenAI proxy (/v1/chat/completions, /v1/models)
    ollama_compat.py  Ollama proxy (/api/chat, /api/tags, /api/version)
    proxy_common.py   shared chat-message model + latest-user extraction
    store.py          in-memory ring buffer powering the /recent monitor feed
api/main.py        thin demo: create_app(...) + GET / (web UI)  ← example consumer
web/index.html     chat + guardrail panel + live-monitor toggle
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

### Hardened (production gap sweep)
- **Retrieval degrades, never crashes** — the Neo4j path is wrapped in `FallbackRetriever(Neo4jRetriever, Retriever)`: any failure (connection loss, offline index, model load) falls back to offline BM25 instead of 500-ing the request. The Neo4j retriever also reconnects+retries once on a dropped connection.
- **Generation/output screening fail closed** — `Sentinel.run` guards the chatbot call (→ safe Vietnamese fallback) and the output check (→ BLOCK) so a backend exception can't crash a turn.
- **Detection breadth** — base64-encoded payloads are decoded from the *raw* message and re-scanned (normalize lowercases, so decoding must precede it); added high-precision Chinese/Indonesian "ignore instructions" patterns; prefix-injection now tolerates a leading directive.
- **Non-destructive normalization** — leet-decoding no longer rewrites the canonical text (it corrupted legitimate numerics like `70kg`→`tokg`); `normalize` only *flags* in-word leet, and `score_rules` decodes leet as a scan-only target — so retrieval, the trace, and the user-visible text stay intact while detection still fires on `1gn0r3 4ll …`.
- **Domain-aware legal framing** — `decide` attaches the jurisdiction matching the data at stake (education→FERPA/COPPA, health→GDPR/PDPD, public-service→PDPD/ND-142; attacks stay OWASP-only), fixing wrong-jurisdiction citations (e.g. an education turn no longer cited health GDPR). Citations are de-duped.
- **Guardrail proxy** — OpenAI-compatible (`/v1/chat/completions`, `/v1/models`) and Ollama-native (`/api/chat`, `/api/tags`) endpoints let any chat client (Open WebUI, Jan, Codex CLI, Enchanted, …) route through V-Sentinel; the screened answer is returned in the client's wire format, every decision is recorded to `/recent`, and the web UI doubles as a live monitor.
- **PII** — added BHXH / passport / bank-account recognizers; context match is now bidirectional + word-boundary + diacritic-folded (catches keyword-after-number, kills substring false positives).
- **Output check** — now flags system-prompt leakage in the generated answer.
- **Prompt-injection via retrieved text** — article snippets are flattened, length-clamped, and fenced as untrusted reference data in the system prompt.
- **API** — bounded input (`max_length`), generic 500 handler (no stack-trace leak), `/health`, request/decision logging, and env-gated optional API-key + in-memory rate limit (off by default). Startup degrades to BM25 if Neo4j is unreachable.
- **Config validation** — `SentinelConfig`/`Neo4jConfig` reject out-of-range values at construction.
- **Cross-law retrieval relevance** — uncertain Vietnamese queries route to the VN decree only (`default_corpus="vn"`, language-gated); a `min_reranker_score` floor (demo default 0.3 via `VSENTINEL_MIN_RERANK`) drops off-topic hits. Verified live: health/benign → 0 citations, AI-duty → ND-142, English FERPA → FERPA. Language detection now folds diacritics so unaccented Vietnamese routes correctly.

### Still open (deliberately deferred)
- **Default BM25 citations are seed placeholders** — the optional `Neo4jRetriever` serves real reranked citations; remaining choice is whether Neo4j backs the demo or its articles get folded into the BM25 seed.
- **AuraDB Cypher uses `db.index.vector.queryNodes`** (deprecated in favor of `SEARCH`) — works on 5.x; migrating needs a live AuraDB verification pass, so left until creds are rotated and re-tested.
- **Single-message scope** — no multi-turn/crescendo detection (changes the architecture; YAGNI for the MVP).
- **`illegal` vs `attack`** split on "did a jailbreak rule fire" vs. "just unsafe content" — confirm the heuristic matches the intended legal framing (a spurious rule hit shadows `illegal`→`attack`; keep rule precision high).
- **Eval is unified and domain-aware, data still modest** — `eval.run_eval` now runs the hardened `Sentinel` path over a 47/47 attack/benign set across public-service/education/healthcare and reports `over_refusal_by_domain`, `detection_by_domain` and a fail-safe (LLM-down) rate. For headline report numbers, scale the MultiJail-vi / XSTest-vi sets further.

## 9. Run

```bash
# live demo (needs Ollama)
ollama pull qwen2.5          # chatbot + safety classifier (one model)
uv run uvicorn api.main:app --port 8000      # http://localhost:8000

# use as a guardrail proxy from any OpenAI-compatible chat app:
#   base URL http://localhost:8000/v1 · any api key · model qwen2.5
# then click "👁 Theo dõi trực tiếp" on the dashboard to watch the traffic.

uv run pytest -q                              # 144 tests

# optional: real reranked citations over the Neo4j legal graph
uv sync --extra neo4j && cp .env.example .env # then fill in NEO4J_* creds
uv run python -m eval.run_eval                # metrics
```
