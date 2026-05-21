from pydantic import BaseModel


class TextAnalysisRequest(BaseModel):
    text: str


class TranslationRequest(BaseModel):
    text: str
    target_lang: str = "en"


class WordInfo(BaseModel):
    text: str
    hsk_level: str | None = None
    level_new: str | None = None
    level_old: str | None = None
    pinyin: str | None = None
    meaning: str | None = None
    meanings: list[str] | None = None
    frequency: int | None = None
    is_hsk: bool = False
    translation_source: str | None = None
    radical: str | None = None
    radical_pinyin: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class SignupWithInviteRequest(BaseModel):
    token: str
    username: str
    password: str


class UpdateInviteQuotaRequest(BaseModel):
    invite_quota: int
