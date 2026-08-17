from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any


class ModelInfo(BaseModel):
    id: str
    name: str


class LoadModelRequest(BaseModel):
    model_id: str


class LoadModelResponse(BaseModel):
    active_model_id: str
    active_model_name: str


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatStreamRequest(BaseModel):
    model_id: str
    messages: List[ChatMessage]
    max_new_tokens: Optional[int] = None
    temperature: Optional[float] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class SimpleGenerateRequest(BaseModel):
    model_id: str
    sys_prompt: str = ""
    user_prompt: str
    max_new_tokens: Optional[int] = None
    temperature: Optional[float] = None


class SimpleGenerateResponse(BaseModel):
    model_id: str
    text: str


class AiLlmsModelsRequest(BaseModel):
    messages: List[ChatMessage]
    max_new_tokens: Optional[int] = None
    temperature: Optional[float] = None


class AiLlmsModelsResponse(BaseModel):
    model_id: str
    model_name: str
    text: str
