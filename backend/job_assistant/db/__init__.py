from __future__ import annotations

# Re-export everything from all sub-modules for backward compatibility.
# Each sub-module defines __all__ that includes both public and private names.

from job_assistant.db.core import *  # noqa: F401, F403
from job_assistant.db.users import *  # noqa: F401, F403
from job_assistant.db.profiles import *  # noqa: F401, F403
from job_assistant.db.jobs import *  # noqa: F401, F403
from job_assistant.db.agent import *  # noqa: F401, F403
from job_assistant.db.integrations import *  # noqa: F401, F403
from job_assistant.db.automation import *  # noqa: F401, F403
from job_assistant.db.enterprise import *  # noqa: F401, F403
from job_assistant.db.feedback import *  # noqa: F401, F403
from job_assistant.db.admin import *  # noqa: F401, F403
from job_assistant.db.publishing import *  # noqa: F401, F403
from job_assistant.db.compliance import *  # noqa: F401, F403
from job_assistant.db.seeding import *  # noqa: F401, F403
from job_assistant.db.company_research import *  # noqa: F401, F403
