"""Safety eval for the Vietnamese guardrail.

Runs an attack set (jailbreak attempts) and a benign set (XSTest-style
over-refusal probes) through the SAME hardened pipeline the demo uses and
reports detection / over-refusal, a per-category breakdown, and a fail-safe
detection rate (deterministic rule backbone only, LLM classifier unavailable).

Items may be plain strings or ``{"prompt", "category"}`` records.
"""
from __future__ import annotations

from vsentinel.pipeline import run


def _prompt(item) -> str:
    return item["prompt"] if isinstance(item, dict) else item


def _category(item) -> str:
    return item.get("category", "uncategorized") if isinstance(item, dict) else "uncategorized"


def _domain(item) -> str:
    return item.get("domain", "unspecified") if isinstance(item, dict) else "unspecified"


def _by_category(items: list, blocked: list[bool]) -> dict:
    agg: dict[str, dict[str, int]] = {}
    for item, hit in zip(items, blocked):
        cat = agg.setdefault(_category(item), {"total": 0, "blocked": 0})
        cat["total"] += 1
        cat["blocked"] += int(hit)
    return {
        c: {"detected": v["blocked"], "total": v["total"],
            "rate": round(v["blocked"] / v["total"], 3)}
        for c, v in sorted(agg.items())
    }


def _by_domain(items: list, blocked: list[bool]) -> dict:
    """Per-domain block-rate. For attacks => detection; for benign => over-refusal."""
    agg: dict[str, dict[str, int]] = {}
    for item, hit in zip(items, blocked):
        dom = agg.setdefault(_domain(item), {"total": 0, "blocked": 0})
        dom["total"] += 1
        dom["blocked"] += int(hit)
    return {
        d: {"blocked": v["blocked"], "total": v["total"],
            "rate": round(v["blocked"] / v["total"], 3)}
        for d, v in sorted(agg.items())
    }


def evaluate(attacks: list, benign: list) -> dict:
    attack_blocked = [run(_prompt(a)).decision == "BLOCK" for a in attacks]
    benign_blocked = [run(_prompt(b)).decision == "BLOCK" for b in benign]
    n_a, n_b = max(1, len(attacks)), max(1, len(benign))
    return {
        "detection_rate": sum(attack_blocked) / n_a,
        "over_refusal_rate": sum(benign_blocked) / n_b,
        "false_positive_rate": sum(benign_blocked) / n_b,  # alias, kept for back-compat
        "detection_by_category": _by_category(attacks, attack_blocked),
        "detection_by_domain": _by_domain(attacks, attack_blocked),
        "over_refusal_by_domain": _by_domain(benign, benign_blocked),
        "n_attacks": len(attacks),
        "n_benign": len(benign),
    }


def failsafe_detection(attacks: list) -> float:
    """Detection rate with the LLM classifier down — deterministic rules only.

    Simulates Ollama being unavailable (classifier degrades to 'controversial')
    and measures how many attacks the rule backbone still blocks on its own.
    Uses ``check_input`` so no generation/Ollama call is made.
    """
    from vsentinel.sentinel import Sentinel

    guard = Sentinel(
        classifier=lambda text, role="user": "controversial",
        chatbot=lambda *a, **k: "",
    )
    blocked = sum(1 for a in attacks if guard.check_input(_prompt(a)).decision == "BLOCK")
    return round(blocked / max(1, len(attacks)), 3)


if __name__ == "__main__":
    import json
    from pathlib import Path

    from eval.multijail_vi import load_vi

    attacks = load_vi()
    benign = json.loads((Path(__file__).parent / "xstest_vi.json").read_text(encoding="utf-8"))
    metrics = evaluate(attacks, benign)
    metrics["failsafe_detection_rate"] = failsafe_detection(attacks)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
