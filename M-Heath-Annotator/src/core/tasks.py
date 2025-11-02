"""
Celery annotation tasks with Gemini integration.
"""
import os
import logging
from datetime import datetime
from typing import Dict
import redis

from celery import Task
from .celery_app import app, AnnotationTask
from .gemini_client import GeminiClient, GeminiAPIError, RateLimitError
from .config_loader import get_config_loader
from .checkpoint import RedisCheckpointManager
from ..utils.validators import validate_response
from ..storage.excel_manager import ExcelAnnotationManager
from ..storage.malform_logger import MalformLogger
from ..models.annotation import AnnotationRequest, AnnotationResult


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# SHARED RESOURCES (LAZY INITIALIZATION)
# ═══════════════════════════════════════════════════════════

_redis_client = None
_gemini_client = None
_excel_manager = None
_malform_logger = None
_checkpoint_mgr = None


def get_redis_client() -> redis.Redis:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        config_loader = get_config_loader()
        settings = config_loader.get_settings_config()
        redis_config = settings['redis']

        _redis_client = redis.Redis(
            host=redis_config['host'],
            port=redis_config['port'],
            db=redis_config['db_broker'],
            password=redis_config.get('password'),
            decode_responses=True
        )
        logger.info("Initialized Redis client for tasks")

    return _redis_client


def get_gemini_client() -> GeminiClient:
    """Get or create Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        redis_client = get_redis_client()
        _gemini_client = GeminiClient(redis_client)
        logger.info("Initialized Gemini client for tasks")

    return _gemini_client


def get_excel_manager() -> ExcelAnnotationManager:
    """Get or create Excel annotation manager."""
    global _excel_manager
    if _excel_manager is None:
        redis_client = get_redis_client()

        # Get output directory from settings
        config_loader = get_config_loader()
        settings = config_loader.get_settings_config()
        output_dir = settings.get('output', {}).get('directory', 'data/annotations')

        _excel_manager = ExcelAnnotationManager(
            output_dir=output_dir,
            redis_client=redis_client,
            buffer_size=1  # Immediate write for individual tasks
        )
        logger.info("Initialized Excel annotation manager for tasks")

    return _excel_manager


def get_malform_logger() -> MalformLogger:
    """Get or create malform logger."""
    global _malform_logger
    if _malform_logger is None:
        redis_client = get_redis_client()
        _malform_logger = MalformLogger(
            log_dir='data/malform_logs',
            redis_client=redis_client
        )
        logger.info("Initialized malform logger for tasks")

    return _malform_logger


def get_checkpoint_manager() -> RedisCheckpointManager:
    """Get or create checkpoint manager."""
    global _checkpoint_mgr
    if _checkpoint_mgr is None:
        redis_client = get_redis_client()
        _checkpoint_mgr = RedisCheckpointManager(redis_client)
        logger.info("Initialized checkpoint manager for tasks")

    return _checkpoint_mgr


# ═══════════════════════════════════════════════════════════
# ANNOTATION TASK
# ═══════════════════════════════════════════════════════════

@app.task(
    base=AnnotationTask,
    bind=True,
    name='annotate_sample',
    max_retries=3,
    default_retry_delay=60
)
def annotate_sample(
    self,
    annotator_id: int,
    domain: str,
    sample_id: str,
    text: str
) -> Dict:
    """
    Annotate a single sample using Gemini AI.

    Task workflow:
    1. Check checkpoint (skip if completed)
    2. Load configuration (prompt, API key)
    3. Build prompt
    4. Generate response with rate limiting
    5. Parse and validate response
    6. Write to Excel
    7. Log malformed responses
    8. Update checkpoint
    9. Return result

    Args:
        annotator_id: Annotator ID (1-5)
        domain: Domain name
        sample_id: Sample identifier
        text: Text to annotate

    Returns:
        Dictionary with annotation result
    """
    task_id = self.request.id
    start_time = datetime.now()

    logger.info(f"[{task_id}] Starting annotation: {sample_id} for annotator {annotator_id}, domain {domain}")

    try:
        # Get shared resources
        checkpoint_mgr = get_checkpoint_manager()
        config_loader = get_config_loader()
        gemini_client = get_gemini_client()
        excel_manager = get_excel_manager()
        malform_logger = get_malform_logger()

        # ───────────────────────────────────────────────────────
        # STEP 1: Check checkpoint
        # ───────────────────────────────────────────────────────
        if checkpoint_mgr.is_completed(annotator_id, domain, sample_id):
            logger.info(f"[{task_id}] Sample {sample_id} already completed, skipping")
            return {
                'sample_id': sample_id,
                'status': 'skipped',
                'message': 'Already completed'
            }

        # ───────────────────────────────────────────────────────
        # STEP 2: Load configuration
        # ───────────────────────────────────────────────────────
        domain_config = config_loader.get_domain_config(domain)
        prompt_template = domain_config['prompt_template']

        # ───────────────────────────────────────────────────────
        # STEP 3: Build prompt
        # ───────────────────────────────────────────────────────
        prompt = prompt_template.format(text=text)
        logger.debug(f"[{task_id}] Built prompt (length: {len(prompt)})")

        # ───────────────────────────────────────────────────────
        # STEP 4: Generate response
        # ───────────────────────────────────────────────────────
        try:
            raw_response = gemini_client.generate(
                prompt=prompt,
                annotator_id=annotator_id,
                domain=domain,
                max_retries=3
            )
            logger.debug(f"[{task_id}] Generated response (length: {len(raw_response)})")

        except RateLimitError as e:
            # Rate limit - retry task
            logger.warning(f"[{task_id}] Rate limit hit, retrying task")
            raise self.retry(exc=e, countdown=e.retry_after)

        except GeminiAPIError as e:
            if e.should_retry:
                # Retriable error - retry task
                logger.warning(f"[{task_id}] Retriable API error, retrying: {e}")
                raise self.retry(exc=e, countdown=60)
            else:
                # Non-retriable error - mark as error
                logger.error(f"[{task_id}] Non-retriable API error: {e}")
                result = AnnotationResult(
                    sample_id=sample_id,
                    status='error',
                    label=None,
                    raw_response=str(e),
                    parsing_error=None,
                    validity_error=str(e)
                )

                # Write to Excel
                _write_result_to_excel(excel_manager, annotator_id, domain, sample_id, text, result)

                # Mark as completed (don't retry errors)
                checkpoint_mgr.mark_completed(annotator_id, domain, sample_id)

                return result.dict()

        # ───────────────────────────────────────────────────────
        # STEP 5: Parse and validate response
        # ───────────────────────────────────────────────────────
        validation_result = validate_response(domain, raw_response)

        if validation_result.is_valid:
            # Success
            status = 'success'
            label = validation_result.label
            parsing_error = None
            validity_error = None

            logger.info(f"[{task_id}] Successfully annotated {sample_id}: {label}")

        else:
            # Malformed response
            status = 'malformed'
            label = None
            parsing_error = validation_result.parsing_error
            validity_error = validation_result.validity_error

            logger.warning(f"[{task_id}] Malformed response for {sample_id}: {parsing_error or validity_error}")

        # ───────────────────────────────────────────────────────
        # STEP 6: Create result
        # ───────────────────────────────────────────────────────
        result = AnnotationResult(
            sample_id=sample_id,
            status=status,
            label=label,
            raw_response=raw_response,
            parsing_error=parsing_error,
            validity_error=validity_error,
            timestamp=datetime.now()
        )

        # ───────────────────────────────────────────────────────
        # STEP 7: Write to Excel
        # ───────────────────────────────────────────────────────
        _write_result_to_excel(excel_manager, annotator_id, domain, sample_id, text, result)

        # ───────────────────────────────────────────────────────
        # STEP 8: Log malformed if needed
        # ───────────────────────────────────────────────────────
        if result.is_malformed():
            error_data = {
                'sample_text': text,
                'raw_response': raw_response,
                'parsing_error': parsing_error,
                'validity_error': validity_error,
                'retry_count': 0,
                'task_id': task_id
            }
            malform_logger.log_error(annotator_id, domain, sample_id, error_data)

        # ───────────────────────────────────────────────────────
        # STEP 9: Update checkpoint
        # ───────────────────────────────────────────────────────
        checkpoint_mgr.mark_completed(annotator_id, domain, sample_id)

        # ───────────────────────────────────────────────────────
        # STEP 10: Track task metrics
        # ───────────────────────────────────────────────────────
        duration = (datetime.now() - start_time).total_seconds()
        _track_task_metrics(annotator_id, domain, task_id, duration, result.status)

        logger.info(f"[{task_id}] Task completed in {duration:.2f}s: {result.status}")

        # ───────────────────────────────────────────────────────
        # STEP 11: Return result
        # ───────────────────────────────────────────────────────
        return result.dict()

    except Exception as e:
        # Unexpected error
        logger.error(f"[{task_id}] Unexpected error: {e}", exc_info=True)

        # Try to mark as error in checkpoint (don't retry forever)
        try:
            checkpoint_mgr = get_checkpoint_manager()
            checkpoint_mgr.mark_completed(annotator_id, domain, sample_id)
        except:
            pass

        raise


# ═══════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def _write_result_to_excel(
    excel_manager: ExcelAnnotationManager,
    annotator_id: int,
    domain: str,
    sample_id: str,
    text: str,
    result: AnnotationResult
) -> None:
    """Write annotation result to Excel file."""
    try:
        # Initialize file if needed
        excel_manager.initialize_file(annotator_id, domain)

        # Prepare row data
        row_data = {
            'sample_id': sample_id,
            'text': text,
            'raw_response': result.raw_response,
            'label': result.label or '',
            'malformed_flag': result.is_malformed(),
            'parsing_error': result.parsing_error or '',
            'validity_error': result.validity_error or '',
            'timestamp': result.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

        # Write (this will be buffered and flushed periodically)
        excel_manager.write_annotation(annotator_id, domain, row_data)

        # Force flush for individual task (buffer_size=1 means immediate write)
        excel_manager.flush_buffer(annotator_id, domain)

    except Exception as e:
        logger.error(f"Error writing to Excel: {e}")
        # Don't raise - we've still completed the annotation


def _track_task_metrics(
    annotator_id: int,
    domain: str,
    task_id: str,
    duration: float,
    status: str
) -> None:
    """Track task execution metrics in Redis."""
    try:
        redis_client = get_redis_client()

        # Task details
        task_key = f"task:{task_id}"
        redis_client.hset(task_key, mapping={
            'annotator_id': annotator_id,
            'domain': domain,
            'duration': duration,
            'status': status,
            'completed_at': datetime.now().isoformat()
        })
        redis_client.expire(task_key, 86400)  # 24 hours

        # Aggregate metrics
        metrics_key = f"task_metrics:{annotator_id}:{domain}"
        pipe = redis_client.pipeline()
        pipe.hincrby(metrics_key, 'total_tasks', 1)
        pipe.hincrbyfloat(metrics_key, 'total_duration', duration)

        if status == 'success':
            pipe.hincrby(metrics_key, 'successful_tasks', 1)
        elif status == 'malformed':
            pipe.hincrby(metrics_key, 'malformed_tasks', 1)
        else:
            pipe.hincrby(metrics_key, 'error_tasks', 1)

        pipe.expire(metrics_key, 86400)  # 24 hours
        pipe.execute()

    except Exception as e:
        logger.warning(f"Error tracking task metrics: {e}")


# ═══════════════════════════════════════════════════════════
# TASK QUEUE POPULATION
# ═══════════════════════════════════════════════════════════

def populate_task_queues(
    annotator_id: int = None,
    domain: str = None,
    limit: int = None
) -> Dict:
    """
    Populate Celery task queues with annotation tasks.

    Args:
        annotator_id: Specific annotator ID (or None for all)
        domain: Specific domain (or None for all)
        limit: Maximum samples per worker (or None for all)

    Returns:
        Dictionary with queued task counts
    """
    logger.info(f"Populating task queues: annotator={annotator_id}, domain={domain}, limit={limit}")

    from .celery_app import get_queue_name
    from ..storage.source_loader import SourceDataLoader

    # Get shared resources
    redis_client = get_redis_client()
    config_loader = get_config_loader()
    checkpoint_mgr = get_checkpoint_manager()
    excel_manager = get_excel_manager()

    # Load source data
    settings = config_loader.get_settings_config()
    excel_path = settings.get('data', {}).get('excel_path', 'data/source/m_help_dataset.xlsx')

    source_loader = SourceDataLoader(
        excel_path=excel_path,
        redis_client=redis_client
    )

    # Load all samples
    all_samples = source_loader.load_all_samples()
    logger.info(f"Loaded {len(all_samples)} samples from source")

    # Determine which workers to process
    annotator_ids = [annotator_id] if annotator_id else config_loader.get_all_annotator_ids()
    domains = [domain] if domain else config_loader.get_all_domain_names()

    results = {
        'total_queued': 0,
        'by_worker': {}
    }

    # Process each worker
    for ann_id in annotator_ids:
        for dom in domains:
            worker_key = f"{ann_id}_{dom}"

            try:
                # Get worker configuration
                worker_config = config_loader.get_worker_config(ann_id, dom)

                if not worker_config.get('enabled', True):
                    logger.info(f"Worker {worker_key} disabled, skipping")
                    continue

                # Sync checkpoint from Excel (for resume capability)
                synced_count = excel_manager.sync_checkpoint_from_excel(ann_id, dom)
                if synced_count > 0:
                    logger.info(f"Synced {synced_count} completed samples from Excel for {worker_key}")

                # Get completed samples
                completed_ids = checkpoint_mgr.get_completed_samples(ann_id, dom)

                # Filter pending samples
                pending_samples = [
                    s for s in all_samples
                    if s['sample_id'] not in completed_ids
                ]

                # Apply limit
                sample_limit = limit or worker_config.get('sample_limit')
                if sample_limit:
                    pending_samples = pending_samples[:sample_limit]

                logger.info(f"Worker {worker_key}: {len(pending_samples)} pending samples")

                # Queue tasks
                queue_name = get_queue_name(ann_id, dom)
                queued_count = 0

                for sample in pending_samples:
                    annotate_sample.apply_async(
                        kwargs={
                            'annotator_id': ann_id,
                            'domain': dom,
                            'sample_id': sample['sample_id'],
                            'text': sample['text']
                        },
                        queue=queue_name
                    )
                    queued_count += 1

                results['by_worker'][worker_key] = {
                    'queued': queued_count,
                    'completed': len(completed_ids),
                    'total': len(all_samples),
                    'queue_name': queue_name
                }

                results['total_queued'] += queued_count

                logger.info(f"Queued {queued_count} tasks for {worker_key} on queue {queue_name}")

                # Store queue metadata
                _store_queue_metadata(redis_client, ann_id, dom, queued_count)

            except Exception as e:
                logger.error(f"Error processing worker {worker_key}: {e}")
                results['by_worker'][worker_key] = {
                    'error': str(e)
                }

    logger.info(f"Queue population complete: {results['total_queued']} total tasks queued")

    return results


def _store_queue_metadata(
    redis_client: redis.Redis,
    annotator_id: int,
    domain: str,
    total_queued: int
) -> None:
    """Store queue metadata in Redis."""
    key = f"queue_meta:{annotator_id}:{domain}"

    metadata = {
        'total_queued': total_queued,
        'queued_at': datetime.now().isoformat()
    }

    redis_client.hset(key, mapping=metadata)
    redis_client.expire(key, 86400)  # 24 hours
