from typing import Literal

from pydantic import BaseModel


class QualityIssueUpdate(BaseModel):
    issue_status: Literal["OPEN", "RESOLVED", "IGNORED"]
