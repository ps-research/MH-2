"""
Tests for annotation data models.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from src.models.annotation import (
    AnnotationRequest,
    AnnotationResult,
    MalformError,
    ProgressMetrics
)


class TestAnnotationRequest:
    """Tests for AnnotationRequest model."""

    def test_valid_request(self):
        """Test valid annotation request."""
        request = AnnotationRequest(
            annotator_id=1,
            domain='urgency',
            sample_id='TEST-001',
            text='Test text for annotation'
        )

        assert request.annotator_id == 1
        assert request.domain == 'urgency'
        assert request.sample_id == 'TEST-001'
        assert request.text == 'Test text for annotation'

    def test_invalid_annotator_id(self):
        """Test validation of annotator ID."""
        with pytest.raises(ValidationError):
            AnnotationRequest(
                annotator_id=10,  # Invalid: must be 1-5
                domain='urgency',
                sample_id='TEST-001',
                text='Test text'
            )

    def test_invalid_domain(self):
        """Test validation of domain name."""
        with pytest.raises(ValidationError):
            AnnotationRequest(
                annotator_id=1,
                domain='invalid_domain',
                sample_id='TEST-001',
                text='Test text'
            )

    def test_domain_case_insensitive(self):
        """Test domain validation is case-insensitive."""
        request = AnnotationRequest(
            annotator_id=1,
            domain='URGENCY',
            sample_id='TEST-001',
            text='Test text'
        )

        assert request.domain == 'urgency'  # Should be lowercased


class TestAnnotationResult:
    """Tests for AnnotationResult model."""

    def test_successful_result(self):
        """Test successful annotation result."""
        result = AnnotationResult(
            sample_id='TEST-001',
            status='success',
            label='LEVEL_3',
            raw_response='Analysis... <<LEVEL_3>>',
            parsing_error=None,
            validity_error=None
        )

        assert result.is_success()
        assert not result.is_malformed()
        assert not result.is_error()
        assert result.get_error_message() is None

    def test_malformed_result(self):
        """Test malformed annotation result."""
        result = AnnotationResult(
            sample_id='TEST-001',
            status='malformed',
            label=None,
            raw_response='Bad response',
            parsing_error='Could not find << >> tags',
            validity_error=None
        )

        assert not result.is_success()
        assert result.is_malformed()
        assert not result.is_error()
        assert 'Parsing:' in result.get_error_message()

    def test_error_result(self):
        """Test error annotation result."""
        result = AnnotationResult(
            sample_id='TEST-001',
            status='error',
            label=None,
            raw_response='Error occurred',
            parsing_error=None,
            validity_error='API error'
        )

        assert not result.is_success()
        assert not result.is_malformed()
        assert result.is_error()
        assert 'Validity:' in result.get_error_message()


class TestMalformError:
    """Tests for MalformError model."""

    def test_valid_malform_error(self):
        """Test valid malform error."""
        error = MalformError(
            sample_id='TEST-001',
            domain='urgency',
            annotator_id=1,
            sample_text='Test text',
            raw_response='Bad response',
            parsing_error='Parse error',
            validity_error=None,
            retry_count=0,
            task_id='task-123'
        )

        assert error.sample_id == 'TEST-001'
        assert error.domain == 'urgency'
        assert error.get_error_type() == 'parsing'

    def test_error_type_detection(self):
        """Test error type detection."""
        # Parsing error
        error1 = MalformError(
            sample_id='TEST-001',
            domain='urgency',
            annotator_id=1,
            sample_text='Text',
            raw_response='Response',
            parsing_error='Parse error',
            validity_error=None
        )
        assert error1.get_error_type() == 'parsing'

        # Validity error
        error2 = MalformError(
            sample_id='TEST-002',
            domain='urgency',
            annotator_id=1,
            sample_text='Text',
            raw_response='Response',
            parsing_error=None,
            validity_error='Validity error'
        )
        assert error2.get_error_type() == 'validity'

    def test_to_dict(self):
        """Test conversion to dictionary."""
        error = MalformError(
            sample_id='TEST-001',
            domain='urgency',
            annotator_id=1,
            sample_text='Text',
            raw_response='Response',
            parsing_error='Error'
        )

        error_dict = error.to_dict()

        assert 'sample_id' in error_dict
        assert 'timestamp' in error_dict
        assert isinstance(error_dict['timestamp'], str)


class TestProgressMetrics:
    """Tests for ProgressMetrics model."""

    def test_valid_metrics(self):
        """Test valid progress metrics."""
        metrics = ProgressMetrics(
            annotator_id=1,
            domain='urgency',
            completed=75,
            total=100,
            malformed_count=5,
            success_rate=93.3
        )

        assert metrics.get_remaining() == 25
        assert metrics.get_success_count() == 70
        assert metrics.get_completion_percentage() == 75.0

    def test_success_rate_calculation(self):
        """Test automatic success rate calculation."""
        metrics = ProgressMetrics(
            annotator_id=1,
            domain='urgency',
            completed=100,
            total=100,
            malformed_count=10,
            success_rate=None  # Should be calculated
        )

        assert metrics.success_rate == 90.0

    def test_time_remaining_estimation(self):
        """Test time remaining estimation."""
        metrics = ProgressMetrics(
            annotator_id=1,
            domain='urgency',
            completed=50,
            total=100,
            malformed_count=0,
            success_rate=100.0,
            avg_task_duration=2.0  # 2 seconds per task
        )

        # 50 remaining tasks * 2 seconds = 100 seconds
        assert metrics.estimate_time_remaining() == 100.0

    def test_validation_completed_not_exceeds_total(self):
        """Test validation that completed doesn't exceed total."""
        with pytest.raises(ValidationError):
            ProgressMetrics(
                annotator_id=1,
                domain='urgency',
                completed=150,  # Invalid: exceeds total
                total=100,
                malformed_count=0,
                success_rate=100.0
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
