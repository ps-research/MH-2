"""
Tests for Pydantic configuration models.
"""
import pytest
from pydantic import ValidationError
from src.core.models import (
    AnnotatorConfig,
    AnnotatorsConfig,
    ValidationConfig,
    DomainConfig,
    DomainsConfig,
    DomainWorkerConfig,
    WorkersConfig,
    RedisConfig,
    CeleryConfig,
    SettingsConfig,
    validate_config
)


class TestAnnotatorConfig:
    """Tests for AnnotatorConfig model."""

    def test_valid_config(self):
        config = AnnotatorConfig(
            name="Test Annotator",
            api_key="test_key_123",
            email="test@example.com",
            rate_limit=60,
            max_retries=3
        )
        assert config.name == "Test Annotator"
        assert config.rate_limit == 60

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            AnnotatorConfig(
                name="Test",
                api_key="key",
                email="invalid_email",
                rate_limit=60
            )

    def test_invalid_rate_limit(self):
        with pytest.raises(ValidationError):
            AnnotatorConfig(
                name="Test",
                api_key="key",
                email="test@example.com",
                rate_limit=0  # Must be > 0
            )

    def test_default_max_retries(self):
        config = AnnotatorConfig(
            name="Test",
            api_key="key",
            email="test@example.com",
            rate_limit=60
        )
        assert config.max_retries == 3


class TestAnnotatorsConfig:
    """Tests for AnnotatorsConfig model."""

    def test_valid_annotators(self):
        config = AnnotatorsConfig(
            annotators={
                1: AnnotatorConfig(
                    name="Annotator 1",
                    api_key="key1",
                    email="ann1@example.com",
                    rate_limit=60
                ),
                2: AnnotatorConfig(
                    name="Annotator 2",
                    api_key="key2",
                    email="ann2@example.com",
                    rate_limit=60
                )
            }
        )
        assert len(config.annotators) == 2

    def test_invalid_annotator_id(self):
        with pytest.raises(ValidationError, match="between 1 and 5"):
            AnnotatorsConfig(
                annotators={
                    6: AnnotatorConfig(
                        name="Invalid",
                        api_key="key",
                        email="test@example.com",
                        rate_limit=60
                    )
                }
            )


class TestValidationConfig:
    """Tests for ValidationConfig model."""

    def test_valid_validation_config(self):
        config = ValidationConfig(
            pattern=r'LEVEL[_\s]*([0-4])',
            type='single',
            valid_codes=['LEVEL_0', 'LEVEL_1']
        )
        assert config.type == 'single'

    def test_invalid_regex(self):
        with pytest.raises(ValidationError, match="Invalid regex"):
            ValidationConfig(
                pattern=r'[invalid(',  # Invalid regex
                type='single',
                valid_codes=['CODE']
            )

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            ValidationConfig(
                pattern=r'test',
                type='invalid',  # Must be 'single' or 'multi'
                valid_codes=['CODE']
            )


class TestDomainConfig:
    """Tests for DomainConfig model."""

    def test_valid_domain_config(self):
        config = DomainConfig(
            name="Urgency",
            prompt_template="Analyze this: {text}",
            validation=ValidationConfig(
                pattern=r'LEVEL_\d',
                type='single',
                valid_codes=['LEVEL_0']
            )
        )
        assert "{text}" in config.prompt_template

    def test_missing_placeholder(self):
        with pytest.raises(ValidationError, match="text.*placeholder"):
            DomainConfig(
                name="Test",
                prompt_template="No placeholder here",
                validation=ValidationConfig(
                    pattern=r'test',
                    type='single',
                    valid_codes=['CODE']
                )
            )


class TestDomainsConfig:
    """Tests for DomainsConfig model."""

    def test_valid_domains(self):
        config = DomainsConfig(
            domains={
                'urgency': DomainConfig(
                    name="Urgency",
                    prompt_template="Prompt: {text}",
                    validation=ValidationConfig(
                        pattern=r'LEVEL',
                        type='single',
                        valid_codes=['LEVEL_0']
                    )
                )
            }
        )
        assert 'urgency' in config.domains

    def test_invalid_domain_name(self):
        with pytest.raises(ValidationError, match="Invalid domain name"):
            DomainsConfig(
                domains={
                    'invalid_domain': DomainConfig(
                        name="Invalid",
                        prompt_template="Prompt: {text}",
                        validation=ValidationConfig(
                            pattern=r'test',
                            type='single',
                            valid_codes=['CODE']
                        )
                    )
                }
            )


class TestDomainWorkerConfig:
    """Tests for DomainWorkerConfig model."""

    def test_valid_worker_config(self):
        config = DomainWorkerConfig(
            enabled=True,
            concurrency=2,
            queue="annotator_1_urgency",
            sample_limit=100,
            batch_size=10
        )
        assert config.concurrency == 2

    def test_invalid_queue_format(self):
        with pytest.raises(ValidationError, match="annotator_X_domain"):
            DomainWorkerConfig(
                queue="invalid_queue_name"
            )

    def test_default_values(self):
        config = DomainWorkerConfig(
            queue="annotator_1_urgency"
        )
        assert config.enabled is True
        assert config.concurrency == 1
        assert config.batch_size == 1


class TestRedisConfig:
    """Tests for RedisConfig model."""

    def test_valid_redis_config(self):
        config = RedisConfig(
            host="localhost",
            port=6379,
            db_broker=0,
            db_backend=1
        )
        assert config.host == "localhost"

    def test_same_db_error(self):
        with pytest.raises(ValidationError, match="different"):
            RedisConfig(
                db_broker=0,
                db_backend=0  # Same as broker
            )

    def test_defaults(self):
        config = RedisConfig()
        assert config.host == "localhost"
        assert config.port == 6379


class TestCeleryConfig:
    """Tests for CeleryConfig model."""

    def test_valid_celery_config(self):
        config = CeleryConfig(
            task_time_limit=300,
            task_soft_time_limit=240
        )
        assert config.task_time_limit == 300

    def test_soft_limit_greater_than_hard(self):
        with pytest.raises(ValidationError, match="less than"):
            CeleryConfig(
                task_time_limit=200,
                task_soft_time_limit=300  # Greater than hard limit
            )


class TestValidateConfigFunction:
    """Tests for validate_config helper function."""

    def test_validate_settings(self):
        config_dict = {
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'db_broker': 0,
                'db_backend': 1
            },
            'celery': {
                'task_time_limit': 300,
                'task_soft_time_limit': 240
            },
            'logging': {
                'level': 'INFO',
                'file': 'test.log'
            }
        }
        result = validate_config('settings', config_dict)
        assert isinstance(result, SettingsConfig)

    def test_invalid_config_type(self):
        with pytest.raises(ValueError, match="Invalid config type"):
            validate_config('invalid_type', {})

    def test_validation_error(self):
        with pytest.raises(ValidationError):
            validate_config('settings', {'invalid': 'data'})
