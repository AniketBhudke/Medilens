import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ProfileIn(BaseModel):
    name: str = ""
    phone: str = ""
    caregiver_phone: str = ""
    language: Literal["en", "hi", "mr"] = "en"
    tz: str = "Asia/Kolkata"
    t_morning: str = "08:00"
    t_afternoon: str = "14:00"
    t_evening: str = "18:00"
    t_night: str = "21:00"
    escalation_min: int = Field(10, ge=1, le=60)
    caregiver_min: int = Field(10, ge=1, le=120)

    @field_validator("t_morning", "t_afternoon", "t_evening", "t_night")
    @classmethod
    def _t(cls, v):
        if not HHMM.match(v):
            raise ValueError("time must be HH:MM")
        return v

    @field_validator("phone", "caregiver_phone")
    @classmethod
    def _p(cls, v):
        v = v.strip().replace(" ", "")
        if v and not re.match(r"^\+\d{8,15}$", v):
            raise ValueError("phone must be in international format, e.g. +919876543210")
        return v


class PlanMedicine(BaseModel):
    name: str
    strength: str = ""
    frequency_raw: str = ""
    slots: Optional[dict[str, float]] = None      # manual override: {"morning":1,"night":1}
    duration_days: Optional[int] = Field(None, ge=1, le=60)
    food_timing: str = "any"
    how_to_take: str = ""


class PlanIn(BaseModel):
    medicines: list[PlanMedicine]
    default_days: Optional[int] = Field(None, ge=1, le=60)
    replace_existing: bool = False


class PhoneIn(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _phone(cls, value):
        value = value.strip().replace(" ", "")
        if not re.match(r"^\+\d{8,15}$", value):
            raise ValueError("phone must be in international format, e.g. +919876543210")
        return value


class SignUpIn(PhoneIn):
    name: str = Field("", max_length=100)
    password: str = Field(min_length=8, max_length=128)


class PhoneCodeIn(PhoneIn):
    code: str = Field(pattern=r"^\d{6}$")


class LoginIn(PhoneIn):
    password: str = Field(min_length=1, max_length=128)


class ResetPasswordIn(PhoneCodeIn):
    new_password: str = Field(min_length=8, max_length=128)


class ResendCodeIn(PhoneIn):
    purpose: Literal["signup", "reset"]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def _content(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)

    @field_validator("messages")
    @classmethod
    def _conversation(cls, messages):
        if messages[0].role != "user" or messages[-1].role != "user":
            raise ValueError("conversation must start and end with a user message")
        if any(message.role == "user" and len(message.content) > 2000 for message in messages):
            raise ValueError("user messages must be 2000 characters or fewer")
        return messages
