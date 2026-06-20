from __future__ import annotations
from vsentinel.pipeline import run

def evaluate(attacks: list[str], benign: list[str]) -> dict:
    blocked_attacks = sum(1 for a in attacks if run(a).decision == "BLOCK")
    blocked_benign = sum(1 for b in benign if run(b).decision == "BLOCK")
    n_a, n_b = max(1, len(attacks)), max(1, len(benign))
    return {
        "detection_rate": blocked_attacks / n_a,
        "false_positive_rate": blocked_benign / n_b,
        "over_refusal_rate": blocked_benign / n_b,
        "n_attacks": len(attacks),
        "n_benign": len(benign),
    }

if __name__ == "__main__":
    import json
    from pathlib import Path
    from eval.multijail_vi import load_vi
    benign = json.loads((Path(__file__).parent / "xstest_vi.json").read_text(encoding="utf-8"))
    metrics = evaluate(load_vi(limit=50), benign)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
