"""Reference data every database needs: business settings and compatibility rules. Idempotent."""

from sqlalchemy.orm import Session

from app.modules.admin import service as settings
from app.modules.compatibility import service as compatibility


def seed_reference(db: Session) -> None:
    settings.seed(db)
    compatibility.seed(db)
    db.commit()
