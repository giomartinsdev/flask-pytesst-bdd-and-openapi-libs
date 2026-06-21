from dataclasses import dataclass
from typing import Optional


@dataclass
class CreateAreaCommand:
    name: str
    description: Optional[str] = None


@dataclass
class UpdateAreaCommand:
    area_id: int
    name: Optional[str] = None
    description: Optional[str] = None


@dataclass
class AssignHeadCommand:
    area_id: int
    head_employee_id: int


@dataclass
class DeleteAreaCommand:
    area_id: int
