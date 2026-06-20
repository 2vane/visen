from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

Category = Literal["attack", "illegal", "sensitive_legal", "benign"]
Severity = Literal["safe", "controversial", "unsafe"]
Decision = Literal["ALLOW", "REFRAME", "BLOCK"]
Verdict = Literal["ALLOW", "REDACT", "BLOCK"]

class RuleHit(BaseModel):
    id: str
    owasp_tag: str = ""

class Citation(BaseModel):
    source: Literal["ND142/2026", "PDPD", "GDPR", "OWASP"]
    ref: str
    text: str = ""

class PiiHit(BaseModel):
    type: str
    span: tuple[int, int]
    action: Literal["redact", "flag"] = "redact"

class Article(BaseModel):
    ref: str
    snippet: str = ""

class RiskInfo(BaseModel):
    score: float = 0.0
    category: Category = "benign"
    guard_severity: Severity = "safe"
    rules_fired: list[RuleHit] = Field(default_factory=list)

class PolicyInfo(BaseModel):
    reason: str = ""
    citations: list[Citation] = Field(default_factory=list)

class OutputCheck(BaseModel):
    verdict: Verdict = "ALLOW"
    redactions: list[str] = Field(default_factory=list)

class DecisionTrace(BaseModel):
    input_raw: str
    input_normalized: str = ""
    obfuscation_flags: list[str] = Field(default_factory=list)
    risk: RiskInfo = Field(default_factory=RiskInfo)
    decision: Decision = "ALLOW"
    policy: PolicyInfo = Field(default_factory=PolicyInfo)
    pii: list[PiiHit] = Field(default_factory=list)
    used_reframed_prompt: bool = False
    retrieved_articles: list[Article] = Field(default_factory=list)
    output_check: OutputCheck | None = None
    final_message: str = ""
    latency_ms: int = 0
