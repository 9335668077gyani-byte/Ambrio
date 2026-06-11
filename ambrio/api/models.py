# ambrio/api/models.py
from pydantic import BaseModel
from typing  import Optional


class ChatRequest(BaseModel):
    content:    str
    session_id: Optional[str] = None


class ChatToken(BaseModel):
    type: str = "token"
    data: str


class ChatDone(BaseModel):
    type:    str = "done"
    model:   str
    tokens:  int
    elapsed: float
    tool:    Optional[str] = None


class ErrorMsg(BaseModel):
    type:    str = "error"
    message: str


class HealthResponse(BaseModel):
    status:  str
    version: str
