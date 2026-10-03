"""Import every module's models so Alembic and create_all see the full schema."""

from app.modules.admin import models as admin  # noqa: F401
from app.modules.audit import models as audit  # noqa: F401
from app.modules.auth import models as auth  # noqa: F401
from app.modules.compatibility import models as compatibility  # noqa: F401
from app.modules.donors import models as donors  # noqa: F401
from app.modules.forecasting import models as forecasting  # noqa: F401
from app.modules.inventory import models as inventory  # noqa: F401
from app.modules.matching import models as matching  # noqa: F401
from app.modules.notifications import models as notifications  # noqa: F401
from app.modules.redistribution import models as redistribution  # noqa: F401
from app.modules.requests import models as requests  # noqa: F401
from app.modules.sites import models as sites  # noqa: F401
