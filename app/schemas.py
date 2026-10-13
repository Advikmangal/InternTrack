from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Status = Literal['Saved', 'Applied', 'Assessment', 'Interview', 'Offer', 'Rejected', 'Withdrawn']
Mode = Literal['Remote', 'Hybrid', 'On-site']


def valid_zone(value):
    value = value.strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        # On Windows a region-only key such as "Asia" can resolve to a
        # tzdata directory and raise PermissionError instead of not-found.
        raise ValueError('Enter a full time zone, such as Asia/Kolkata, Europe/London, or America/New_York') from None
    return value


class Register(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Name cannot be blank')
        return value.strip()


class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class Preferences(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    timezone: str
    _zone = field_validator('timezone')(valid_zone)


class ApplicationIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    company: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=160)
    job_url: str = Field(default='', max_length=2000)
    location: str = Field(default='', max_length=160)
    work_mode: Mode = 'Remote'
    salary: str = Field(default='', max_length=160)
    status: Status = 'Saved'
    application_date: date | None = None
    deadline: date | None = None
    recruiter_name: str = Field(default='', max_length=100)
    recruiter_email: str = Field(default='', max_length=254)
    notes: str = Field(default='', max_length=20000)
    resume_id: int | None = None

    @field_validator('job_url')
    @classmethod
    def valid_url(cls, v):
        from urllib.parse import urlparse
        if v and (urlparse(v).scheme not in ('https', 'http') or not urlparse(v).hostname):
            raise ValueError('Job URL must be an http or https URL')
        return v

    @field_validator('recruiter_email')
    @classmethod
    def email(cls, v):
        if v:
            from pydantic import TypeAdapter
            return str(TypeAdapter(EmailStr).validate_python(v))
        return v

    @model_validator(mode='after')
    def submitted_date(self):
        if self.status != 'Saved' and not self.application_date:
            raise ValueError('Application date is required unless status is Saved')
        return self


class ResumeAttachmentIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resume_id: int | None = Field(..., gt=0)


class StatusIn(BaseModel):
    status: Status
    application_date: date | None = None


class InterviewIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    type: Literal['Online', 'Phone', 'In-person'] = 'Online'
    starts_at: datetime
    timezone: str
    venue: str = Field(default='', max_length=2000)
    notes: str = Field(default='', max_length=20000)
    outcome: str = Field(default='', max_length=20000)
    _zone = field_validator('timezone')(valid_zone)

    @field_validator('starts_at')
    @classmethod
    def aware(cls, v):
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError('Interview date must include a timezone offset')
        return v


class FollowUpIn(BaseModel):
    due_date: date


class CompleteFollowUp(BaseModel):
    next_date: date | None = None


class CSVIn(BaseModel):
    text: str = Field(max_length=1000000)
