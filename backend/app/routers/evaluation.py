from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..db import get_db
from ..models import EvalRun, User
from ..services import audit, evaluation

router = APIRouter(prefix="/api", tags=["evaluation"])


@router.get("/eval")
def latest_runs(user: User = Depends(require("manager", "admin")), db: Session = Depends(get_db)):
    """Latest stored result per mode (pipeline and baselines)."""
    out = {}
    for run in db.scalars(select(EvalRun).order_by(EvalRun.at.desc())):
        out.setdefault(run.mode, {"at": run.at.isoformat(), **run.results})
    return out


@router.post("/eval/run")
def run_rules_eval(user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    """Re-run the rule-based pipeline on the labelled set (a few seconds). Model runs use the CLI."""
    facts, rules = evaluation.seeded_ledger()
    result = evaluation.run("pipeline_rules", facts, rules)
    db.add(EvalRun(mode="pipeline_rules", results=result))
    audit.record(db, user, "eval.run", "eval", None,
                 f"Evaluation (rules): {result['drafts']} drafts in {result['seconds']} s.")
    db.commit()
    return result
