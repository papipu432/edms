from pydantic import BaseModel


class CommandPaletteResult(BaseModel):
    type: str
    id: int
    title: str
    url: str
    description: str | None = None


class CommandPaletteResponse(BaseModel):
    results: list[CommandPaletteResult]
