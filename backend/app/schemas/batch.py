from pydantic import BaseModel, Field, field_validator


class BulkMarkReadRequest(BaseModel):
    notification_ids: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("notification_ids")
    @classmethod
    def validate_ids(cls, v: list[str]) -> list[str]:
        if len(v) > 1000:
            raise ValueError("Maximum 1000 notification IDs")
        return v


class BulkMarkUnreadRequest(BaseModel):
    notification_ids: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("notification_ids")
    @classmethod
    def validate_ids(cls, v: list[str]) -> list[str]:
        if len(v) > 1000:
            raise ValueError("Maximum 1000 notification IDs")
        return v


class BulkArchiveRequest(BaseModel):
    notification_ids: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("notification_ids")
    @classmethod
    def validate_ids(cls, v: list[str]) -> list[str]:
        if len(v) > 1000:
            raise ValueError("Maximum 1000 notification IDs")
        return v


class BulkDeleteRequest(BaseModel):
    notification_ids: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("notification_ids")
    @classmethod
    def validate_ids(cls, v: list[str]) -> list[str]:
        if len(v) > 1000:
            raise ValueError("Maximum 1000 notification IDs")
        return v


class BulkOperationResponse(BaseModel):
    processed: int
    failed: int
    message: str
