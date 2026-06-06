from enum import StrEnum
from pydantic import BaseModel, Field
import uuid, time

class MsgType(StrEnum):
    CHAT_REQUEST   = 'chat.request'
    CHAT_TOKEN     = 'chat.token'
    CHAT_DONE      = 'chat.done'
    TOOL_CALL      = 'tool.call'
    TOOL_RESULT    = 'tool.result'
    SANDBOX_SUBMIT = 'sandbox.submit'
    SANDBOX_RESULT = 'sandbox.result'
    ERROR          = 'error'
    SESSION_SYNC   = 'session.sync'

class Frame(BaseModel):
    id:         str   = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    type:       MsgType
    payload:    dict
    ts:         float = Field(default_factory=time.monotonic)
