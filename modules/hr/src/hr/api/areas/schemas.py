from pydantic import BaseModel


class CreateAreaRequest(BaseModel):
    name: str
    description: str | None = None


class UpdateAreaRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class AssignHeadRequest(BaseModel):
    head_employee_id: int
