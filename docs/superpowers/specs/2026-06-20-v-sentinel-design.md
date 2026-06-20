# V-Sentinel — Design Spec

**Date:** 2026-06-20
**Context:** Global South AI Sprint hackathon (2026-06-19 → 2026-06-21).
**One-liner:** A guardrail layer that sits between users and a Vietnamese public-service/healthcare chatbot, performing *dual* risk control — jailbreak/prompt-injection detection **and** legal/safety compliance with Nghị định 142/2026/NĐ-CP (the implementing decree for Vietnam's AI Law).

---

## 1. Positioning

Nghị định 142/2026/NĐ-CP details **Luật Trí tuệ nhân tạo** (AI Law, Luật 63/2025/QH15), signed 30/4/2026. Verified from the source PDF (`material/142-2026-ndcp.signed.pdf`, 97 pages, scanned):

- **Chương I** — definitions (*hệ thống trí tuệ nhân tạo*, *rủi ro*, *mô hình AI*); **Điều 4** establishes a national AI portal/database.
- **Chương II** — *Phân loại và đánh giá sự phù hợp hệ thống TTNT*: risk-based **classification + conformity assessment** (Điều 5: classify by *mức độ rủi ro*), plus transparency/registration duties.

This is EU-AI-Act-style risk tiering in Vietnamese law. **V-Sentinel is therefore pitched as a conformity tool** that helps a deployed chatbot meet ND-142/2026's risk-classification, transparency, and monitoring obligations — not merely a content filter. This is the project's original, defensible framing and the core of the "AI sovereignty" pitch.

## 2. Goals / Non-goals

**Goals (MVP, 2 days):**
- A working wrapper around a local chatbot that classifies each user turn and routes it to one of: **ALLOW / REFRAME / BLOCK**.
- Defeat Vietnamese-language evasion (the central thesis: Western guardrails leak in Vietnamese).
- Reduce **over-refusal** on sensitive-but-legal questions (health/law) by reframing instead of refusing.
- Cite the specific legal/standard basis for every block (ND-142/2026, PDPD, OWASP, GDPR).
- A visual demo: chat UI + live "guardrail panel" showing the decision trace.
- Real eval numbers for the report.

**Non-goals (explicit YAGNI):**
- No model fine-tuning (Qwen3Guard-Gen is used off-the-shelf).
- No vector database — RAG citation is keyword/BM25 over a small article set.
- No NER PII model — regex + context-gated recognizers only.
- No multi-turn/conversation-state attack detection (single-message scope for the MVP).
- No production auth/scaling — local demo only.

## 3. Architecture — five-stage pipeline

```
User input
  │
▼ STAGE 0 · Vietnamese normalization (normalize.py)
   NFKC, diacritic folding, strip zero-width chars, homoglyph map,
   decode leetspeak/base64 → normalized text + obfuscation flags
  │
▼ STAGE 1 · Risk scoring & categorization (detect.py + guard_client.py)
   1a deterministic matcher (VN+EN patterns, OWASP-LLM01 tagged)  ← BACKBONE
   1b Qwen3Guard-Gen-0.6B via Ollama → severity safe|controversial|unsafe
   → risk{score, category∈[attack|illegal|sensitive_legal|benign], guard_severity, rules_fired[]}
  │
▼ STAGE 2 · Policy engine (policy.py + pii.py + retrieve.py)
   consults: VN rules (legal_policy.yml from decree), PII detector,
             GDPR/PDPD map, OWASP tags; BM25-retrieves matching article(s)
   → decision{ALLOW|REFRAME|BLOCK} + citations[] + safety system-prompt
  │
▼ STAGE 3 · Generation (generate.py)
   Qwen2.5 (Ollama) answers, with safety prompt + retrieved legal context
  │
▼ STAGE 4 · Output verification (verify.py)
   re-scan answer: PII leakage, prohibited content, Qwen3Guard severity
   → ALLOW | REDACT | BLOCK
  │
▼ STAGE 5 · Action / behavior
   final_message + full DecisionTrace → API → UI guardrail panel
```

**Orchestration:** NVIDIA NeMo Guardrails runs input/output rails that call custom Python actions (`rails_actions.py`) wrapping the pipeline. Core decision logic lives in plain, unit-testable Python so the demo is never hostage to Colang or a flaky model.

**Four user-visible decision states:** ALLOWED · BLOCKED (security) · BLOCKED (illegal, cited) · REFRAMED (sensitive-but-legal → answered helpfully).

## 4. Repo layout (uv-managed Python project)

```
pyproject.toml                      uv-managed deps
README.md
config/
  config.yml                        NeMo Guardrails: models (qwen2.5 main, qwen3guard), rails
  rails/*.co                        Colang input/output rail flows
  policy/
    jailbreak_patterns.yml          VN+EN deterministic patterns, each OWASP-tagged
    legal_policy.yml                categories → ND142/2026 Điều/Khoản + OWASP + GDPR/PDPD tags + action
    pii_recognizers.yml             VN PII regex + context words
    reframe_templates.yml           safe-rewrite templates per sensitive category
src/vsentinel/
  schema.py                         DecisionTrace + dataclasses (SHARED CONTRACT — build first)
  normalize.py                      Stage 0
  detect.py                         Stage 1 deterministic matcher + scoring
  guard_client.py                   Qwen3Guard-Gen-0.6B via Ollama
  ollama_client.py                  Qwen2.5 chat wrapper
  pii.py                            Stage 2 Presidio VN recognizers
  policy.py                         Stage 2 policy engine
  retrieve.py                       Stage 2 BM25 over decree articles
  generate.py                       Stage 3
  verify.py                         Stage 4
  pipeline.py                       orchestrates stages → DecisionTrace
  rails_actions.py                  NeMo custom actions wrapping pipeline
api/main.py                         FastAPI POST /chat → {answer, trace}
web/index.html                      chat + live guardrail panel (vanilla JS, no build step)
data/decree_articles.json           OCR'd relevant ND-142/2026 articles, chunked (teammate-sourced)
eval/
  multijail_vi.py                   load MultiJail vi subset, run, metrics
  xstest_vi.json                    translated over-refusal prompts (teammate-sourced)
  run_eval.py                       detection accuracy / over-refusal rate / FPR
tests/
  test_normalize.py test_detect.py test_policy.py test_pii.py
```

## 5. Shared contract — DecisionTrace

Every module reads/writes pieces of this; the UI renders it. Defined in `schema.py` first so parallel builders agree on the interface.

```
DecisionTrace:
  input_raw: str
  input_normalized: str
  obfuscation_flags: list[str]            # e.g. ["leetspeak", "zero_width", "diacritic_stripped"]
  risk:
    score: float                          # 0..1
    category: "attack" | "illegal" | "sensitive_legal" | "benign"
    guard_severity: "safe" | "controversial" | "unsafe"
    rules_fired: list[{id: str, owasp_tag: str}]
  decision: "ALLOW" | "REFRAME" | "BLOCK"
  policy:
    reason: str
    citations: list[{source: "ND142/2026"|"PDPD"|"GDPR"|"OWASP", ref: str, text: str}]
  pii:
    found: list[{type: str, span: [int,int], action: "redact"|"flag"}]
  generation:
    used_reframed_prompt: bool
    retrieved_articles: list[{ref: str, snippet: str}]
  output_check:
    verdict: "ALLOW" | "REDACT" | "BLOCK"
    redactions: list[str]
  final_action: str
  final_message: str
  latency_ms: int
```

## 6. Policy config schema (`legal_policy.yml`)

Each rule is data-driven and carries multi-framework traceability — this is what makes the *report* strong without building three engines:

```yaml
- id: anti_state_content
  category: illegal
  match: { guard_severity: [unsafe], rules: [anti_state_*] }
  action: BLOCK
  citations:
    - { source: ND142/2026, ref: "Điều X Khoản Y", text: "..." }   # teammate fills exact refs
    - { source: OWASP, ref: "LLM01", text: "Prompt Injection" }
  refusal_message_vi: "..."

- id: medical_advice_sensitive
  category: sensitive_legal
  match: { guard_severity: [controversial], topics: [health] }
  action: REFRAME
  reframe_template: medical_safe
  citations:
    - { source: GDPR, ref: "Art. 9", text: "special-category health data" }
```

## 7. Error handling (demo-safe by design)

- Deterministic rules are the backbone — they decide even with every model offline.
- Ollama/Qwen3Guard timeout or down → rules decide; **fail-closed on attack/illegal**, warn-and-allow on benign; surface the degraded state in the trace.
- Unparseable Qwen3Guard output → treat as `controversial` → REFRAME (never silently ALLOW).
- All external input validated; local-only; no secrets committed; no PII logged.

## 8. Tech stack

Python 3.13 (uv), NeMo Guardrails, Ollama (`qwen2.5` chatbot + `qwen3guard` classifier), Microsoft Presidio (PII), `rank_bm25` (RAG), FastAPI + Uvicorn, vanilla HTML/JS UI (no build), pytest.

## 9. Evaluation plan

- **Jailbreak detection:** MultiJail Vietnamese subset → detection rate, false-positive rate.
- **Over-refusal:** ~250 XSTest prompts translated to Vietnamese → over-refusal rate (lower is better).
- **Report numbers:** baseline (raw chatbot) vs V-Sentinel on both metrics; ablation rules-only vs rules+Qwen3Guard.

## 10. Team division (2 people)

**Build team (user + Claude agent team):** the 8 modules, API, UI, pipeline, NeMo config, eval scripts.

**Teammate (Vietnamese-native, no training):**
1. **Data:** clean MultiJail-vi; translate ~250 XSTest → `xstest_vi.json`; curate ~10 jailbreak + ~10 sensitive-but-legal demo prompts.
2. **Legal:** extract chatbot-relevant ND-142/2026 articles (prohibited practices, risk tiers Chương II, transparency) → fill `legal_policy.yml` citations + `decree_articles.json`; map to PDPD (NĐ 13/2023) and GDPR/EU AI Act.
3. **Report + 2-min demo video** ("Policy Leverage" writeup).

## 11. Build waves (parallel agent team)

- **Wave 0 (foundation, sequential):** `uv init` + `pyproject.toml`; `schema.py` (shared contract); `config/` skeleton; OCR relevant decree articles → `data/decree_articles.json`.
- **Wave 1 (parallel, one module each against the schema):** normalize · detect+patterns · guard/ollama clients · pii · policy+retrieve+reframe · api+web · eval harness. Each ships with its unit tests (TDD).
- **Wave 2 (integrate):** `pipeline.py` + `rails_actions.py` + NeMo config wired end-to-end; run eval; polish demo.

## 12. References (verified live, 2026-06-20)

- ND-142/2026/NĐ-CP — source PDF in `material/` (implements Luật TTNT 63/2025/QH15).
- MultiJail (Vietnamese-inclusive jailbreak set) — Deng et al., ICLR 2024, arXiv:2310.06474; github.com/DAMO-NLP-SG/multilingual-safety-for-LLMs. Thesis support: non-English prompts ~3× more harmful content.
- XSTest (over-refusal benchmark) — Röttger et al., arXiv:2308.01263 (translate to VN).
- Aya Red-Teaming — **NOT used** (8 languages, Vietnamese absent): huggingface.co/datasets/walledai/AyaRedTeaming.
- Qwen3Guard — Qwen Team, arXiv:2510.14276; huggingface.co/Qwen/Qwen3Guard-Gen-4B (0.6B/4B/8B, 119 langs incl. VN, Apache-2.0, GGUF for Ollama).
- Llama Guard 3 / ShieldGemma — **NOT used** (no Vietnamese support).
- OWASP Top 10 for LLM Applications 2025 — genai.owasp.org (LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, …).
- NeMo Guardrails — docs.nvidia.com/nemo/guardrails (Ollama engine, self-check input/output rails).
- Microsoft Presidio — github.com/microsoft/presidio (custom VN PatternRecognizers).
- Vietnam data law mapping — Nghị định 13/2023/NĐ-CP (PDPD); GDPR Art. 5/9/17; EU AI Act risk tiers.

## 13. Open items (teammate-provided, plug into config)

- Exact ND-142/2026 article references for each policy rule (`legal_policy.yml`).
- `data/decree_articles.json` content (OCR + human-selected articles).
- `eval/xstest_vi.json` (translated over-refusal prompts).
- Demo prompt set.
