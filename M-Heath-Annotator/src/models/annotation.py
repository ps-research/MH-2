"""
Pydantic models for annotation requests, results, and metrics.
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, validator, model_validator


class AnnotationRequest(BaseModel):
    """Request to annotate a single sample."""
    annotator_id: int = Field(..., ge=1, le=5, description="Annotator ID (1-5)")
    domain: str = Field(..., description="Domain name")
    sample_id: str = Field(..., min_length=1, description="Unique sample identifier")
    text: str = Field(..., min_length=1, description="Text to annotate")

    @validator('domain')
    def validate_domain(cls, v):
        """Ensure domain is valid."""
        valid_domains = {'urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal'}
        if v.lower() not in valid_domains:
            raise ValueError(f"Invalid domain: {v}. Must be one of {valid_domains}")
        return v.lower()

    class Config:
        extra = 'forbid'


class AnnotationResult(BaseModel):
    """Result of annotation task."""
    sample_id: str = Field(..., description="Sample identifier")
    status: Literal["success", "malformed", "error"] = Field(..., description="Annotation status")
    label: Optional[str] = Field(None, description="Extracted label")
    raw_response: str = Field(..., description="Raw AI response")
    parsing_error: Optional[str] = Field(None, description="Error parsing response")
    validity_error: Optional[str] = Field(None, description="Error validating label")
    timestamp: datetime = Field(default_factory=datetime.now, description="Completion timestamp")

    def is_success(self) -> bool:
        """Check if annotation was successful."""
        return self.status == "success" and self.label is not None

    def is_malformed(self) -> bool:
        """Check if response was malformed."""
        return self.status == "malformed"

    def is_error(self) -> bool:
        """Check if task had an error."""
        return self.status == "error"

    def get_error_message(self) -> Optional[str]:
        """Get combined error message."""
        if self.parsing_error:
            return f"Parsing: {self.parsing_error}"
        if self.validity_error:
            return f"Validity: {self.validity_error}"
        return None

    class Config:
        extra = 'forbid'


class MalformError(BaseModel):
    """Malformed response error details."""
    sample_id: str = Field(..., description="Sample identifier")
    domain: str = Field(..., description="Domain name")
    annotator_id: int = Field(..., ge=1, le=5, description="Annotator ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")
    sample_text: str = Field(..., description="Original sample text")
    raw_response: str = Field(..., description="Raw AI response")
    parsing_error: Optional[str] = Field(None, description="Parsing error message")
    validity_error: Optional[str] = Field(None, description="Validity error message")
    retry_count: int = Field(default=0, ge=0, description="Number of retries attempted")
    task_id: Optional[str] = Field(None, description="Celery task ID")

    def get_error_type(self) -> str:
        """Get primary error type."""
        if self.parsing_error:
            return "parsing"
        elif self.validity_error:
            return "validity"
        else:
            return "unknown"

    def to_dict(self) -> dict:
        """Convert to dictionary with ISO timestamps."""
        data = self.dict()
        data['timestamp'] = self.timestamp.isoformat()
        return data

    class Config:
        extra = 'forbid'


class ProgressMetrics(BaseModel):
    """Progress metrics for annotator-domain pair."""
    annotator_id: int = Field(..., ge=1, le=5, description="Annotator ID")
    domain: str = Field(..., description="Domain name")
    completed: int = Field(..., ge=0, description="Number of completed samples")
    total: int = Field(..., ge=0, description="Total number of samples")
    malformed_count: int = Field(default=0, ge=0, description="Number of malformed responses")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Success rate percentage")
    avg_task_duration: float = Field(default=0.0, ge=0.0, description="Average task duration in seconds")
    last_updated: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    @model_validator(mode='after')
    def validate_completed_total_relationship(self):
        """Ensure completed doesn't exceed total."""
        if self.completed > self.total:
            raise ValueError(f"Completed ({self.completed}) cannot exceed total ({self.total})")
        return self

    @validator('success_rate', pre=True, always=True)
    def calculate_success_rate(cls, v, values):
        """Calculate success rate if not provided."""
        if v is None and 'completed' in values and 'total' in values and 'malformed_count' in values:
            completed = values['completed']
            malformed = values.get('malformed_count', 0)
            if completed > 0:
                return ((completed - malformed) / completed) * 100
            return 0.0
        return v

    def get_remaining(self) -> int:
        """Get number of remaining samples."""
        return max(0, self.total - self.completed)

    def get_success_count(self) -> int:
        """Get number of successful annotations."""
        return max(0, self.completed - self.malformed_count)

    def get_completion_percentage(self) -> float:
        """Get completion percentage."""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    def estimate_time_remaining(self) -> float:
        """Estimate time remaining in seconds."""
        if self.avg_task_duration == 0:
            return 0.0
        return self.get_remaining() * self.avg_task_duration

    class Config:
        extra = 'forbid'


# ═══════════════════════════════════════════════════════════
# ADDITIONAL HELPER MODELS
# ═══════════════════════════════════════════════════════════

class TaskQueueMetadata(BaseModel):
    """Metadata about queued tasks for a worker."""
    annotator_id: int = Field(..., ge=1, le=5)
    domain: str
    total_queued: int = Field(..., ge=0)
    queued_at: datetime = Field(default_factory=datetime.now)
    estimated_completion_time: Optional[datetime] = None

    class Config:
        extra = 'forbid'


class AnnotationBatch(BaseModel):
    """Batch of annotation requests."""
    requests: list[AnnotationRequest] = Field(..., min_items=1)
    batch_id: str = Field(..., description="Unique batch identifier")
    priority: int = Field(default=0, description="Batch priority (higher = more urgent)")

    def get_sample_ids(self) -> list[str]:
        """Get list of sample IDs in batch."""
        return [req.sample_id for req in self.requests]

    def get_size(self) -> int:
        """Get batch size."""
        return len(self.requests)

    class Config:
        extra = 'forbid'
