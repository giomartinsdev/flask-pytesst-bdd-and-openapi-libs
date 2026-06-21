from pydantic import BaseModel


class CreateAreaCommand(BaseModel):
    name: str
    description: str | None = None


class UpdateAreaCommand(BaseModel):
    area_id: int
    name: str | None = None
    description: str | None = None


class AssignHeadCommand(BaseModel):
    area_id: int
    head_employee_id: int


class DeleteAreaCommand(BaseModel):
    area_id: int
