"""
Control API for programmatic worker management with thread-safe operations.
"""
import time
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from contextlib import contextmanager
import redis

from ..workers.launcher import WorkerLauncher
from ..workers.controller import WorkerController
from ..workers.monitor import WorkerMonitor
from ..core.checkpoint import RedisCheckpointManager
from ..storage.excel_manager import ExcelAnnotationManager


logger = logging.getLogger(__name__)


class ControlAPI:
    """
    High-level API for programmatic worker control.

    Features:
    - Thread-safe operations using Redis locks
    - Bulk operations with error handling
    - Global status queries
    - Progress consolidation from Excel files
    - Data integrity verification
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize control API.

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client
        self.launcher = WorkerLauncher(redis_client)
        self.controller = WorkerController(redis_client)
        self.monitor = WorkerMonitor(redis_client)
        self.checkpoint_mgr = RedisCheckpointManager(redis_client)
        self.excel_mgr = ExcelAnnotationManager(
            output_dir='data/annotations',
            redis_client=redis_client
        )

        logger.info("ControlAPI initialized")

    # ═══════════════════════════════════════════════════════════
    # REDIS LOCKS
    # ═══════════════════════════════════════════════════════════

    @contextmanager
    def operation_lock(self, operation_type: str, timeout: int = 60):
        """
        Context manager for operation locking.

        Args:
            operation_type: Type of operation (e.g., 'pause', 'stop', 'restart')
            timeout: Lock timeout in seconds

        Yields:
            Lock acquired successfully

        Raises:
            RuntimeError: If lock cannot be acquired
        """
        lock_key = f"lock:operation:{operation_type}"
        lock_value = f"{datetime.now().isoformat()}"

        # Try to acquire lock
        acquired = self.redis.set(lock_key, lock_value, nx=True, ex=timeout)

        if not acquired:
            raise RuntimeError(f"Operation {operation_type} already in progress")

        try:
            logger.debug(f"Acquired lock for operation: {operation_type}")
            yield

        finally:
            # Release lock
            self.redis.delete(lock_key)
            logger.debug(f"Released lock for operation: {operation_type}")

    # ═══════════════════════════════════════════════════════════
    # COMMAND EXECUTION
    # ═══════════════════════════════════════════════════════════

    def execute_command(self, command: str, **kwargs) -> Dict:
        """
        Execute a control command with locking.

        Supported commands:
        - pause: Pause worker(s)
        - resume: Resume worker(s)
        - stop: Stop worker(s)
        - restart: Restart worker(s)
        - status: Get worker status
        - flush: Flush Excel buffer(s)

        Args:
            command: Command name
            **kwargs: Command parameters (annotator_id, domain, force, etc.)

        Returns:
            Dictionary with command result
        """
        start_time = time.time()

        logger.info(f"Executing command: {command} with params: {kwargs}")

        result = {
            'command': command,
            'params': kwargs,
            'success': False,
            'timestamp': datetime.now().isoformat()
        }

        try:
            # Commands that don't need locking
            if command == 'status':
                annotator_id = kwargs.get('annotator_id')
                domain = kwargs.get('domain')

                if annotator_id and domain:
                    result['data'] = self.controller.get_worker_status(annotator_id, domain)
                else:
                    result['data'] = self.monitor.get_all_worker_statuses()

                result['success'] = True

            # Commands that need locking
            elif command == 'pause':
                with self.operation_lock('pause'):
                    annotator_id = kwargs['annotator_id']
                    domain = kwargs['domain']
                    success = self.controller.pause_worker(annotator_id, domain)
                    result['success'] = success

            elif command == 'resume':
                with self.operation_lock('resume'):
                    annotator_id = kwargs['annotator_id']
                    domain = kwargs['domain']
                    success = self.controller.resume_worker(annotator_id, domain)
                    result['success'] = success

            elif command == 'stop':
                with self.operation_lock('stop'):
                    annotator_id = kwargs['annotator_id']
                    domain = kwargs['domain']
                    force = kwargs.get('force', False)
                    success = self.controller.stop_worker(annotator_id, domain, force=force)
                    result['success'] = success

            elif command == 'restart':
                with self.operation_lock('restart'):
                    annotator_id = kwargs['annotator_id']
                    domain = kwargs['domain']
                    process = self.launcher.restart_worker(annotator_id, domain)
                    result['success'] = process is not None
                    result['pid'] = process.pid if process else None

            elif command == 'flush':
                annotator_id = kwargs['annotator_id']
                domain = kwargs['domain']
                count = self.controller.flush_excel_buffer(annotator_id, domain)
                result['success'] = True
                result['flushed_rows'] = count

            elif command == 'pause_all':
                with self.operation_lock('pause_all'):
                    results = self.controller.pause_all()
                    result['data'] = results
                    result['success'] = True

            elif command == 'resume_all':
                with self.operation_lock('resume_all'):
                    results = self.controller.resume_all()
                    result['data'] = results
                    result['success'] = True

            elif command == 'stop_all':
                with self.operation_lock('stop_all'):
                    force = kwargs.get('force', False)
                    results = self.controller.stop_all(force=force)
                    result['data'] = results
                    result['success'] = True

            elif command == 'flush_all':
                results = self.controller.flush_all_excel_buffers()
                result['data'] = results
                result['success'] = True

            else:
                result['error'] = f"Unknown command: {command}"

        except Exception as e:
            logger.error(f"Error executing command {command}: {e}", exc_info=True)
            result['error'] = str(e)

        # Add execution duration
        duration = time.time() - start_time
        result['duration_seconds'] = round(duration, 3)

        return result

    # ═══════════════════════════════════════════════════════════
    # BULK OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def bulk_operation(
        self,
        operation: str,
        targets: List[Tuple[int, str]]
    ) -> Dict:
        """
        Perform bulk operation on multiple workers.

        Args:
            operation: Operation name ('pause', 'resume', 'stop', 'restart', 'flush')
            targets: List of (annotator_id, domain) tuples

        Returns:
            Dictionary with results per target
        """
        start_time = time.time()

        logger.info(f"Executing bulk {operation} on {len(targets)} workers")

        result = {
            'operation': operation,
            'total_targets': len(targets),
            'results': {},
            'summary': {
                'success': 0,
                'failed': 0
            },
            'timestamp': datetime.now().isoformat()
        }

        # Acquire lock for bulk operation
        try:
            with self.operation_lock(f"bulk_{operation}"):
                for annotator_id, domain in targets:
                    worker_key = f"{annotator_id}_{domain}"

                    try:
                        if operation == 'pause':
                            success = self.controller.pause_worker(annotator_id, domain)

                        elif operation == 'resume':
                            success = self.controller.resume_worker(annotator_id, domain)

                        elif operation == 'stop':
                            success = self.controller.stop_worker(annotator_id, domain)

                        elif operation == 'restart':
                            process = self.launcher.restart_worker(annotator_id, domain)
                            success = process is not None

                        elif operation == 'flush':
                            count = self.controller.flush_excel_buffer(annotator_id, domain)
                            success = True
                            result['results'][worker_key] = {
                                'success': success,
                                'flushed_rows': count
                            }
                            result['summary']['success'] += 1
                            continue

                        else:
                            success = False
                            result['results'][worker_key] = {
                                'success': False,
                                'error': f"Unknown operation: {operation}"
                            }
                            result['summary']['failed'] += 1
                            continue

                        result['results'][worker_key] = {'success': success}

                        if success:
                            result['summary']['success'] += 1
                        else:
                            result['summary']['failed'] += 1

                    except Exception as e:
                        logger.error(f"Error in bulk operation for {worker_key}: {e}")
                        result['results'][worker_key] = {
                            'success': False,
                            'error': str(e)
                        }
                        result['summary']['failed'] += 1

        except RuntimeError as e:
            # Lock acquisition failed
            result['error'] = str(e)
            logger.error(f"Bulk operation lock failed: {e}")

        # Add duration
        duration = time.time() - start_time
        result['duration_seconds'] = round(duration, 3)

        logger.info(f"Bulk {operation} complete: {result['summary']['success']} success, {result['summary']['failed']} failed")

        return result

    # ═══════════════════════════════════════════════════════════
    # GLOBAL STATUS
    # ═══════════════════════════════════════════════════════════

    def get_global_status(self) -> Dict:
        """
        Get comprehensive global status of all workers and system.

        Returns:
            Dictionary with global status information
        """
        logger.info("Getting global status")

        status = {
            'timestamp': datetime.now().isoformat(),
            'workers': {},
            'system': {},
            'summary': {
                'total_workers': 0,
                'running': 0,
                'paused': 0,
                'stopped': 0,
                'healthy': 0,
                'unhealthy': 0
            }
        }

        # Get worker statuses
        worker_statuses = self.monitor.get_all_worker_statuses()
        status['workers'] = worker_statuses
        status['summary']['total_workers'] = len(worker_statuses)

        # Count by status
        for worker_key, worker_status in worker_statuses.items():
            worker_state = worker_status.get('status', 'unknown')

            if worker_state == 'running':
                status['summary']['running'] += 1
            elif worker_state == 'paused':
                status['summary']['paused'] += 1
            elif worker_state == 'stopped':
                status['summary']['stopped'] += 1

            if worker_status.get('healthy', False):
                status['summary']['healthy'] += 1
            else:
                status['summary']['unhealthy'] += 1

        # Get system metrics
        status['system'] = self.monitor.get_system_metrics()

        # Get checkpoint summary
        status['checkpoint_summary'] = self.checkpoint_mgr.get_summary()

        return status

    # ═══════════════════════════════════════════════════════════
    # PROGRESS CONSOLIDATION
    # ═══════════════════════════════════════════════════════════

    def consolidate_progress(self) -> Dict:
        """
        Consolidate progress from all Excel files and compare with Redis.

        Returns:
            Dictionary with consolidated progress and discrepancies
        """
        logger.info("Consolidating progress from Excel files")

        consolidation = {
            'timestamp': datetime.now().isoformat(),
            'by_worker': {},
            'discrepancies': [],
            'summary': {
                'total_completed': 0,
                'total_expected': 0,
                'discrepancies_found': 0
            }
        }

        # Get all workers
        pattern = "worker:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            parts = key.split(':')
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]
            worker_key = f"{annotator_id}_{domain}"

            # Get progress from Redis checkpoint
            redis_completed, redis_total = self.checkpoint_mgr.get_progress(annotator_id, domain)

            # Get progress from Excel file
            excel_completed_ids = self.excel_mgr.get_completed_sample_ids(annotator_id, domain)
            excel_completed = len(excel_completed_ids)

            consolidation['by_worker'][worker_key] = {
                'redis_completed': redis_completed,
                'excel_completed': excel_completed,
                'total': redis_total,
                'match': redis_completed == excel_completed
            }

            consolidation['summary']['total_completed'] += excel_completed
            consolidation['summary']['total_expected'] += redis_total

            # Check for discrepancies
            if redis_completed != excel_completed:
                discrepancy = {
                    'worker_key': worker_key,
                    'redis_count': redis_completed,
                    'excel_count': excel_completed,
                    'difference': abs(redis_completed - excel_completed)
                }
                consolidation['discrepancies'].append(discrepancy)
                consolidation['summary']['discrepancies_found'] += 1

                logger.warning(f"Progress discrepancy for {worker_key}: Redis={redis_completed}, Excel={excel_completed}")

        return consolidation

    # ═══════════════════════════════════════════════════════════
    # DATA INTEGRITY
    # ═══════════════════════════════════════════════════════════

    def verify_data_integrity(self) -> Dict:
        """
        Verify data integrity across Redis and Excel files.

        Checks:
        - Redis checkpoint vs Excel file consistency
        - Excel file integrity (not corrupted)
        - Missing files
        - Malform log consistency

        Returns:
            Dictionary with integrity verification results
        """
        logger.info("Verifying data integrity")

        verification = {
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'issues': [],
            'summary': {
                'total_checks': 0,
                'passed': 0,
                'failed': 0
            }
        }

        # Check 1: Progress consistency
        consolidation = self.consolidate_progress()
        verification['checks']['progress_consistency'] = {
            'status': 'PASS' if len(consolidation['discrepancies']) == 0 else 'FAIL',
            'discrepancies': consolidation['discrepancies']
        }
        verification['summary']['total_checks'] += 1

        if len(consolidation['discrepancies']) == 0:
            verification['summary']['passed'] += 1
        else:
            verification['summary']['failed'] += 1
            for disc in consolidation['discrepancies']:
                verification['issues'].append(f"Progress mismatch for {disc['worker_key']}")

        # Check 2: Excel file integrity
        excel_integrity = self.monitor.verify_excel_integrity()
        failed_excel = [k for k, v in excel_integrity.items() if not v]

        verification['checks']['excel_integrity'] = {
            'status': 'PASS' if len(failed_excel) == 0 else 'FAIL',
            'failed_files': failed_excel
        }
        verification['summary']['total_checks'] += 1

        if len(failed_excel) == 0:
            verification['summary']['passed'] += 1
        else:
            verification['summary']['failed'] += 1
            for worker_key in failed_excel:
                verification['issues'].append(f"Excel file corrupted for {worker_key}")

        # Check 3: Missing Excel files
        pattern = "worker:*"
        keys = self.redis.keys(pattern)
        missing_files = []

        for key in keys:
            parts = key.split(':')
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]
            worker_key = f"{annotator_id}_{domain}"

            file_path = self.excel_mgr._get_file_path(annotator_id, domain)
            if not file_path.exists():
                missing_files.append(worker_key)

        verification['checks']['missing_files'] = {
            'status': 'PASS' if len(missing_files) == 0 else 'FAIL',
            'missing': missing_files
        }
        verification['summary']['total_checks'] += 1

        if len(missing_files) == 0:
            verification['summary']['passed'] += 1
        else:
            verification['summary']['failed'] += 1
            for worker_key in missing_files:
                verification['issues'].append(f"Excel file missing for {worker_key}")

        # Overall status
        verification['overall_status'] = 'PASS' if verification['summary']['failed'] == 0 else 'FAIL'

        logger.info(f"Data integrity check: {verification['summary']['passed']}/{verification['summary']['total_checks']} passed")

        return verification

    # ═══════════════════════════════════════════════════════════
    # QUEUE MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def get_queue_stats(self) -> Dict[str, Dict]:
        """
        Get statistics for all task queues.

        Returns:
            Dictionary with queue stats
        """
        from ..core.celery_app import app

        stats = {}

        try:
            inspector = app.control.inspect()

            # Get active tasks
            active = inspector.active() or {}

            # Get reserved tasks
            reserved = inspector.reserved() or {}

            # Count per queue
            queue_counts = {}

            for worker, tasks in active.items():
                for task in tasks:
                    queue = task.get('delivery_info', {}).get('routing_key', 'unknown')
                    if queue not in queue_counts:
                        queue_counts[queue] = {'active': 0, 'reserved': 0}
                    queue_counts[queue]['active'] += 1

            for worker, tasks in reserved.items():
                for task in tasks:
                    queue = task.get('delivery_info', {}).get('routing_key', 'unknown')
                    if queue not in queue_counts:
                        queue_counts[queue] = {'active': 0, 'reserved': 0}
                    queue_counts[queue]['reserved'] += 1

            stats = queue_counts

        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")

        return stats
