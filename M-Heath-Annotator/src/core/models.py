"""
Pydantic models for configuration validation.
"""
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, validator
import re


# ═══════════════════════════════════════════════════════════
# ANNOTATOR CONFIGURATION MODELS
# ═══════════════════════════════════════════════════════════

class AnnotatorConfig(BaseModel):
    """Configuration for a single annotator."""
    name: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    rate_limit: int = Field(..., gt=0, description="Requests per minute")
    max_retries: int = Field(default=3, ge=0, le=10)

    class Config:
        extra = 'forbid'


class AnnotatorsConfig(BaseModel):
    """Configuration for all annotators."""
    annotators: Dict[int, AnnotatorConfig]

    @validator('annotators')
    def validate_annotator_ids(cls, v):
        """Ensure annotator IDs are in valid range."""
        for annotator_id in v.keys():
            if annotator_id < 1 or annotator_id > 5:
                raise ValueError(f"Annotator ID must be between 1 and 5, got {annotator_id}")
        return v

    class Config:
        extra = 'forbid'


# ═══════════════════════════════════════════════════════════
# DOMAIN CONFIGURATION MODELS
# ═══════════════════════════════════════════════════════════

class ValidationConfig(BaseModel):
    """Validation rules for domain responses."""
    pattern: str = Field(..., description="Regex pattern for extraction")
    type: Literal['single', 'multi'] = Field(..., description="Single or multi-label")
    valid_codes: List[str] = Field(..., min_items=1)

    @validator('pattern')
    def validate_regex_pattern(cls, v):
        """Ensure pattern is a valid regex."""
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        return v

    class Config:
        extra = 'forbid'


class DomainConfig(BaseModel):
    """Configuration for a single domain."""
    name: str = Field(..., min_length=1)
    prompt_template: str = Field(..., min_length=1)
    validation: ValidationConfig

    @validator('prompt_template')
    def validate_prompt_has_placeholder(cls, v):
        """Ensure prompt template has {text} placeholder."""
        if '{text}' not in v:
            raise ValueError("Prompt template must contain {text} placeholder")
        return v

    class Config:
        extra = 'forbid'


class DomainsConfig(BaseModel):
    """Configuration for all domains."""
    domains: Dict[str, DomainConfig]

    @validator('domains')
    def validate_domain_names(cls, v):
        """Ensure domain names are valid."""
        valid_domains = {'urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal'}
        for domain_name in v.keys():
            if domain_name not in valid_domains:
                raise ValueError(f"Invalid domain name: {domain_name}. Must be one of {valid_domains}")
        return v

    class Config:
        extra = 'forbid'


# ═══════════════════════════════════════════════════════════
# WORKER CONFIGURATION MODELS
# ═══════════════════════════════════════════════════════════

class DomainWorkerConfig(BaseModel):
    """Configuration for a worker processing a specific domain."""
    enabled: bool = Field(default=True)
    concurrency: int = Field(default=1, ge=1, le=10)
    queue: str = Field(..., min_length=1)
    sample_limit: Optional[int] = Field(default=None, ge=1)
    batch_size: int = Field(default=1, ge=1, le=100)

    @validator('queue')
    def validate_queue_format(cls, v):
        """Ensure queue name follows pattern: annotator_X_domain."""
        if not re.match(r'^annotator_\d+_\w+$', v):
            raise ValueError(f"Queue name must follow pattern 'annotator_X_domain', got: {v}")
        return v

    class Config:
        extra = 'forbid'


class AnnotatorWorkerConfig(BaseModel):
    """Configuration for all workers for a single annotator."""
    domains: Dict[str, DomainWorkerConfig]

    class Config:
        extra = 'forbid'


class WorkersConfig(BaseModel):
    """Configuration for all worker pools."""
    worker_pools: Dict[str, AnnotatorWorkerConfig]

    @validator('worker_pools')
    def validate_worker_pool_names(cls, v):
        """Ensure worker pool names follow pattern: annotator_X."""
        for pool_name in v.keys():
            if not re.match(r'^annotator_\d+$', pool_name):
                raise ValueError(f"Worker pool name must follow pattern 'annotator_X', got: {pool_name}")
        return v

    class Config:
        extra = 'forbid'


# ═══════════════════════════════════════════════════════════
# SETTINGS CONFIGURATION MODELS
# ═══════════════════════════════════════════════════════════

class RedisConfig(BaseModel):
    """Redis connection configuration."""
    host: str = Field(default='localhost')
    port: int = Field(default=6379, ge=1, le=65535)
    db_broker: int = Field(default=0, ge=0, le=15)
    db_backend: int = Field(default=1, ge=0, le=15)
    password: Optional[str] = None

    @validator('db_backend')
    def validate_different_dbs(cls, v, values):
        """Ensure broker and backend use different DBs."""
        if 'db_broker' in values and v == values['db_broker']:
            raise ValueError("db_broker and db_backend must be different")
        return v

    class Config:
        extra = 'forbid'


class CeleryConfig(BaseModel):
    """Celery task configuration."""
    task_time_limit: int = Field(default=300, ge=60, le=3600)
    task_soft_time_limit: int = Field(default=240, ge=30, le=3600)
    worker_prefetch_multiplier: int = Field(default=1, ge=1, le=10)
    task_acks_late: bool = Field(default=True)
    task_reject_on_worker_lost: bool = Field(default=True)

    @validator('task_soft_time_limit')
    def validate_soft_limit_less_than_hard(cls, v, values):
        """Ensure soft time limit is less than hard limit."""
        if 'task_time_limit' in values and v >= values['task_time_limit']:
            raise ValueError("task_soft_time_limit must be less than task_time_limit")
        return v

    class Config:
        extra = 'forbid'


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = Field(default='INFO')
    file: Optional[str] = Field(default='logs/annotator.log')
    format: str = Field(default='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    max_bytes: int = Field(default=10485760, ge=1024)  # 10MB default
    backup_count: int = Field(default=5, ge=1, le=100)

    class Config:
        extra = 'forbid'


class SettingsConfig(BaseModel):
    """Application settings configuration."""
    redis: RedisConfig
    celery: CeleryConfig
    logging: LoggingConfig

    class Config:
        extra = 'forbid'


# ═══════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def validate_config(config_type: str, config_dict: dict) -> BaseModel:
    """
    Validate configuration dictionary against appropriate model.

    Args:
        config_type: Type of config ('annotators', 'domains', 'workers', 'settings')
        config_dict: Configuration dictionary to validate

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If config_type is invalid
        ValidationError: If config_dict doesn't match schema
    """
    models_map = {
        'annotators': AnnotatorsConfig,
        'domains': DomainsConfig,
        'workers': WorkersConfig,
        'settings': SettingsConfig
    }

    if config_type not in models_map:
        raise ValueError(f"Invalid config type: {config_type}. Must be one of {list(models_map.keys())}")

    model_class = models_map[config_type]
    return model_class(**config_dict)
