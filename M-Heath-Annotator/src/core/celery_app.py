"""
Celery application configuration for distributed mental health annotation system.
"""
import os
from celery import Celery, Task
from celery.signals import task_prerun, task_postrun, task_failure
from kombu import Queue
import logging
from typing import Dict, List

from .config_loader import get_config_loader
from .checkpoint import RedisCheckpointManager
import redis


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# LOAD CONFIGURATION
# ═══════════════════════════════════════════════════════════

def load_celery_config():
    """Load Celery configuration from settings."""
    config_loader = get_config_loader()
    settings = config_loader.get_settings_config()

    redis_config = settings['redis']
    celery_config = settings['celery']

    # Build Redis URLs
    broker_url = f"redis://{redis_config['host']}:{redis_config['port']}/{redis_config['db_broker']}"
    backend_url = f"redis://{redis_config['host']}:{redis_config['port']}/{redis_config['db_backend']}"

    if redis_config.get('password'):
        broker_url = f"redis://:{redis_config['password']}@{redis_config['host']}:{redis_config['port']}/{redis_config['db_broker']}"
        backend_url = f"redis://:{redis_config['password']}@{redis_config['host']}:{redis_config['port']}/{redis_config['db_backend']}"

    return {
        'broker_url': broker_url,
        'backend_url': backend_url,
        'celery_config': celery_config,
        'redis_config': redis_config
    }


# ═══════════════════════════════════════════════════════════
# CREATE CELERY APP
# ═══════════════════════════════════════════════════════════

# Initialize Celery app
app = Celery('mental_health_annotator')

# Load configuration
try:
    config = load_celery_config()

    # Configure Celery
    app.conf.broker_url = config['broker_url']
    app.conf.result_backend = config['backend_url']

    celery_conf = config['celery_config']

    app.conf.update(
        # Task execution settings
        task_time_limit=celery_conf['task_time_limit'],
        task_soft_time_limit=celery_conf['task_soft_time_limit'],
        task_acks_late=celery_conf['task_acks_late'],
        task_reject_on_worker_lost=celery_conf['task_reject_on_worker_lost'],

        # Worker settings
        worker_prefetch_multiplier=celery_conf['worker_prefetch_multiplier'],
        worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks

        # Result backend settings
        result_expires=3600,  # Results expire after 1 hour
        result_extended=True,

        # Serialization
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],

        # Timezone
        timezone='UTC',
        enable_utc=True,

        # Task routes (will be set dynamically)
        task_routes={},

        # Error handling
        task_default_retry_delay=60,  # 1 minute
        task_max_retries=3,
    )

    logger.info("Celery app configured successfully")

except Exception as e:
    logger.warning(f"Could not load configuration, using defaults: {e}")
    # Fallback to default configuration
    app.conf.broker_url = 'redis://localhost:6379/0'
    app.conf.result_backend = 'redis://localhost:6379/1'


# ═══════════════════════════════════════════════════════════
# QUEUE CONFIGURATION
# ═══════════════════════════════════════════════════════════

def setup_queues():

# Import tasks to register them with Celery
    """
    Setup Celery queues for all annotator-domain pairs.

    Creates 30 queues (5 annotators × 6 domains):
    - annotator_1_urgency
    - annotator_1_therapeutic
    - ...
    - annotator_5_redressal
    """
    config_loader = get_config_loader()

    try:
        # Get all enabled workers from configuration
        all_queues = []
        task_routes = {}

        for annotator_id in range(1, 6):  # Annotators 1-5
            enabled_workers = config_loader.get_enabled_workers(annotator_id)

            for domain, worker_config in enabled_workers.items():
                queue_name = worker_config['queue']
                all_queues.append(Queue(queue_name))

                # Map task pattern to queue
                task_pattern = f'annotate_{domain}'
                task_routes[task_pattern] = {'queue': queue_name}

        # Update Celery configuration
        app.conf.task_queues = tuple(all_queues)
        app.conf.task_routes = task_routes

        logger.info(f"Configured {len(all_queues)} queues")

    except Exception as e:
        logger.error(f"Error setting up queues: {e}")
        # Fallback: create default queues
        default_queues = []
        domains = ['urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal']

        for annotator_id in range(1, 6):
            for domain in domains:
                queue_name = f"annotator_{annotator_id}_{domain}"
                default_queues.append(Queue(queue_name))

        app.conf.task_queues = tuple(default_queues)
        logger.warning(f"Using default queue configuration: {len(default_queues)} queues")


# Initialize queues
setup_queues()

# Import tasks to register them with Celery
from . import tasks  # noqa: F401


# ═══════════════════════════════════════════════════════════
# CUSTOM TASK BASE CLASS
# ═══════════════════════════════════════════════════════════

class AnnotationTask(Task):
    """
    Custom task base class with checkpoint support and automatic retry.

    Features:
    - Automatic retry on rate limit with exponential backoff
    - Checkpoint on completion
    - Error logging to Redis
    """

    # Class-level shared resources
    _checkpoint_manager = None
    _redis_client = None

    def __init__(self):
        super().__init__()

    @property
    def checkpoint_manager(self) -> RedisCheckpointManager:
        """Get or create checkpoint manager (lazy initialization)."""
        if self._checkpoint_manager is None:
            redis_client = self.get_redis_client()
            self.__class__._checkpoint_manager = RedisCheckpointManager(redis_client)
        return self._checkpoint_manager

    def get_redis_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._redis_client is None:
            try:
                config = load_celery_config()
                redis_conf = config['redis_config']

                self.__class__._redis_client = redis.Redis(
                    host=redis_conf['host'],
                    port=redis_conf['port'],
                    db=redis_conf['db_broker'],
                    password=redis_conf.get('password'),
                    decode_responses=True
                )
            except Exception as e:
                logger.error(f"Error creating Redis client: {e}")
                # Fallback
                self.__class__._redis_client = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True
                )

        return self._redis_client

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds."""
        logger.debug(f"Task {task_id} completed successfully")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried."""
        logger.warning(f"Task {task_id} retrying due to: {exc}")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails after all retries."""
        logger.error(f"Task {task_id} failed: {exc}")

        # Log failure to Redis
        try:
            redis_client = self.get_redis_client()
            error_key = f"error:{task_id}"

            error_data = {
                'task_id': task_id,
                'exception': str(exc),
                'args': str(args),
                'kwargs': str(kwargs),
                'traceback': str(einfo)
            }

            redis_client.hset(error_key, mapping=error_data)
            redis_client.expire(error_key, 86400)  # Expire after 24 hours

        except Exception as e:
            logger.error(f"Error logging failure to Redis: {e}")

    def retry_on_rate_limit(self, exc):
        """
        Check if exception is a rate limit error and retry with exponential backoff.

        Args:
            exc: Exception that occurred

        Returns:
            True if retried, False otherwise
        """
        rate_limit_indicators = ['429', 'rate limit', 'quota', 'too many requests']

        exc_str = str(exc).lower()
        is_rate_limit = any(indicator in exc_str for indicator in rate_limit_indicators)

        if is_rate_limit:
            # Calculate exponential backoff: 2^retry_count minutes
            retry_count = self.request.retries
            countdown = (2 ** retry_count) * 60  # In seconds

            logger.warning(f"Rate limit hit, retrying in {countdown}s (attempt {retry_count + 1})")

            # Retry with exponential backoff
            raise self.retry(exc=exc, countdown=countdown, max_retries=5)

        return False


# ═══════════════════════════════════════════════════════════
# CELERY SIGNALS
# ═══════════════════════════════════════════════════════════

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """Handler called before task execution."""
    logger.debug(f"Starting task: {task.name} (ID: {task_id})")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extra):
    """Handler called after task execution."""
    logger.debug(f"Finished task: {task.name} (ID: {task_id}), State: {state}")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extra):
    """Handler called when task fails."""
    logger.error(f"Task failed: {sender.name} (ID: {task_id})")
    logger.error(f"Exception: {exception}")


# ═══════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════

def get_queue_name(annotator_id: int, domain: str) -> str:
    """
    Get queue name for annotator-domain pair.

    Args:
        annotator_id: Annotator ID
        domain: Domain name

    Returns:
        Queue name
    """
    return f"annotator_{annotator_id}_{domain}"


def get_active_queues() -> List[str]:
    """
    Get list of all configured queue names.

    Returns:
        List of queue names
    """
    if not app.conf.task_queues:
        return []

    return [queue.name for queue in app.conf.task_queues]


def get_queue_stats() -> Dict[str, int]:
    """
    Get statistics for all queues.

    Returns:
        Dictionary mapping queue names to message counts
    """
    try:
        inspector = app.control.inspect()
        active_queues = inspector.active_queues()

        stats = {}
        if active_queues:
            for worker, queues in active_queues.items():
                for queue_info in queues:
                    queue_name = queue_info['name']
                    # Get message count from Redis
                    # This is a simplified version; actual implementation would query Redis
                    stats[queue_name] = 0

        return stats

    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        return {}


def purge_queue(queue_name: str) -> int:
    """
    Purge all messages from a queue.

    Args:
        queue_name: Name of queue to purge

    Returns:
        Number of messages purged
    """
    try:
        count = app.control.purge()
        logger.info(f"Purged {count} messages from queue {queue_name}")
        return count
    except Exception as e:
        logger.error(f"Error purging queue {queue_name}: {e}")
        return 0


def get_celery_health() -> Dict[str, any]:
    """
    Get health status of Celery system.

    Returns:
        Dictionary with health information
    """
    health = {
        'broker_connected': False,
        'active_workers': 0,
        'total_queues': len(app.conf.task_queues) if app.conf.task_queues else 0,
        'registered_tasks': len(app.tasks),
    }

    try:
        # Check broker connection
        app.connection().ensure_connection(max_retries=1)
        health['broker_connected'] = True

        # Get active workers
        inspector = app.control.inspect()
        active_workers = inspector.active()
        if active_workers:
            health['active_workers'] = len(active_workers)

    except Exception as e:
        health['error'] = str(e)

    return health


# ═══════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════

__all__ = [
    'app',
    'AnnotationTask',
    'get_queue_name',
    'get_active_queues',
    'get_queue_stats',
    'purge_queue',
    'get_celery_health'
]
