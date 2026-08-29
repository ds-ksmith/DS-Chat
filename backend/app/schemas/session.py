import uuid
from datetime import datetime

from pydantic import BaseModel


class SessionRead(BaseModel):
    id: uuid.UUID
    ip_address: str | None
    # Parsed from the stored user_agent by the router (see
    # user_agent_service.describe_user_agent) -- not a stored column, so a
    # future improvement to the parser applies retroactively to old rows
    # too.
    device_label: str
    created_at: datetime
    last_seen_at: datetime
    # Whether this is the session the request making this call is itself
    # authenticated with -- lets the UI mark "this device" and treat
    # revoking it as a self-logout rather than just another row.
    is_current: bool
