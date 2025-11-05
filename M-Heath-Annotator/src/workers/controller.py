"""
Worker controller for runtime control and management of Celery workers.
"""
import os
import signal
import logging
from typing import Dict, List, Optional
from datetime import datetime
import redis
from celery import Celery

from ..core.celery_app import app, get_queue_name
from ..core.checkpoint import RedisCheckpointManager
from ..storage.excel_manager import ExcelAnnotationManager


logger = logging.getLogger(__name__)


class WorkerController:
    """
    Controls worker runtime behavior using Celery control commands.

    Features:
    - Pause/resume workers (stop consuming tasks)
    - Stop workers gracefully or forcefully
    - Restart workers with checkpoint sync
    - Query worker status and active tasks
    - Force flush Excel buffers
    """

    def __init__(self, redis_client: redis.Redis, celery_app: Optional[Celery] = None):
        """
        Initialize worker controller.

        Args:
            redis_client: Redis client instance
            celery_app: Celery app instance (defaults to global app)
        """
        self.redis = redis_client
        self.app = celery_app or app
        self.checkpoint_mgr = RedisCheckpointManager(redis_client)
        self.excel_mgr = ExcelAnnotationManager(
            output_dir='data/annotations',
            redis_client=redis_client
        )

        logger.info("WorkerController initialized")

    # ═══════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════

    def _get_worker_name(self, annotator_id: int, domain: str) -> str:
        """Get Celery worker name."""
        return f"worker_{annotator_id}_{domain}"

    def _get_redis_key(self, annotator_id: int, domain: str) -> str:
        """Get Redis key for worker metadata."""
        return f"worker:{annotator_id}:{domain}"

    def _get_worker_destination(self, annotator_id: int, domain: str) -> str:
        """
        Get Celery worker destination for control commands.

        Returns:
            Worker destination pattern (e.g., "worker_1_urgency@*")
        """
        worker_name = self._get_worker_name(annotator_id, domain)
        return f"{worker_name}@*"

    # ═══════════════════════════════════════════════════════════
    # PAUSE/RESUME OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def pause_worker(self, annotator_id: int, domain: str) -> bool:
        """
        Pause a worker (stop consuming new tasks, finish current task).

        Implementation:
        1. Flush Excel buffer
        2. Cancel consumer for queue
        3. Update Redis status to 'paused'

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            True if paused successfully, False otherwise
        """
        worker_name = self._get_worker_name(annotator_id, domain)
        queue_name = get_queue_name(annotator_id, domain)
        redis_key = self._get_redis_key(annotator_id, domain)

        logger.info(f"Pausing worker {worker_name}")

        try:
            # Step 1: Flush Excel buffer before pausing
            try:
                self.excel_mgr.flush_buffer(annotator_id, domain)
                logger.debug(f"Flushed Excel buffer for {worker_name}")
            except Exception as e:
                logger.warning(f"Error flushing Excel buffer: {e}")

            # Step 2: Cancel consumer using Celery control
            destination = self._get_worker_destination(annotator_id, domain)

            # Use cancel_consumer to stop consuming from queue
            self.app.control.cancel_consumer(
                queue_name,
                destination=[destination]
            )

            # Step 3: Update Redis status
            self.redis.hset(redis_key, 'status', 'paused')
            self.redis.hset(redis_key, 'paused_at', datetime.now().isoformat())

            logger.info(f"Worker {worker_name} paused successfully")
            return True

        except Exception as e:
            logger.error(f"Error pausing worker {worker_name}: {e}")
            return False

    def resume_worker(self, annotator_id: int, domain: str) -> bool:
        """
        Resume a paused worker (start consuming tasks again).

        Implementation:
        1. Re-sync checkpoint from Excel (in case of manual edits)
        2. Add consumer for queue
        3. Update Redis status to 'running'

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            True if resumed successfully, False otherwise
        """
        worker_name = self._get_worker_name(annotator_id, domain)
        queue_name = get_queue_name(annotator_id, domain)
        redis_key = self._get_redis_key(annotator_id, domain)

        logger.info(f"Resuming worker {worker_name}")

        try:
            # Step 1: Re-sync checkpoint from Excel
            try:
                synced_count = self.excel_mgr.sync_checkpoint_from_excel(annotator_id, domain)
                if synced_count > 0:
                    logger.info(f"Re-synced {synced_count} samples from Excel for {worker_name}")
            except Exception as e:
                logger.warning(f"Error syncing checkpoint: {e}")

            # Step 2: Add consumer using Celery control
            destination = self._get_worker_destination(annotator_id, domain)

            # Use add_consumer to start consuming from queue again
            self.app.control.add_consumer(
                queue_name,
                destination=[destination]
            )

            # Step 3: Update Redis status
            self.redis.hset(redis_key, 'status', 'running')
            self.redis.hset(redis_key, 'resumed_at', datetime.now().isoformat())

            logger.info(f"Worker {worker_name} resumed successfully")
            return True

        except Exception as e:
            logger.error(f"Error resuming worker {worker_name}: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    # STOP OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def stop_worker(self, annotator_id: int, domain: str, force: bool = False) -> bool:
        """
        Stop a worker process.

        Graceful stop:
        1. Flush Excel buffer
        2. Send shutdown signal via Celery control
        3. Close Excel file handles
        4. Clean up Redis state

        Force stop:
        1. Kill process using SIGKILL
        2. Clean up Redis state

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            force: If True, use SIGKILL

        Returns:
            True if stopped successfully, False otherwise
        """
        worker_name = self._get_worker_name(annotator_id, domain)
        redis_key = self._get_redis_key(annotator_id, domain)

        logger.info(f"Stopping worker {worker_name} (force={force})")

        try:
            if force:
                # Force stop using PID
                worker_data = self.redis.hgetall(redis_key)
                pid = worker_data.get('pid')

                if pid:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        logger.warning(f"Force killed worker {worker_name} (PID {pid})")
                    except (ProcessLookupError, ValueError) as e:
                        logger.warning(f"Process not found: {e}")

            else:
                # Graceful stop

                # Step 1: Flush Excel buffer
                try:
                    self.excel_mgr.flush_buffer(annotator_id, domain)
                    logger.debug(f"Flushed Excel buffer for {worker_name}")
                except Exception as e:
                    logger.warning(f"Error flushing Excel buffer: {e}")

                # Step 2: Send shutdown signal via Celery
                destination = self._get_worker_destination(annotator_id, domain)
                self.app.control.broadcast(
                    'shutdown',
                    destination=[destination]
                )

            # Step 3: Clean up Redis state
            self.redis.hset(redis_key, 'status', 'stopped')
            self.redis.hset(redis_key, 'stopped_at', datetime.now().isoformat())

            logger.info(f"Worker {worker_name} stopped successfully")
            return True

        except Exception as e:
            logger.error(f"Error stopping worker {worker_name}: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    # RESTART OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def restart_worker(self, annotator_id: int, domain: str) -> bool:
        """
        Restart a worker process.

        Implementation:
        1. Stop worker gracefully
        2. Re-sync checkpoint from Excel
        3. Re-populate task queue with remaining samples
        4. Worker will be relaunched by launcher/monitoring system

        Note: This does not launch a new worker - it prepares for restart.
        The actual launch should be done by WorkerLauncher.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            True if restart preparation successful, False otherwise
        """
        worker_name = self._get_worker_name(annotator_id, domain)

        logger.info(f"Restarting worker {worker_name}")

        try:
            # Stop worker gracefully
            success = self.stop_worker(annotator_id, domain, force=False)

            if not success:
                logger.error(f"Failed to stop worker {worker_name}")
                return False

            # Re-sync checkpoint from Excel
            try:
                synced_count = self.excel_mgr.sync_checkpoint_from_excel(annotator_id, domain)
                logger.info(f"Re-synced {synced_count} samples from Excel")
            except Exception as e:
                logger.error(f"Error syncing checkpoint: {e}")
                return False

            # Re-populate task queue
            try:
                from ..core.tasks import populate_task_queues
                results = populate_task_queues(annotator_id=annotator_id, domain=domain)
                queued = results.get('total_queued', 0)
                logger.info(f"Re-queued {queued} tasks for {worker_name}")
            except Exception as e:
                logger.error(f"Error populating task queue: {e}")
                return False

            logger.info(f"Worker {worker_name} restart preparation complete")
            return True

        except Exception as e:
            logger.error(f"Error restarting worker {worker_name}: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    # STATUS QUERIES
    # ═══════════════════════════════════════════════════════════

    def get_worker_status(self, annotator_id: int, domain: str) -> Dict:
        """
        Get detailed status for a worker.

        Returns:
            Dictionary with worker status information
        """
        worker_name = self._get_worker_name(annotator_id, domain)
        redis_key = self._get_redis_key(annotator_id, domain)

        # Get worker data from Redis
        worker_data = self.redis.hgetall(redis_key)

        if not worker_data:
            return {
                'annotator_id': annotator_id,
                'domain': domain,
                'status': 'not_found',
                'error': 'Worker not registered'
            }

        # Get progress information
        completed, total = self.checkpoint_mgr.get_progress(annotator_id, domain)
        remaining = total - completed if total > 0 else 0

        # Calculate uptime
        started_at = worker_data.get('started_at')
        uptime_seconds = 0
        if started_at:
            try:
                start_time = datetime.fromisoformat(started_at)
                uptime_seconds = (datetime.now() - start_time).total_seconds()
            except Exception:
                pass

        # Get current task
        current_task = None
        try:
            active_tasks = self.get_active_tasks(annotator_id, domain)
            if active_tasks:
                current_task = active_tasks[0]
        except Exception:
            pass

        # Get Excel file info
        excel_file = worker_data.get('excel_file_path', '')
        excel_last_modified = ''
        try:
            from pathlib import Path
            if excel_file and Path(excel_file).exists():
                mtime = Path(excel_file).stat().st_mtime
                excel_last_modified = datetime.fromtimestamp(mtime).isoformat()
        except Exception:
            pass

        # Get last error (if any)
        last_error = None
        error_key = f"error:worker:{annotator_id}:{domain}"
        if self.redis.exists(error_key):
            last_error = self.redis.get(error_key)

        return {
            'annotator_id': annotator_id,
            'domain': domain,
            'status': worker_data.get('status', 'unknown'),
            'pid': worker_data.get('pid'),
            'uptime': int(uptime_seconds),
            'tasks_processed': int(worker_data.get('processed_count', 0)),
            'tasks_remaining': remaining,
            'current_task': current_task,
            'last_error': last_error,
            'excel_file': excel_file,
            'excel_last_modified': excel_last_modified,
            'started_at': started_at,
            'last_heartbeat': worker_data.get('last_heartbeat')
        }

    def get_active_tasks(self, annotator_id: int, domain: str) -> List[Dict]:
        """
        Get active tasks for a worker.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            List of active task dictionaries
        """
        destination = self._get_worker_destination(annotator_id, domain)

        try:
            # Get active tasks from Celery
            inspector = self.app.control.inspect(destination=[destination])
            active = inspector.active()

            if not active:
                return []

            # Extract tasks from response
            all_tasks = []
            for worker, tasks in active.items():
                for task in tasks:
                    all_tasks.append({
                        'id': task.get('id'),
                        'name': task.get('name'),
                        'args': task.get('args', []),
                        'kwargs': task.get('kwargs', {}),
                        'worker': worker,
                        'time_start': task.get('time_start')
                    })

            return all_tasks

        except Exception as e:
            logger.error(f"Error getting active tasks: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # EXCEL BUFFER MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def flush_excel_buffer(self, annotator_id: int, domain: str) -> int:
        """
        Force flush Excel buffer for a worker.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Number of buffered rows flushed
        """
        worker_name = self._get_worker_name(annotator_id, domain)
        logger.info(f"Flushing Excel buffer for {worker_name}")

        try:
            # Get buffer size before flush
            worker_key = self.excel_mgr._get_worker_key(annotator_id, domain)
            buffer_size = len(self.excel_mgr._buffers.get(worker_key, []))

            # Flush buffer
            self.excel_mgr.flush_buffer(annotator_id, domain)

            logger.info(f"Flushed {buffer_size} rows for {worker_name}")
            return buffer_size

        except Exception as e:
            logger.error(f"Error flushing Excel buffer: {e}")
            return 0

    def flush_all_excel_buffers(self) -> Dict[str, int]:
        """
        Flush Excel buffers for all workers.

        Returns:
            Dictionary mapping worker keys to flushed row counts
        """
        logger.info("Flushing all Excel buffers")

        results = {}

        # Get all registered workers
        pattern = "worker:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            parts = key.split(':')
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]
            worker_key = f"{annotator_id}_{domain}"

            count = self.flush_excel_buffer(annotator_id, domain)
            results[worker_key] = count

        logger.info(f"Flushed Excel buffers for {len(results)} workers")

        return results

    # ═══════════════════════════════════════════════════════════
    # BULK OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def pause_all(self) -> Dict[str, bool]:
        """
        Pause all workers.

        Returns:
            Dictionary mapping worker keys to success status
        """
        logger.info("Pausing all workers")

        results = {}
        pattern = "worker:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            parts = key.split(':')
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]
            worker_key = f"{annotator_id}_{domain}"

            success = self.pause_worker(annotator_id, domain)
            results[worker_key] = success

        logger.info(f"Paused {sum(results.values())} / {len(results)} workers")

        return results

    def resume_all(self) -> Dict[str, bool]:
        """
        Resume all paused workers.

        Returns:
            Dictionary mapping worker keys to success status
        """
        logger.info("Resuming all workers")

        results = {}
        pattern = "worker:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            parts = key.split(':')
            if len(parts) != 3:
                continue

            worker_data = self.redis.hgetall(key)
            if worker_data.get('status') == 'paused':
                annotator_id = int(parts[1])
                domain = parts[2]
                worker_key = f"{annotator_id}_{domain}"

                success = self.resume_worker(annotator_id, domain)
                results[worker_key] = success

        logger.info(f"Resumed {sum(results.values())} / {len(results)} workers")

        return results

    def stop_all(self, force: bool = False) -> Dict[str, bool]:
        """
        Stop all workers.

        Args:
            force: If True, use SIGKILL for all workers

        Returns:
            Dictionary mapping worker keys to success status
        """
        logger.info(f"Stopping all workers (force={force})")

        results = {}
        pattern = "worker:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            parts = key.split(':')
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]
            worker_key = f"{annotator_id}_{domain}"

            success = self.stop_worker(annotator_id, domain, force=force)
            results[worker_key] = success

        logger.info(f"Stopped {sum(results.values())} / {len(results)} workers")

        return results
