"""
Tests for Gemini API client with rate limiting.
"""
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
import redis
from google.api_core import exceptions as google_exceptions

from src.core.gemini_client import (
    GeminiClient,
    TokenBucketRateLimiter,
    GeminiAPIError,
    RateLimitError,
    InvalidRequestError
)


class TestTokenBucketRateLimiter:
    """Tests for token bucket rate limiter."""

    @pytest.fixture
    def redis_mock(self):
        """Create mock Redis client."""
        mock_redis = Mock(spec=redis.Redis)
        mock_redis.hgetall.return_value = {}
        mock_redis.hset.return_value = True
        mock_redis.expire.return_value = True
        return mock_redis

    @pytest.fixture
    def rate_limiter(self, redis_mock):
        """Create rate limiter instance."""
        return TokenBucketRateLimiter(redis_mock, rate=60, bucket_capacity=60)

    def test_initialization(self, rate_limiter):
        """Test rate limiter initialization."""
        assert rate_limiter.rate == 60
        assert rate_limiter.bucket_capacity == 60
        assert rate_limiter.refill_rate == 1.0  # 60 per minute = 1 per second

    def test_acquire_token_success(self, rate_limiter, redis_mock):
        """Test successful token acquisition."""
        # Mock full bucket
        redis_mock.hgetall.return_value = {
            'tokens': '60.0',
            'last_update': str(time.time())
        }

        result = rate_limiter.acquire(annotator_id=1, tokens=1)
        assert result is True
        assert redis_mock.hset.called

    def test_acquire_token_rate_limit(self, rate_limiter, redis_mock):
        """Test rate limit when no tokens available."""
        # Mock empty bucket
        redis_mock.hgetall.return_value = {
            'tokens': '0.0',
            'last_update': str(time.time())
        }

        result = rate_limiter.acquire(annotator_id=1, tokens=1)
        assert result is False

    def test_token_refill(self, rate_limiter):
        """Test token refill over time."""
        current_tokens = 30.0
        last_update = time.time() - 10.0  # 10 seconds ago

        new_tokens = rate_limiter._refill_bucket(current_tokens, last_update)

        # Should refill ~10 tokens (1 per second)
        assert new_tokens > current_tokens
        assert new_tokens <= rate_limiter.bucket_capacity

    def test_wait_time_calculation(self, rate_limiter, redis_mock):
        """Test wait time calculation."""
        # Mock bucket with 5 tokens
        redis_mock.hgetall.return_value = {
            'tokens': '5.0',
            'last_update': str(time.time())
        }

        # Need 10 tokens - should wait ~5 seconds
        wait_time = rate_limiter.wait_time(annotator_id=1, tokens=10)
        assert wait_time >= 4.0  # Allow some tolerance
        assert wait_time <= 6.0

    def test_reset_bucket(self, rate_limiter, redis_mock):
        """Test bucket reset."""
        rate_limiter.reset(annotator_id=1)

        assert redis_mock.hset.called
        call_args = redis_mock.hset.call_args
        assert call_args[1]['mapping']['tokens'] == str(rate_limiter.bucket_capacity)


class TestGeminiClient:
    """Tests for Gemini API client."""

    @pytest.fixture
    def redis_mock(self):
        """Create mock Redis client."""
        mock_redis = Mock(spec=redis.Redis)
        mock_redis.hgetall.return_value = {}
        mock_redis.hset.return_value = True
        mock_redis.expire.return_value = True
        mock_redis.pipeline.return_value = Mock()
        return mock_redis

    @pytest.fixture
    def gemini_client(self, redis_mock):
        """Create Gemini client instance."""
        with patch('src.core.gemini_client.get_config_loader') as mock_loader:
            mock_config = Mock()
            mock_config.get_settings_config.return_value = {
                'model': {
                    'name': 'gemini-1.5-flash',
                    'temperature': 0.0,
                    'max_tokens': 2048
                }
            }
            mock_config.get_annotator_config.return_value = {
                'api_key': 'test_api_key'
            }
            mock_loader.return_value = mock_config

            client = GeminiClient(redis_mock, model_name='gemini-1.5-flash')
            return client

    def test_initialization(self, gemini_client):
        """Test Gemini client initialization."""
        assert gemini_client.model_name == 'gemini-1.5-flash'
        assert gemini_client.temperature == 0.0
        assert gemini_client.max_tokens == 2048

    def test_check_rate_limit(self, gemini_client, redis_mock):
        """Test rate limit checking."""
        # Mock full bucket
        redis_mock.hgetall.return_value = {
            'tokens': '60.0',
            'last_update': str(time.time())
        }

        result = gemini_client.check_rate_limit(annotator_id=1)
        assert result is True

    @patch('src.core.gemini_client.genai.Client')
    def test_generate_success(self, mock_genai_client, gemini_client, redis_mock):
        """Test successful response generation."""
        # Mock Gemini API response
        mock_client_instance = Mock()
        mock_chunk = Mock()
        mock_chunk.text = "Test response <<LEVEL_3>>"

        mock_client_instance.models.generate_content_stream.return_value = [mock_chunk]
        mock_genai_client.return_value = mock_client_instance

        # Mock rate limiter
        redis_mock.hgetall.return_value = {
            'tokens': '60.0',
            'last_update': str(time.time())
        }

        response = gemini_client.generate(
            prompt="Test prompt",
            annotator_id=1,
            domain="urgency"
        )

        assert response == "Test response <<LEVEL_3>>"

    @patch('src.core.gemini_client.genai.Client')
    def test_generate_rate_limit_error(self, mock_genai_client, gemini_client, redis_mock):
        """Test handling of rate limit errors."""
        # Mock rate limit exception
        mock_client_instance = Mock()
        mock_client_instance.models.generate_content_stream.side_effect = \
            google_exceptions.ResourceExhausted("Rate limit exceeded")
        mock_genai_client.return_value = mock_client_instance

        # Mock rate limiter
        redis_mock.hgetall.return_value = {
            'tokens': '60.0',
            'last_update': str(time.time())
        }

        with pytest.raises(RateLimitError):
            gemini_client.generate(
                prompt="Test prompt",
                annotator_id=1,
                domain="urgency",
                max_retries=1
            )

    @patch('src.core.gemini_client.genai.Client')
    def test_generate_invalid_argument_error(self, mock_genai_client, gemini_client, redis_mock):
        """Test handling of invalid argument errors."""
        # Mock invalid argument exception
        mock_client_instance = Mock()
        mock_client_instance.models.generate_content_stream.side_effect = \
            google_exceptions.InvalidArgument("Invalid request")
        mock_genai_client.return_value = mock_client_instance

        # Mock rate limiter
        redis_mock.hgetall.return_value = {
            'tokens': '60.0',
            'last_update': str(time.time())
        }

        with pytest.raises(InvalidRequestError):
            gemini_client.generate(
                prompt="Test prompt",
                annotator_id=1,
                domain="urgency"
            )

    def test_get_metrics(self, gemini_client, redis_mock):
        """Test metrics retrieval."""
        redis_mock.hgetall.return_value = {
            'total_requests': '100',
            'successful_requests': '95',
            'failed_requests': '5',
            'total_duration': '500.0'
        }

        metrics = gemini_client.get_metrics(annotator_id=1, domain='urgency')

        assert metrics['total_requests'] == 100
        assert metrics['successful_requests'] == 95
        assert metrics['failed_requests'] == 5
        assert metrics['avg_duration'] == pytest.approx(500.0 / 95, rel=0.01)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
