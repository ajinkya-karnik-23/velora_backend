"""Model import hub — import every model here so Alembic's target_metadata discovers them."""

from app.models.base import Base  # noqa: F401
from app.models.client import Client  # noqa: F401
from app.models.config_control import ConfigControl  # noqa: F401
from app.models.control_change_log import ControlChangeLog  # noqa: F401
from app.models.control_framework import ControlFramework  # noqa: F401

# Phase 4
from app.models.control_repository import ControlRepository  # noqa: F401
from app.models.control_test import ControlTest  # noqa: F401
from app.models.control_test_template import ControlTestTemplate  # noqa: F401
from app.models.engagement_team import EngagementTeam  # noqa: F401
from app.models.permission import Permission  # noqa: F401

# Phase 3
from app.models.review_cycle import ReviewCycle  # noqa: F401

# Phase 2
from app.models.role import Role  # noqa: F401
from app.models.role_permission import RolePermission  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_role import UserRole  # noqa: F401
from app.models.version import Version  # noqa: F401

# Phase 5
from app.models.evidence_file import EvidenceFile  # noqa: F401
from app.models.test_log import TestLog  # noqa: F401
# from app.models.control_test_result import ControlTestResult
from app.db.base_class import Base

from app.models.control_test_result import ControlTestResult