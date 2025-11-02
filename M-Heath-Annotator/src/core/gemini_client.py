"""
Gemini API client with rate limiting and error handling.
"""
import os
import time
import logging
from typing import Optional
from datetime import datetime
import redis

from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions

from .config_loader import get_config_loader


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# CUSTOM EXCEPTIONS
# ═══════════════════════════════════════════════════════════

class GeminiAPIError(Exception):
    """Base exception for Gemini API errors."""
    def __init__(self, message: str, should_retry: bool = False):
        super().__init__(message)
        self.should_retry = should_retry


class RateLimitError(GeminiAPIError):
    """Rate limit exceeded error."""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(message, should_retry=True)
        self.retry_after = retry_after


class InvalidRequestError(GeminiAPIError):
    """Invalid request error (no retry)."""
    def __init__(self, message: str):
        super().__init__(message, should_retry=False)


# ═══════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════

class TokenBucketRateLimiter:
    """
    Token bucket rate limiter using Redis for distributed state.

    Allows bursts up to bucket capacity while maintaining average rate.
    """

    def __init__(self, redis_client: redis.Redis, rate: int = 60, bucket_capacity: Optional[int] = None):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client instance
            rate: Requests per minute
            bucket_capacity: Maximum tokens in bucket (defaults to rate)
        """
        self.redis = redis_client
        self.rate = rate  # Requests per minute
        self.bucket_capacity = bucket_capacity or rate
        self.refill_rate = rate / 60.0  # Tokens per second

        logger.debug(f"Rate limiter initialized: {rate} req/min, capacity={self.bucket_capacity}")

    def _get_bucket_key(self, annotator_id: int) -> str:
        """Get Redis key for rate limit bucket."""
        return f"ratelimit:{annotator_id}"

    def _get_bucket_state(self, annotator_id: int) -> tuple[float, float]:
        """
        Get current bucket state from Redis.

        Returns:
            Tuple of (tokens, last_update_timestamp)
        """
        key = self._get_bucket_key(annotator_id)
        data = self.redis.hgetall(key)

        if not data:
            # Initialize bucket
            now = time.time()
            self.redis.hset(key, mapping={
                'tokens': str(self.bucket_capacity),
                'last_update': str(now)
            })
            self.redis.expire(key, 3600)  # Expire after 1 hour of inactivity
            return (self.bucket_capacity, now)

        tokens = float(data.get('tokens', self.bucket_capacity))
        last_update = float(data.get('last_update', time.time()))

        return (tokens, last_update)

    def _update_bucket_state(self, annotator_id: int, tokens: float, timestamp: float) -> None:
        """Update bucket state in Redis."""
        key = self._get_bucket_key(annotator_id)
        self.redis.hset(key, mapping={
            'tokens': str(tokens),
            'last_update': str(timestamp)
        })
        self.redis.expire(key, 3600)

    def _refill_bucket(self, current_tokens: float, last_update: float) -> float:
        """
        Calculate refilled tokens based on time passed.

        Args:
            current_tokens: Current token count
            last_update: Last update timestamp

        Returns:
            New token count after refill
        """
        now = time.time()
        time_passed = now - last_update

        # Calculate tokens to add based on refill rate
        tokens_to_add = time_passed * self.refill_rate
        new_tokens = min(self.bucket_capacity, current_tokens + tokens_to_add)

        logger.debug(f"Refilled bucket: {current_tokens:.2f} -> {new_tokens:.2f} (+{tokens_to_add:.2f})")

        return new_tokens

    def acquire(self, annotator_id: int, tokens: int = 1) -> bool:
        """
        Try to acquire tokens from bucket.

        Args:
            annotator_id: Annotator ID
            tokens: Number of tokens to acquire

        Returns:
            True if tokens acquired, False if rate limit hit
        """
        # Get current state
        current_tokens, last_update = self._get_bucket_state(annotator_id)

        # Refill bucket based on time passed
        now = time.time()
        current_tokens = self._refill_bucket(current_tokens, last_update)

        # Check if enough tokens available
        if current_tokens >= tokens:
            # Consume tokens
            new_tokens = current_tokens - tokens
            self._update_bucket_state(annotator_id, new_tokens, now)
            logger.debug(f"Acquired {tokens} token(s) for annotator {annotator_id}. Remaining: {new_tokens:.2f}")
            return True
        else:
            # Not enough tokens
            logger.warning(f"Rate limit hit for annotator {annotator_id}. Available: {current_tokens:.2f}, needed: {tokens}")
            return False

    def wait_time(self, annotator_id: int, tokens: int = 1) -> float:
        """
        Calculate wait time until tokens available.

        Args:
            annotator_id: Annotator ID
            tokens: Number of tokens needed

        Returns:
            Wait time in seconds
        """
        current_tokens, last_update = self._get_bucket_state(annotator_id)
        current_tokens = self._refill_bucket(current_tokens, last_update)

        if current_tokens >= tokens:
            return 0.0

        # Calculate time needed to refill required tokens
        tokens_needed = tokens - current_tokens
        wait_seconds = tokens_needed / self.refill_rate

        return wait_seconds

    def reset(self, annotator_id: int) -> None:
        """Reset bucket to full capacity."""
        key = self._get_bucket_key(annotator_id)
        self.redis.hset(key, mapping={
            'tokens': str(self.bucket_capacity),
            'last_update': str(time.time())
        })
        logger.info(f"Reset rate limit bucket for annotator {annotator_id}")


# ═══════════════════════════════════════════════════════════
# GEMINI CLIENT
# ═══════════════════════════════════════════════════════════

class GeminiClient:
    """
    Gemini API client with rate limiting and error handling.

    Features:
    - Token bucket rate limiting per annotator
    - Automatic retry on rate limits with exponential backoff
    - Error classification (retriable vs non-retriable)
    - Request/response logging
    """

    def __init__(self, redis_client: redis.Redis, model_name: Optional[str] = None):
        """
        Initialize Gemini client.

        Args:
            redis_client: Redis client for rate limiting
            model_name: Model name (defaults to value from settings.yaml)
        """
        self.redis = redis_client

        # Load configuration
        config_loader = get_config_loader()
        settings = config_loader.get_settings_config()

        self.model_name = model_name or settings['model']['name']
        self.temperature = settings['model'].get('temperature', 0.0)
        self.max_tokens = settings['model'].get('max_tokens', 2048)

        # Initialize Gemini client
        # Note: API key will be loaded per annotator
        self.clients = {}  # Cache of annotator_id -> genai.Client

        # Initialize rate limiter (60 req/min per annotator)
        self.rate_limiter = TokenBucketRateLimiter(
            redis_client=redis_client,
            rate=60,  # 60 requests per minute
            bucket_capacity=60
        )

        logger.info(f"GeminiClient initialized with model: {self.model_name}")

    def _get_client(self, annotator_id: int) -> genai.Client:
        """
        Get or create Gemini client for annotator.

        Args:
            annotator_id: Annotator ID

        Returns:
            Gemini client instance
        """
        if annotator_id not in self.clients:
            # Load API key from configuration
            config_loader = get_config_loader()
            annotator_config = config_loader.get_annotator_config(annotator_id)
            api_key = annotator_config['api_key']

            # Create client
            self.clients[annotator_id] = genai.Client(api_key=api_key)
            logger.debug(f"Created Gemini client for annotator {annotator_id}")

        return self.clients[annotator_id]

    def check_rate_limit(self, annotator_id: int) -> bool:
        """
        Check if rate limit allows request.

        Args:
            annotator_id: Annotator ID

        Returns:
            True if request can proceed, False if rate limited
        """
        return self.rate_limiter.acquire(annotator_id, tokens=1)

    def wait_for_rate_limit(self, annotator_id: int) -> None:
        """
        Wait until rate limit allows request.

        Args:
            annotator_id: Annotator ID
        """
        wait_time = self.rate_limiter.wait_time(annotator_id, tokens=1)

        if wait_time > 0:
            logger.info(f"Rate limit: waiting {wait_time:.2f}s for annotator {annotator_id}")
            time.sleep(wait_time)

            # Acquire token after waiting
            if not self.rate_limiter.acquire(annotator_id, tokens=1):
                # Should not happen, but wait a bit more just in case
                time.sleep(1.0)

    def generate(
        self,
        prompt: str,
        annotator_id: int,
        domain: str,
        max_retries: int = 3,
        base_delay: float = 2.0
    ) -> str:
        """
        Generate response from Gemini API with rate limiting and retry.

        Args:
            prompt: Prompt text
            annotator_id: Annotator ID
            domain: Domain name
            max_retries: Maximum number of retries
            base_delay: Base delay for exponential backoff

        Returns:
            Generated response text

        Raises:
            GeminiAPIError: On API errors
            RateLimitError: On rate limit (after retries)
            InvalidRequestError: On invalid request
        """
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                # Check rate limit before making request
                if not self.check_rate_limit(annotator_id):
                    self.wait_for_rate_limit(annotator_id)

                # Get client for this annotator
                client = self._get_client(annotator_id)

                # Prepare request
                contents = [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)]
                    )
                ]

                # Configure generation
                config = types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    safety_settings=[
                        types.SafetySetting(
                            category='HARM_CATEGORY_HATE_SPEECH',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_DANGEROUS_CONTENT',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_HARASSMENT',
                            threshold='BLOCK_NONE'
                        ),
                        types.SafetySetting(
                            category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                            threshold='BLOCK_NONE'
                        )
                    ]
                )

                # Generate response
                logger.debug(f"Generating response for annotator {annotator_id}, domain {domain}")
                start_time = time.time()

                response_text = ""
                for chunk in client.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config=config
                ):
                    if chunk.text:
                        response_text += chunk.text

                duration = time.time() - start_time
                logger.info(f"Generated response in {duration:.2f}s (length: {len(response_text)})")

                # Track request metrics in Redis
                self._track_request_metrics(annotator_id, domain, duration, success=True)

                return response_text

            except google_exceptions.ResourceExhausted as e:
                # Rate limit error - retry with exponential backoff
                retry_count += 1
                delay = base_delay * (2 ** (retry_count - 1))

                logger.warning(f"Rate limit hit: {e}. Retry {retry_count}/{max_retries} in {delay}s")

                if retry_count > max_retries:
                    last_error = RateLimitError(str(e), retry_after=int(delay))
                    break

                time.sleep(delay)

            except google_exceptions.InvalidArgument as e:
                # Invalid request - no retry
                logger.error(f"Invalid request: {e}")
                self._track_request_metrics(annotator_id, domain, 0, success=False)
                raise InvalidRequestError(str(e))

            except Exception as e:
                # Other errors - retry
                retry_count += 1
                delay = base_delay * (2 ** (retry_count - 1))

                logger.error(f"API error: {e}. Retry {retry_count}/{max_retries} in {delay}s")

                if retry_count > max_retries:
                    last_error = GeminiAPIError(str(e), should_retry=True)
                    break

                time.sleep(delay)

        # All retries exhausted
        self._track_request_metrics(annotator_id, domain, 0, success=False)

        if last_error:
            raise last_error
        else:
            raise GeminiAPIError("Unknown error after all retries")

    def _track_request_metrics(self, annotator_id: int, domain: str, duration: float, success: bool) -> None:
        """Track request metrics in Redis."""
        key = f"metrics:{annotator_id}:{domain}"

        pipe = self.redis.pipeline()
        pipe.hincrby(key, 'total_requests', 1)

        if success:
            pipe.hincrby(key, 'successful_requests', 1)
            pipe.hincrbyfloat(key, 'total_duration', duration)
        else:
            pipe.hincrby(key, 'failed_requests', 1)

        pipe.hset(key, 'last_request_time', datetime.now().isoformat())
        pipe.expire(key, 86400)  # 24 hours

        pipe.execute()

    def get_metrics(self, annotator_id: int, domain: str) -> dict:
        """
        Get request metrics for annotator-domain pair.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Dictionary with metrics
        """
        key = f"metrics:{annotator_id}:{domain}"
        data = self.redis.hgetall(key)

        if not data:
            return {
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'total_duration': 0.0,
                'avg_duration': 0.0
            }

        total_requests = int(data.get('total_requests', 0))
        successful_requests = int(data.get('successful_requests', 0))
        failed_requests = int(data.get('failed_requests', 0))
        total_duration = float(data.get('total_duration', 0.0))

        avg_duration = total_duration / successful_requests if successful_requests > 0 else 0.0

        return {
            'total_requests': total_requests,
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'total_duration': total_duration,
            'avg_duration': avg_duration,
            'last_request_time': data.get('last_request_time')
        }

    def reset_rate_limit(self, annotator_id: int) -> None:
        """Reset rate limit for annotator."""
        self.rate_limiter.reset(annotator_id)
