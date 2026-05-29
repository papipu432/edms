from pydantic import BaseModel


class BreadcrumbItem(BaseModel):
    id: int
    name: str
    url: str


class BreadcrumbResponse(BaseModel):
    items: list[BreadcrumbItem]
