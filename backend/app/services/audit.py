from sqlalchemy.orm import Session

from ..models import AuditLog, User


def record(db: Session, actor: User | None, action: str, entity_type: str, entity_id: int | None, summary: str,
           draft_id: int | None = None, **details) -> AuditLog:
    entry = AuditLog(actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
                     entity_id=entity_id, draft_id=draft_id, summary=summary, details=details)
    db.add(entry)
    return entry
