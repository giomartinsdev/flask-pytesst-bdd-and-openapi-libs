from dataclasses import dataclass
from typing import Optional


@dataclass
class CreateAreaRequest:
    name: str
    description: Optional[str] = None


@dataclass
class UpdateAreaRequest:
    name: Optional[str] = None
    description: Optional[str] = None


@dataclass
class AssignHeadRequest:
    head_employee_id: int
