"""Run the labelled test set through BrandSentinel and the baselines; write counts to eval/results/.

    python eval/run_eval.py                      # rules-only pipeline (seconds)
    python eval/run_eval.py --modes all          # + local AI judge and both LLM baselines (needs Ollama; minutes)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import evaluation, llm  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
ALL = ["pipeline_rules", "pipeline_ai", "llm_brand_guide", "llm_structured_facts"]


def summary(r: dict) -> str:
    s = r["severity"]
    def frac(p, m):
        n, d = (p["tp"], p["tp"] + p["fn"]) if m == "recall" else (p["tp"], p["tp"] + p["fp"])
        return f"{n}/{d}" if d else "—"
    lines = [
        f"## {r['mode']}  ({r['drafts']} drafts, {r['seconds']} s)",
        f"- Critical recall: {frac(s['critical'], 'recall')} (target ≥ 0.95, met: {s['critical']['meets_target']})",
        f"- Major precision {frac(s['major'], 'precision')}, recall {frac(s['major'], 'recall')} (target ≥ 0.90, met: {s['major']['meets_target']})",
        f"- Minor precision: {frac(s['minor'], 'precision')}",
        f"- Findings citing the correct fact: {r['evidence']['correct']}/{r['evidence']['total']}",
        f"- Problem claims flagged with any non-supported outcome: {r['problem_claims_flagged']['caught']}/{r['problem_claims_flagged']['total']}",
        f"- False alarms per clean draft: {r['false_alarms_per_clean_draft']} ({r['clean_drafts']} clean drafts)",
    ]
    if r.get("corrections"):
        lines.append(f"- Corrections passing all three checks: {r['corrections']['passed_all_checks']}/{r['corrections']['proposed']}")
    lines.append("- Per check (caught / precision): " + "; ".join(
        f"{c} {v['tp']}/{v['tp'] + v['fn']} · {v['tp']}/{v['tp'] + v['fp']}" for c, v in r["categories"].items()))
    if r["misses"]:
        lines.append("- Misses: " + "; ".join(f"{m['id']} {m['cat']} “{m['quote']}”" for m in r["misses"]))
    if r["false_alarms"]:
        lines.append("- False alarms: " + "; ".join(f"{m['id']} {m['cat']} “{m['quote']}”" for m in r["false_alarms"]))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="pipeline_rules", help="comma list or 'all'")
    args = ap.parse_args()
    modes = ALL if args.modes == "all" else args.modes.split(",")
    if any(m != "pipeline_rules" for m in modes) and not (llm.local_available() or llm.external_available()):
        sys.exit("A model is needed for these modes: start Ollama or set EXTERNAL_LLM_* variables.")
    facts, rules = evaluation.seeded_ledger()
    RESULTS.mkdir(exist_ok=True)
    for mode in modes:
        print(f"Running {mode}…", flush=True)
        r = evaluation.run(mode, facts, rules)
        if mode != "pipeline_rules":
            from app.config import settings
            r["model"] = settings.local_llm_model if llm.local_available() else settings.external_llm_model
        (RESULTS / f"{mode}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        print(summary(r), flush=True)


if __name__ == "__main__":
    main()
