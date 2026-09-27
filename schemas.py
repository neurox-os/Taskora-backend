from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
from typing import Literal, Any

class New_User(BaseModel):
  username : str      = Field(..., min_length=6, max_length=32, description="Username")
  email    : EmailStr = Field(..., description="Email Address")
  password : str      = Field(..., min_length=8, description="Password")

class Token(BaseModel):
  access_token : str
  token_type   : str
  
class Login_User(BaseModel):
  email : EmailStr = Field(..., description="Email Address")
  password : str   = Field(..., min_length=8, description="Password")

class NewTask(BaseModel):
  description : str = Field(..., description="Task")


class UpdateTask(BaseModel):
  description : str = Field(..., description="Task")

class ChatRequest(BaseModel): 
    model_config = ConfigDict(extra="forbid") 
    message: str

class Task_Response(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    # Removed default="..." to force these to be required in the JSON schema
    title: str = Field(
        description="Short title of the task"
    )
    
    description: str = Field(
        description="Clear, detailed description of what needs to be done."
    )
    
    priority: Literal["high", "medium", "low"] = Field(
        description="set priority based on (high, medium, low)."
    )
    
    due: str = Field(
        description="Due date and time in the format DD-MM-YYYY HH:MM. Use 'No Due Date' if no due date or time is provided."
    )

    # 1. Catch empty descriptions (e.g., "") and replace them
    @field_validator("description", mode="before")
    @classmethod
    def ensure_description(cls, value: Any) -> str:
        if not value or not str(value).strip():
            return "No description provided."
        return str(value)

    # 2. Fix priority hallucinations
    @field_validator("priority", mode="before")
    @classmethod
    def fix_priority_hallucinations(cls, value: Any) -> str:
        if isinstance(value, str):
            val_lower = value.lower()
            if val_lower in ["high", "medium", "low"]:
                return val_lower
            if val_lower in ["urgent", "critical"]:
                return "high"
        return "medium"
      
class AIAssistantResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal[
        "chat",
        "summarize",
        "create_task",
        "update_task",
        "delete_task",
        "complete_task",
        "suggest_tasks",
        "out_of_scope"
    ]

    message: str
    
    # FIX: Add defaults so the server never crashes if the AI forgets these fields
    task_id: int | None = Field(default=None)
    requires_confirmation: bool = Field(default=False)
    tasks: list[Task_Response] = Field(default_factory=list)
class ChatRequest(BaseModel): 
    model_config = ConfigDict(extra="forbid") 
    message: str