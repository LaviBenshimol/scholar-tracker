"""Pydantic models for chat API input/output validation."""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel

# -- Request Models ----------------------------------------------------------


class TextBody(BaseModel):
    body: str


class ButtonReply(BaseModel):
    id: str


class InteractivePayload(BaseModel):
    button_reply: ButtonReply


class ChatRequest(BaseModel):
    """Incoming chat message -- either text or interactive button reply."""
    type: Literal["text", "interactive"]
    text: Optional[TextBody] = None
    interactive: Optional[InteractivePayload] = None
    user_id: Optional[str] = None


# -- Response Models ---------------------------------------------------------

class TextResponse(BaseModel):
    """Simple text message."""
    type: Literal["text"] = "text"
    text: TextBody


class ImageContent(BaseModel):
    url: str
    caption: str = ""


class ImageResponse(BaseModel):
    """Image message with URL and caption."""
    type: Literal["image"] = "image"
    image: ImageContent


class ButtonDef(BaseModel):
    type: Literal["reply"] = "reply"
    reply: ButtonReply
    title: Optional[str] = None


class InteractiveAction(BaseModel):
    buttons: List[ButtonDef]


class InteractiveHeader(BaseModel):
    type: Literal["text"] = "text"
    text: str


class InteractiveBody(BaseModel):
    text: str


class InteractiveContent(BaseModel):
    type: Literal["button"] = "button"
    header: Optional[InteractiveHeader] = None
    body: InteractiveBody
    action: InteractiveAction


class InteractiveResponse(BaseModel):
    """Interactive menu with buttons."""
    type: Literal["interactive"] = "interactive"
    interactive: InteractiveContent


# Union type for all responses
ChatResponse = Union[TextResponse, ImageResponse, InteractiveResponse]
