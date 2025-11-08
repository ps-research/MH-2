"""
Worker launcher for spawning and managing Celery worker processes.
"""
import os
import sys
import signal
import time
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from multiprocessing import Process
import redis

from ..core.config_loader import get_config_loader
from ..core.checkpoint import RedisCheckpointManager
from ..storage.excel_manager import ExcelAnnotationManager
from ..core.tasks import populate_task_queues
from ..core.celery_app import get_queue_name


logger = logging.getLogger(__name__)


class WorkerLauncher:
    """
    Launches and manages worker processes for distributed annotation.

    Features:
    - Spawn isolated worker processes using multiprocessing
    - Pre-launch initialization (Excel sync, queue population)
    - Worker process metadata tracking in Redis
    - Heartbeat mechanism for health monitoring
    - Graceful shutdown with Excel buffer flushing
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize worker launcher.

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client
        self.config_loader = get_config_loader()
        self.checkpoint_mgr = RedisCheckpointManager(redis_client)
        self.excel_mgr = ExcelAnnotationManager(
            output_dir='data/annotations',
            redis_client=redis_client
        )

        # Track launched processes
        self._processes: Dict[str, subprocess.Popen] = {}

        # Ensure log directory exists
        self.log_dir = Path('data/logs')
        self.log_dir.mkdir(parents=True, exist_ok=True)

        logger.info("WorkerLauncher initialized")

    # ═══════════════════════════════════════════════════════════
    # KEY GENERATION
    # ═══════════════════════════════════════════════════════════

    def _get_worker_key(self, annotator_id: int, domain: str) -> str:
        """Get unique key for worker."""
        return f"{annotator_id}_{domain}"

    def _get_redis_worker_key(self, annotator_id: int, domain: str) -> str:
        """Get Redis key for worker metadata."""
        return f"worker:{annotator_id}:{domain}"

    # ═══════════════════════════════════════════════════════════
    # PRE-LAUNCH INITIALIZATION
    # ═══════════════════════════════════════════════════════════

    def _pre_launch_init(self, annotator_id: int, domain: str) -> None:
        """
        Perform pre-launch initialization for a worker.

        Steps:
        1. Initialize Excel file if not exists
        2. Sync checkpoint from existing Excel (resume capability)
        3. Populate task queue with pending samples

        Args:
            annotator_id: Annotator ID
            domain: Domain name
        """
        worker_key = self._get_worker_key(annotator_id, domain)
        logger.info(f"Pre-launch initialization for worker {worker_key}")

        try:
            # Step 1: Initialize Excel file
            self.excel_mgr.initialize_file(annotator_id, domain)

            # Step 2: Sync checkpoint from Excel (resume capability)
            synced_count = self.excel_mgr.sync_checkpoint_from_excel(annotator_id, domain)
            if synced_count > 0:
                logger.info(f"Synced {synced_count} completed samples from Excel for {worker_key}")

            # Step 3: Populate task queue with pending samples
            results = populate_task_queues(annotator_id=annotator_id, domain=domain)
            queued_count = results.get('total_queued', 0)
            logger.info(f"Queued {queued_count} tasks for {worker_key}")

        except Exception as e:
            logger.error(f"Pre-launch initialization failed for {worker_key}: {e}")
            raise

    # ═══════════════════════════════════════════════════════════
    # WORKER LAUNCHING
    # ═══════════════════════════════════════════════════════════

    def launch_worker(self, annotator_id: int, domain: str) -> Optional[subprocess.Popen]:
        """
        Launch a single worker process for annotator-domain pair.

        Args:
            annotator_id: Annotator ID (1-5)
            domain: Domain name

        Returns:
            Process object or None if launch failed
        """
        worker_key = self._get_worker_key(annotator_id, domain)
        queue_name = get_queue_name(annotator_id, domain)
        worker_name = f"worker_{annotator_id}_{domain}"
        log_file = self.log_dir / f"{annotator_id}_{domain}.log"

        logger.info(f"Launching worker: {worker_key}")

        try:
            # Pre-launch initialization
            self._pre_launch_init(annotator_id, domain)

            # Build Celery worker command
            celery_app = 'src.core.celery_app'
            hostname = f"{worker_name}@%h"

            command = [
                sys.executable, '-m', 'celery',
                '-A', celery_app,
                'worker',
                '-Q', queue_name,
                '-n', hostname,
                '-c', '1',  # Concurrency = 1
                '--loglevel=info',
                f'--logfile={log_file}'
            ]

            # Launch worker process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd()
            )

            # Store process
            self._processes[worker_key] = process

            # Store worker metadata in Redis
            self._register_worker(annotator_id, domain, process.pid, str(log_file))

            logger.info(f"Worker {worker_key} launched with PID {process.pid}")

            return process

        except Exception as e:
            logger.error(f"Failed to launch worker {worker_key}: {e}")
            return None

    def launch_annotator_pool(self, annotator_id: int) -> List[subprocess.Popen]:
        """
        Launch all 6 workers for an annotator (all domains).

        Args:
            annotator_id: Annotator ID

        Returns:
            List of launched processes
        """
        domains = ['urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal']
        processes = []

        logger.info(f"Launching worker pool for annotator {annotator_id}")

        for domain in domains:
            try:
                # Check if worker is enabled
                worker_config = self.config_loader.get_worker_config(annotator_id, domain)
                if not worker_config.get('enabled', True):
                    logger.info(f"Worker {annotator_id}_{domain} disabled, skipping")
                    continue

                process = self.launch_worker(annotator_id, domain)
                if process:
                    processes.append(process)

                # Small delay between launches to avoid overwhelming Redis
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error launching worker {annotator_id}_{domain}: {e}")

        logger.info(f"Launched {len(processes)} workers for annotator {annotator_id}")

        return processes

    def launch_all(self) -> Dict[str, subprocess.Popen]:
        """
        Launch all 30 workers (5 annotators × 6 domains).

        Returns:
            Dictionary mapping worker keys to processes
        """
        logger.info("Launching all workers...")

        all_processes = {}

        for annotator_id in range(1, 6):  # Annotators 1-5
            processes = self.launch_annotator_pool(annotator_id)

            for process in processes:
                # Find worker key for this process
                for worker_key, stored_process in self._processes.items():
                    if stored_process == process:
                        all_processes[worker_key] = process
                        break

            # Delay between annotator pools
            time.sleep(1.0)

        logger.info(f"Launched {len(all_processes)} workers total")

        return all_processes

    # ═══════════════════════════════════════════════════════════
    # WORKER METADATA MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def _register_worker(
        self,
        annotator_id: int,
        domain: str,
        pid: int,
        log_file: str
    ) -> None:
        """
        Register worker metadata in Redis.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            pid: Process ID
            log_file: Path to log file
        """
        redis_key = self._get_redis_worker_key(annotator_id, domain)
        excel_file = self.excel_mgr._get_file_path(annotator_id, domain)

        worker_data = {
            'pid': pid,
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'last_heartbeat': datetime.now().isoformat(),
            'processed_count': 0,
            'excel_file_path': str(excel_file),
            'log_file_path': log_file
        }

        self.redis.hset(redis_key, mapping=worker_data)
        logger.debug(f"Registered worker metadata in Redis: {redis_key}")

    def update_heartbeat(self, annotator_id: int, domain: str) -> None:
        """
        Update worker heartbeat timestamp.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
        """
        redis_key = self._get_redis_worker_key(annotator_id, domain)

        self.redis.hset(redis_key, 'last_heartbeat', datetime.now().isoformat())

        # Increment processed count
        self.redis.hincrby(redis_key, 'processed_count', 1)

    # ═══════════════════════════════════════════════════════════
    # WORKER STATUS
    # ═══════════════════════════════════════════════════════════

    def get_worker_pid(self, annotator_id: int, domain: str) -> Optional[int]:
        """
        Get process ID for worker.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Process ID or None if not found
        """
        redis_key = self._get_redis_worker_key(annotator_id, domain)
        worker_data = self.redis.hgetall(redis_key)

        if worker_data and 'pid' in worker_data:
            return int(worker_data['pid'])

        return None

    def is_worker_alive(self, annotator_id: int, domain: str) -> bool:
        """
        Check if worker process is alive.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            True if worker is alive, False otherwise
        """
        worker_key = self._get_worker_key(annotator_id, domain)

        # Check if we have the process object
        if worker_key in self._processes:
            process = self._processes[worker_key]
            return process.poll() is None

        # Fallback: check PID from Redis
        pid = self.get_worker_pid(annotator_id, domain)
        if pid:
            try:
                # Send signal 0 to check if process exists
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

        return False

    def get_all_workers_status(self) -> Dict[str, Dict]:
        """
        Get status of all workers.

        Returns:
            Dictionary mapping worker keys to status info
        """
        workers_status = {}

        # Get all worker keys from Redis
        pattern = "worker:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            # Parse key: worker:{annotator_id}:{domain}
            parts = key.split(':')
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]
            worker_key = self._get_worker_key(annotator_id, domain)

            worker_data = self.redis.hgetall(key)
            is_alive = self.is_worker_alive(annotator_id, domain)

            workers_status[worker_key] = {
                'annotator_id': annotator_id,
                'domain': domain,
                'pid': worker_data.get('pid'),
                'status': worker_data.get('status'),
                'alive': is_alive,
                'started_at': worker_data.get('started_at'),
                'last_heartbeat': worker_data.get('last_heartbeat'),
                'processed_count': worker_data.get('processed_count', 0)
            }

        return workers_status

    # ═══════════════════════════════════════════════════════════
    # WORKER SHUTDOWN
    # ═══════════════════════════════════════════════════════════

    def stop_worker(
        self,
        annotator_id: int,
        domain: str,
        force: bool = False,
        timeout: int = 30
    ) -> bool:
        """
        Stop a worker process gracefully or forcefully.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            force: If True, use SIGKILL immediately
            timeout: Graceful shutdown timeout in seconds

        Returns:
            True if worker stopped successfully, False otherwise
        """
        worker_key = self._get_worker_key(annotator_id, domain)
        logger.info(f"Stopping worker {worker_key} (force={force})")

        # Get PID
        pid = self.get_worker_pid(annotator_id, domain)
        if not pid:
            logger.warning(f"Worker {worker_key} not found in Redis")
            return False

        try:
            # Check if process exists
            if not self.is_worker_alive(annotator_id, domain):
                logger.info(f"Worker {worker_key} already stopped")
                self._cleanup_worker(annotator_id, domain)
                return True

            if force:
                # Force kill immediately
                logger.warning(f"Force killing worker {worker_key} (PID {pid})")
                try:
                    if os.name == 'nt':  # Windows
                        # On Windows, use SIGTERM (SIGKILL doesn't exist)
                        os.kill(pid, signal.SIGTERM)
                    else:  # Unix/Linux/Mac
                        os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    # Process already dead, that's fine
                    pass
            else:
                # Graceful shutdown
                logger.info(f"Sending SIGTERM to worker {worker_key} (PID {pid})")

                # Flush Excel buffer before shutdown
                try:
                    self.excel_mgr.flush_buffer(annotator_id, domain)
                    logger.debug(f"Flushed Excel buffer for {worker_key}")
                except Exception as e:
                    logger.error(f"Error flushing Excel buffer: {e}")

                # Send SIGTERM
                os.kill(pid, signal.SIGTERM)

                # Wait for graceful shutdown
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self.is_worker_alive(annotator_id, domain):
                        logger.info(f"Worker {worker_key} stopped gracefully")
                        self._cleanup_worker(annotator_id, domain)
                        return True
                    time.sleep(0.5)

                # Timeout - force kill
                logger.warning(f"Worker {worker_key} did not stop gracefully, force killing")
                try:
                    if os.name == 'nt':  # Windows
                        # On Windows, use SIGTERM (SIGKILL doesn't exist)
                        os.kill(pid, signal.SIGTERM)
                    else:  # Unix/Linux/Mac
                        os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    # Process already dead, that's fine
                    pass

            # Wait a bit for kill to take effect
            time.sleep(1.0)

            # Cleanup
            self._cleanup_worker(annotator_id, domain)

            return True

        except ProcessLookupError:
            logger.warning(f"Worker {worker_key} process not found")
            self._cleanup_worker(annotator_id, domain)
            return True

        except Exception as e:
            logger.error(f"Error stopping worker {worker_key}: {e}")
            return False

    def stop_all(self, force: bool = False) -> Dict[str, bool]:
        """
        Stop all workers.

        Args:
            force: If True, use SIGKILL for all workers

        Returns:
            Dictionary mapping worker keys to stop success status
        """
        logger.info(f"Stopping all workers (force={force})")

        results = {}
        workers_status = self.get_all_workers_status()

        for worker_key, status in workers_status.items():
            if status['alive']:
                annotator_id = status['annotator_id']
                domain = status['domain']

                success = self.stop_worker(annotator_id, domain, force=force)
                results[worker_key] = success

                # Small delay between stops
                time.sleep(0.2)

        logger.info(f"Stopped {len(results)} workers")

        return results

    def _cleanup_worker(self, annotator_id: int, domain: str) -> None:
        """
        Clean up worker metadata after stop.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
        """
        worker_key = self._get_worker_key(annotator_id, domain)
        redis_key = self._get_redis_worker_key(annotator_id, domain)

        # Remove from processes dict
        if worker_key in self._processes:
            del self._processes[worker_key]

        # Update Redis status
        self.redis.hset(redis_key, 'status', 'stopped')

        logger.debug(f"Cleaned up worker {worker_key}")

    # ═══════════════════════════════════════════════════════════
    # RESTART WORKER
    # ═══════════════════════════════════════════════════════════

    def restart_worker(self, annotator_id: int, domain: str) -> Optional[subprocess.Popen]:
        """
        Restart a worker process.

        Steps:
        1. Stop worker gracefully
        2. Re-sync checkpoint from Excel
        3. Re-populate task queue
        4. Launch new worker process

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            New process object or None if failed
        """
        worker_key = self._get_worker_key(annotator_id, domain)
        logger.info(f"Restarting worker {worker_key}")

        try:
            # Stop existing worker
            if self.is_worker_alive(annotator_id, domain):
                self.stop_worker(annotator_id, domain, force=False)
                time.sleep(2.0)  # Wait for full cleanup

            # Launch new worker (pre-launch init will handle sync and queue population)
            process = self.launch_worker(annotator_id, domain)

            if process:
                logger.info(f"Worker {worker_key} restarted successfully")
                return process
            else:
                logger.error(f"Failed to restart worker {worker_key}")
                return None

        except Exception as e:
            logger.error(f"Error restarting worker {worker_key}: {e}")
            return None
