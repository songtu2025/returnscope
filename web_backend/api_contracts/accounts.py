from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class InvitationCreateRequest(BaseModel):
    email: str = Field(max_length=254)


class AuthTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class RegisterRequest(AuthTokenRequest):
    display_name: str = Field(min_length=1, max_length=60)
    password: str = Field(max_length=200)


class PasswordResetRequest(BaseModel):
    email: str = Field(max_length=254)


class PasswordResetCompleteRequest(AuthTokenRequest):
    new_password: str = Field(max_length=200)


class EmailChangeRequest(BaseModel):
    current_password: str = Field(max_length=200)
    new_email: str = Field(max_length=254)


class UserCreateRequest(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=10, max_length=200)


class UserStatusRequest(BaseModel):
    active: bool
    expected_active: bool
    note: str = Field(min_length=1, max_length=500)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)
