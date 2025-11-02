"""
Redis-based checkpoint manager for distributed annotation system.
"""
import json
import redis
from typing import List, Dict, Tuple, Optional, Set
from datetime import datetime
from pathlib import Path
import logging


logger = logging.getLogger(__name__)


class RedisCheckpointManager:
    """
    Manages annotation checkpoints using Redis for distributed coordination.

    Redis Key Patterns:
    - checkpoint:{annotator_id}:{domain} - Redis Set of completed sample IDs
    - progress:{annotator_id}:{domain} - Redis Hash with completed/total/last_updated
    - worker:{annotator_id}:{domain} - Redis Hash with worker state (status/pid/started_at)
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize checkpoint manager.

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client
        logger.info("RedisCheckpointManager initialized")

    # ═══════════════════════════════════════════════════════════
    # KEY GENERATION
    # ═══════════════════════════════════════════════════════════

    def _checkpoint_key(self, annotator_id: int, domain: str) -> str:
        """Generate Redis key for completed samples set."""
        return f"checkpoint:{annotator_id}:{domain}"

    def _progress_key(self, annotator_id: int, domain: str) -> str:
        """Generate Redis key for progress tracking hash."""
        return f"progress:{annotator_id}:{domain}"

    def _worker_key(self, annotator_id: int, domain: str) -> str:
        """Generate Redis key for worker state hash."""
        return f"worker:{annotator_id}:{domain}"

    # ═══════════════════════════════════════════════════════════
    # COMPLETION TRACKING
    # ═══════════════════════════════════════════════════════════

    def is_completed(self, annotator_id: int, domain: str, sample_id: str) -> bool:
        """
        Check if a sample has been completed for a specific annotator-domain pair.

        Args:
            annotator_id: Annotator ID (1-5)
            domain: Domain name
            sample_id: Sample identifier

        Returns:
            True if sample is completed, False otherwise
        """
        key = self._checkpoint_key(annotator_id, domain)
        return self.redis.sismember(key, sample_id) == 1

    def mark_completed(self, annotator_id: int, domain: str, sample_id: str) -> None:
        """
        Mark a sample as completed using atomic Redis transaction.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            sample_id: Sample identifier
        """
        checkpoint_key = self._checkpoint_key(annotator_id, domain)
        progress_key = self._progress_key(annotator_id, domain)

        # Use pipeline for atomic operations
        pipe = self.redis.pipeline()

        # Add to completed set
        pipe.sadd(checkpoint_key, sample_id)

        # Update progress hash
        pipe.hincrby(progress_key, "completed", 1)
        pipe.hset(progress_key, "last_updated", datetime.now().isoformat())

        # Execute atomically
        pipe.execute()

        logger.debug(f"Marked sample {sample_id} as completed for annotator {annotator_id}, domain {domain}")

    def mark_completed_batch(self, annotator_id: int, domain: str, sample_ids: List[str]) -> None:
        """
        Mark multiple samples as completed in a single atomic transaction.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            sample_ids: List of sample identifiers
        """
        if not sample_ids:
            return

        checkpoint_key = self._checkpoint_key(annotator_id, domain)
        progress_key = self._progress_key(annotator_id, domain)

        # Use pipeline for atomic operations
        pipe = self.redis.pipeline()

        # Add all to completed set
        pipe.sadd(checkpoint_key, *sample_ids)

        # Update progress hash
        pipe.hincrby(progress_key, "completed", len(sample_ids))
        pipe.hset(progress_key, "last_updated", datetime.now().isoformat())

        # Execute atomically
        pipe.execute()

        logger.info(f"Marked {len(sample_ids)} samples as completed for annotator {annotator_id}, domain {domain}")

    def get_completed_samples(self, annotator_id: int, domain: str) -> Set[str]:
        """
        Get all completed sample IDs for an annotator-domain pair.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Set of completed sample IDs
        """
        key = self._checkpoint_key(annotator_id, domain)
        completed = self.redis.smembers(key)
        return set(completed) if completed else set()

    def get_completed_count(self, annotator_id: int, domain: str) -> int:
        """
        Get count of completed samples.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Number of completed samples
        """
        key = self._checkpoint_key(annotator_id, domain)
        return self.redis.scard(key)

    # ═══════════════════════════════════════════════════════════
    # PROGRESS TRACKING
    # ═══════════════════════════════════════════════════════════

    def initialize_progress(self, annotator_id: int, domain: str, total_samples: int) -> None:
        """
        Initialize progress tracking for an annotator-domain pair.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            total_samples: Total number of samples to annotate
        """
        key = self._progress_key(annotator_id, domain)

        progress_data = {
            "completed": 0,
            "total": total_samples,
            "last_updated": datetime.now().isoformat()
        }

        self.redis.hset(key, mapping=progress_data)
        logger.info(f"Initialized progress for annotator {annotator_id}, domain {domain}: 0/{total_samples}")

    def get_progress(self, annotator_id: int, domain: str) -> Tuple[int, int]:
        """
        Get progress for an annotator-domain pair.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Tuple of (completed_count, total_count)
        """
        key = self._progress_key(annotator_id, domain)
        progress = self.redis.hgetall(key)

        if not progress:
            return (0, 0)

        completed = int(progress.get("completed", 0))
        total = int(progress.get("total", 0))

        return (completed, total)

    def get_progress_percentage(self, annotator_id: int, domain: str) -> float:
        """
        Get progress percentage.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Progress percentage (0-100)
        """
        completed, total = self.get_progress(annotator_id, domain)

        if total == 0:
            return 0.0

        return (completed / total) * 100

    def get_all_progress(self) -> Dict[str, Dict[str, Tuple[int, int]]]:
        """
        Get progress for all annotator-domain pairs.

        Returns:
            Nested dictionary: {annotator_id: {domain: (completed, total)}}
        """
        progress_keys = self.redis.keys("progress:*")
        all_progress = {}

        for key in progress_keys:
            # Parse key: progress:{annotator_id}:{domain}
            parts = key.split(":")
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]

            if annotator_id not in all_progress:
                all_progress[annotator_id] = {}

            all_progress[annotator_id][domain] = self.get_progress(annotator_id, domain)

        return all_progress

    # ═══════════════════════════════════════════════════════════
    # PENDING SAMPLES
    # ═══════════════════════════════════════════════════════════

    def get_pending_samples(self, annotator_id: int, domain: str, all_sample_ids: List[str]) -> List[str]:
        """
        Get list of pending (not completed) sample IDs.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            all_sample_ids: List of all sample IDs in dataset

        Returns:
            List of pending sample IDs
        """
        completed = self.get_completed_samples(annotator_id, domain)
        pending = [sid for sid in all_sample_ids if sid not in completed]

        logger.debug(f"Found {len(pending)} pending samples for annotator {annotator_id}, domain {domain}")
        return pending

    # ═══════════════════════════════════════════════════════════
    # WORKER STATE MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def register_worker(self, annotator_id: int, domain: str, pid: int) -> None:
        """
        Register a worker as active.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            pid: Process ID
        """
        key = self._worker_key(annotator_id, domain)

        worker_data = {
            "status": "running",
            "pid": pid,
            "started_at": datetime.now().isoformat()
        }

        self.redis.hset(key, mapping=worker_data)
        logger.info(f"Registered worker for annotator {annotator_id}, domain {domain} (PID: {pid})")

    def update_worker_status(self, annotator_id: int, domain: str, status: str) -> None:
        """
        Update worker status.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            status: Worker status ('running', 'paused', 'stopped', 'error')
        """
        key = self._worker_key(annotator_id, domain)
        self.redis.hset(key, "status", status)
        logger.debug(f"Updated worker status to '{status}' for annotator {annotator_id}, domain {domain}")

    def get_worker_state(self, annotator_id: int, domain: str) -> Optional[Dict[str, str]]:
        """
        Get worker state.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Dictionary with worker state or None if not registered
        """
        key = self._worker_key(annotator_id, domain)
        state = self.redis.hgetall(key)

        return dict(state) if state else None

    def get_all_workers(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        """
        Get state of all workers.

        Returns:
            Nested dictionary: {annotator_id: {domain: worker_state}}
        """
        worker_keys = self.redis.keys("worker:*")
        all_workers = {}

        for key in worker_keys:
            # Parse key: worker:{annotator_id}:{domain}
            parts = key.split(":")
            if len(parts) != 3:
                continue

            annotator_id = int(parts[1])
            domain = parts[2]

            if annotator_id not in all_workers:
                all_workers[annotator_id] = {}

            all_workers[annotator_id][domain] = self.get_worker_state(annotator_id, domain)

        return all_workers

    def unregister_worker(self, annotator_id: int, domain: str) -> None:
        """
        Unregister a worker.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
        """
        key = self._worker_key(annotator_id, domain)
        self.redis.delete(key)
        logger.info(f"Unregistered worker for annotator {annotator_id}, domain {domain}")

    # ═══════════════════════════════════════════════════════════
    # SNAPSHOT MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def save_snapshot(self, run_id: str, output_dir: str = "checkpoints") -> str:
        """
        Export all checkpoint data to JSON file.

        Args:
            run_id: Unique identifier for this snapshot
            output_dir: Directory to save snapshot file

        Returns:
            Path to saved snapshot file
        """
        # Gather all checkpoint data
        snapshot_data = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "checkpoints": {},
            "progress": {},
            "workers": {}
        }

        # Get all checkpoint keys
        checkpoint_keys = self.redis.keys("checkpoint:*")
        for key in checkpoint_keys:
            completed_samples = list(self.redis.smembers(key))
            snapshot_data["checkpoints"][key] = completed_samples

        # Get all progress keys
        progress_keys = self.redis.keys("progress:*")
        for key in progress_keys:
            progress = self.redis.hgetall(key)
            snapshot_data["progress"][key] = dict(progress)

        # Get all worker keys
        worker_keys = self.redis.keys("worker:*")
        for key in worker_keys:
            worker_state = self.redis.hgetall(key)
            snapshot_data["workers"][key] = dict(worker_state)

        # Save to file
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        filename = f"checkpoint_snapshot_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = output_path / filename

        with open(file_path, 'w') as f:
            json.dump(snapshot_data, f, indent=2)

        logger.info(f"Saved checkpoint snapshot to {file_path}")
        return str(file_path)

    def restore_snapshot(self, snapshot_path: str) -> None:
        """
        Restore checkpoint data from JSON snapshot file.

        Args:
            snapshot_path: Path to snapshot file
        """
        with open(snapshot_path, 'r') as f:
            snapshot_data = json.load(f)

        # Use pipeline for efficient bulk operations
        pipe = self.redis.pipeline()

        # Restore checkpoints
        for key, completed_samples in snapshot_data.get("checkpoints", {}).items():
            if completed_samples:
                pipe.sadd(key, *completed_samples)

        # Restore progress
        for key, progress in snapshot_data.get("progress", {}).items():
            pipe.hset(key, mapping=progress)

        # Restore workers
        for key, worker_state in snapshot_data.get("workers", {}).items():
            pipe.hset(key, mapping=worker_state)

        # Execute all operations
        pipe.execute()

        logger.info(f"Restored checkpoint snapshot from {snapshot_path}")

    # ═══════════════════════════════════════════════════════════
    # CLEANUP OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def clear_domain(self, annotator_id: int, domain: str) -> None:
        """
        Clear all checkpoint data for a specific annotator-domain pair.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
        """
        checkpoint_key = self._checkpoint_key(annotator_id, domain)
        progress_key = self._progress_key(annotator_id, domain)
        worker_key = self._worker_key(annotator_id, domain)

        pipe = self.redis.pipeline()
        pipe.delete(checkpoint_key)
        pipe.delete(progress_key)
        pipe.delete(worker_key)
        pipe.execute()

        logger.info(f"Cleared checkpoint data for annotator {annotator_id}, domain {domain}")

    def clear_annotator(self, annotator_id: int) -> None:
        """
        Clear all checkpoint data for a specific annotator across all domains.

        Args:
            annotator_id: Annotator ID
        """
        patterns = [
            f"checkpoint:{annotator_id}:*",
            f"progress:{annotator_id}:*",
            f"worker:{annotator_id}:*"
        ]

        for pattern in patterns:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)

        logger.info(f"Cleared all checkpoint data for annotator {annotator_id}")

    def factory_reset(self) -> None:
        """
        Clear ALL checkpoint data (use with caution!).
        """
        patterns = ["checkpoint:*", "progress:*", "worker:*"]

        total_deleted = 0
        for pattern in patterns:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                total_deleted += len(keys)

        logger.warning(f"Factory reset completed: deleted {total_deleted} keys")

    # ═══════════════════════════════════════════════════════════
    # STATISTICS & REPORTING
    # ═══════════════════════════════════════════════════════════

    def get_summary(self) -> Dict[str, any]:
        """
        Get comprehensive summary of checkpoint system state.

        Returns:
            Dictionary with summary statistics
        """
        checkpoint_keys = self.redis.keys("checkpoint:*")
        progress_keys = self.redis.keys("progress:*")
        worker_keys = self.redis.keys("worker:*")

        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_checkpoints": len(checkpoint_keys),
            "total_progress_trackers": len(progress_keys),
            "total_workers": len(worker_keys),
            "total_completed_samples": 0,
            "by_annotator": {}
        }

        # Calculate total completed samples
        for key in checkpoint_keys:
            count = self.redis.scard(key)
            summary["total_completed_samples"] += count

        # Get progress by annotator
        all_progress = self.get_all_progress()
        for annotator_id, domains in all_progress.items():
            summary["by_annotator"][annotator_id] = {
                "domains": domains,
                "total_completed": sum(completed for completed, _ in domains.values()),
                "total_samples": sum(total for _, total in domains.values())
            }

        return summary

    def health_check(self) -> Dict[str, any]:
        """
        Perform health check on checkpoint system.

        Returns:
            Dictionary with health status
        """
        health = {
            "redis_connected": False,
            "timestamp": datetime.now().isoformat()
        }

        try:
            self.redis.ping()
            health["redis_connected"] = True

            # Get basic stats
            health["checkpoint_keys_count"] = len(self.redis.keys("checkpoint:*"))
            health["progress_keys_count"] = len(self.redis.keys("progress:*"))
            health["worker_keys_count"] = len(self.redis.keys("worker:*"))

        except Exception as e:
            health["error"] = str(e)

        return health
