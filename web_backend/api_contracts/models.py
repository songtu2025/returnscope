from pydantic import BaseModel, Field


class ModelDefinitionRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=80)
    supported_efforts: list[str] = Field(
        default_factory=lambda: ["low", "medium", "high"],
        min_length=1,
        max_length=3,
    )
    active: bool = True


class ModelUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    supported_efforts: list[str] = Field(min_length=1, max_length=3)
    active: bool


class ModelValidateRequest(BaseModel):
    effort: str | None = None


class ConfigVersionRequest(BaseModel):
    connection_id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(default="responses-compatible", max_length=50)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=2000)
    primary_model: str = Field(min_length=1, max_length=120)
    primary_effort: str = "medium"
    cheap_model: str | None = Field(default=None, max_length=120)
    cheap_effort: str = "medium"
    secondary_model: str | None = Field(default=None, max_length=120)
    secondary_effort: str = "high"
    cheap_audit_percent: int = Field(default=5, ge=0, le=100)
    requests_per_minute: int = Field(default=60, ge=1, le=10000)
    max_workers: int = Field(default=4, ge=1, le=16)
    timeout_seconds: int = Field(default=120, ge=5, le=600)
    change_note: str = Field(min_length=1, max_length=500)
    models: list[ModelDefinitionRequest] | None = Field(
        default=None,
        max_length=50,
    )


class ModelPolicyRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=100)
    cheap_model: str | None = Field(default=None, max_length=120)
    cheap_effort: str = "low"
    primary_model: str = Field(min_length=1, max_length=120)
    primary_effort: str = "medium"
    secondary_model: str | None = Field(default=None, max_length=120)
    secondary_effort: str = "high"
    cheap_audit_percent: int = Field(default=5, ge=0, le=100)


class UserModelPreferenceRequest(ModelPolicyRequest):
    pass
