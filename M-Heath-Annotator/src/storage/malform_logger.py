"""
Malform logger with dual storage (Redis + JSON files).
"""
import json
import time
import threading
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import redis
import pandas as pd

from ..models.annotation import MalformError


logger = logging.getLogger(__name__)


class MalformLogger:
    """
    Logs malformed responses with dual storage.

    Features:
    - Real-time Redis storage for dashboard
    - Persistent JSON file storage
    - Auto-sync every 50 errors or 5 minutes
    - Thread-safe operations
    - Export to Excel for analysis
    """

    def __init__(
        self,
        log_dir: str,
        redis_client: redis.Redis,
        auto_sync_count: int = 50,
        auto_sync_interval: int = 300
    ):
        """
        Initialize malform logger.

        Args:
            log_dir: Directory for JSON log files
            redis_client: Redis client
            auto_sync_count: Sync after this many errors
            auto_sync_interval: Sync interval in seconds
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.redis = redis_client
        self.auto_sync_count = auto_sync_count
        self.auto_sync_interval = auto_sync_interval

        # Thread safety
        self._lock = threading.Lock()
        self._sync_counters: Dict[str, int] = {}  # {worker_key: count}
        self._last_sync_times: Dict[str, float] = {}  # {worker_key: timestamp}

        logger.info(f"MalformLogger initialized: {self.log_dir}")

    def _get_worker_key(self, annotator_id: int, domain: str) -> str:
        """Get unique key for worker."""
        return f"{annotator_id}_{domain}"

    def _get_file_path(self, annotator_id: int, domain: str) -> Path:
        """Get JSON log file path."""
        filename = f"annotator_{annotator_id}_{domain}_malforms.json"
        return self.log_dir / filename

    def _get_redis_key(self, annotator_id: int, domain: str, sample_id: str) -> str:
        """Get Redis key for malform error."""
        return f"malform:{annotator_id}:{domain}:{sample_id}"

    def _get_count_key(self, annotator_id: int, domain: str) -> str:
        """Get Redis sorted set key for malform counts."""
        return f"malform_count:{annotator_id}:{domain}"

    def log_error(
        self,
        annotator_id: int,
        domain: str,
        sample_id: str,
        error_data: Dict
    ) -> None:
        """
        Log malformed response error.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            sample_id: Sample identifier
            error_data: Error data dictionary (should contain all fields for MalformError)
        """
        with self._lock:
            try:
                # Create MalformError model
                malform_error = MalformError(
                    sample_id=sample_id,
                    domain=domain,
                    annotator_id=annotator_id,
                    sample_text=error_data.get('sample_text', ''),
                    raw_response=error_data.get('raw_response', ''),
                    parsing_error=error_data.get('parsing_error'),
                    validity_error=error_data.get('validity_error'),
                    retry_count=error_data.get('retry_count', 0),
                    task_id=error_data.get('task_id')
                )

                # Store in Redis
                self._store_in_redis(annotator_id, domain, sample_id, malform_error)

                # Update sync counter
                worker_key = self._get_worker_key(annotator_id, domain)
                self._sync_counters[worker_key] = self._sync_counters.get(worker_key, 0) + 1

                # Check if auto-sync needed
                should_sync = False

                # Check count threshold
                if self._sync_counters[worker_key] >= self.auto_sync_count:
                    should_sync = True

                # Check time threshold
                last_sync = self._last_sync_times.get(worker_key, 0)
                if time.time() - last_sync >= self.auto_sync_interval:
                    should_sync = True

                # Perform sync if needed
                if should_sync:
                    self._sync_to_file(annotator_id, domain)

                logger.debug(f"Logged malform error: {sample_id} for {worker_key}")

            except Exception as e:
                logger.error(f"Error logging malform: {e}")

    def _store_in_redis(
        self,
        annotator_id: int,
        domain: str,
        sample_id: str,
        malform_error: MalformError
    ) -> None:
        """Store malform error in Redis."""
        redis_key = self._get_redis_key(annotator_id, domain, sample_id)
        count_key = self._get_count_key(annotator_id, domain)

        # Store as Redis hash
        error_dict = malform_error.to_dict()

        pipe = self.redis.pipeline()
        pipe.hset(redis_key, mapping=error_dict)
        pipe.expire(redis_key, 604800)  # 7 days

        # Add to sorted set for counting (score = timestamp)
        timestamp_score = time.time()
        pipe.zadd(count_key, {sample_id: timestamp_score})
        pipe.expire(count_key, 604800)  # 7 days

        pipe.execute()

    def _sync_to_file(self, annotator_id: int, domain: str) -> None:
        """Sync Redis data to JSON file."""
        try:
            file_path = self._get_file_path(annotator_id, domain)

            # Load existing file if it exists
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {
                    'annotator_id': annotator_id,
                    'domain': domain,
                    'created_at': datetime.now().isoformat(),
                    'last_updated': datetime.now().isoformat(),
                    'malforms': {}
                }

            # Get all malforms from Redis
            pattern = f"malform:{annotator_id}:{domain}:*"
            keys = self.redis.keys(pattern)

            for key in keys:
                error_data = self.redis.hgetall(key)
                if error_data:
                    sample_id = error_data.get('sample_id', key.split(':')[-1])
                    data['malforms'][sample_id] = error_data

            # Update metadata
            data['last_updated'] = datetime.now().isoformat()
            data['total_malforms'] = len(data['malforms'])

            # Write to file
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)

            # Reset sync counter
            worker_key = self._get_worker_key(annotator_id, domain)
            self._sync_counters[worker_key] = 0
            self._last_sync_times[worker_key] = time.time()

            logger.info(f"Synced {len(data['malforms'])} malforms to {file_path.name}")

        except Exception as e:
            logger.error(f"Error syncing to file: {e}")

    def get_malforms(self, annotator_id: int, domain: str) -> List[Dict]:
        """
        Get all malform errors for worker.

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            List of malform error dictionaries
        """
        malforms = []

        # Get from Redis
        pattern = f"malform:{annotator_id}:{domain}:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            error_data = self.redis.hgetall(key)
            if error_data:
                malforms.append(error_data)

        logger.debug(f"Retrieved {len(malforms)} malforms for {annotator_id}/{domain}")
        return malforms

    def get_summary(self, annotator_id: int) -> Dict:
        """
        Get summary of malforms by domain for annotator.

        Args:
            annotator_id: Annotator ID

        Returns:
            Dictionary with counts by domain
        """
        summary = {
            'annotator_id': annotator_id,
            'total_malforms': 0,
            'by_domain': {}
        }

        domains = ['urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal']

        for domain in domains:
            count_key = self._get_count_key(annotator_id, domain)
            count = self.redis.zcard(count_key)

            summary['by_domain'][domain] = count
            summary['total_malforms'] += count

        return summary

    def get_malform_by_sample(
        self,
        annotator_id: int,
        domain: str,
        sample_id: str
    ) -> Optional[Dict]:
        """
        Get malform error for specific sample.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
            sample_id: Sample identifier

        Returns:
            Malform error dictionary or None
        """
        redis_key = self._get_redis_key(annotator_id, domain, sample_id)
        error_data = self.redis.hgetall(redis_key)

        return dict(error_data) if error_data else None

    def export_all_to_excel(self, output_path: str) -> None:
        """
        Export all malforms to consolidated Excel file.

        Args:
            output_path: Output Excel file path
        """
        try:
            all_malforms = []

            # Collect from all JSON files
            for json_file in self.log_dir.glob("*.json"):
                with open(json_file, 'r') as f:
                    data = json.load(f)

                    annotator_id = data.get('annotator_id')
                    domain = data.get('domain')

                    for sample_id, malform in data.get('malforms', {}).items():
                        row = {
                            'Annotator_ID': annotator_id,
                            'Domain': domain,
                            'Sample_ID': sample_id,
                            'Timestamp': malform.get('timestamp', ''),
                            'Sample_Text': malform.get('sample_text', '')[:200],
                            'Raw_Response': malform.get('raw_response', '')[:200],
                            'Parsing_Error': malform.get('parsing_error', ''),
                            'Validity_Error': malform.get('validity_error', ''),
                            'Retry_Count': malform.get('retry_count', 0),
                            'Task_ID': malform.get('task_id', '')
                        }
                        all_malforms.append(row)

            # Create DataFrame and export
            if all_malforms:
                df = pd.DataFrame(all_malforms)
                df.to_excel(output_path, index=False, engine='openpyxl')
                logger.info(f"Exported {len(all_malforms)} malforms to {output_path}")
            else:
                logger.warning("No malforms found to export")

        except Exception as e:
            logger.error(f"Error exporting to Excel: {e}")
            raise

    def load_from_json(self, file_path: str) -> None:
        """
        Load malforms from JSON file and restore to Redis.

        Args:
            file_path: Path to JSON file
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            annotator_id = data.get('annotator_id')
            domain = data.get('domain')

            if not annotator_id or not domain:
                raise ValueError("Invalid JSON file: missing annotator_id or domain")

            # Restore to Redis
            for sample_id, malform_data in data.get('malforms', {}).items():
                malform_error = MalformError(
                    sample_id=sample_id,
                    domain=domain,
                    annotator_id=annotator_id,
                    sample_text=malform_data.get('sample_text', ''),
                    raw_response=malform_data.get('raw_response', ''),
                    parsing_error=malform_data.get('parsing_error'),
                    validity_error=malform_data.get('validity_error'),
                    retry_count=int(malform_data.get('retry_count', 0)),
                    task_id=malform_data.get('task_id')
                )

                self._store_in_redis(annotator_id, domain, sample_id, malform_error)

            logger.info(f"Loaded {len(data.get('malforms', {}))} malforms from {file_path}")

        except Exception as e:
            logger.error(f"Error loading from JSON: {e}")
            raise

    def force_sync(self, annotator_id: int, domain: str) -> None:
        """
        Force sync to JSON file.

        Args:
            annotator_id: Annotator ID
            domain: Domain name
        """
        with self._lock:
            self._sync_to_file(annotator_id, domain)

    def force_sync_all(self) -> None:
        """Force sync all pending malforms to JSON files."""
        with self._lock:
            # Find all unique worker combinations
            pattern = "malform:*"
            keys = self.redis.keys(pattern)

            workers = set()
            for key in keys:
                parts = key.split(':')
                if len(parts) >= 3:
                    annotator_id = int(parts[1])
                    domain = parts[2]
                    workers.add((annotator_id, domain))

            # Sync each worker
            for annotator_id, domain in workers:
                self._sync_to_file(annotator_id, domain)

        logger.info(f"Forced sync for {len(workers)} workers")

    def clear_malforms(self, annotator_id: int, domain: str) -> int:
        """
        Clear malforms for worker (Redis only).

        Args:
            annotator_id: Annotator ID
            domain: Domain name

        Returns:
            Number of malforms cleared
        """
        pattern = f"malform:{annotator_id}:{domain}:*"
        keys = self.redis.keys(pattern)

        if keys:
            count = len(keys)
            self.redis.delete(*keys)

            # Clear sorted set
            count_key = self._get_count_key(annotator_id, domain)
            self.redis.delete(count_key)

            logger.info(f"Cleared {count} malforms for {annotator_id}/{domain}")
            return count

        return 0

    def get_statistics(self) -> Dict:
        """
        Get overall malform statistics.

        Returns:
            Dictionary with statistics
        """
        stats = {
            'total_malforms': 0,
            'by_annotator': {},
            'by_domain': {},
            'by_error_type': {
                'parsing': 0,
                'validity': 0
            }
        }

        # Scan all malform keys
        pattern = "malform:*"
        keys = self.redis.keys(pattern)

        for key in keys:
            error_data = self.redis.hgetall(key)
            if not error_data:
                continue

            stats['total_malforms'] += 1

            # By annotator
            annotator_id = int(error_data.get('annotator_id', 0))
            stats['by_annotator'][annotator_id] = stats['by_annotator'].get(annotator_id, 0) + 1

            # By domain
            domain = error_data.get('domain', 'unknown')
            stats['by_domain'][domain] = stats['by_domain'].get(domain, 0) + 1

            # By error type
            if error_data.get('parsing_error'):
                stats['by_error_type']['parsing'] += 1
            elif error_data.get('validity_error'):
                stats['by_error_type']['validity'] += 1

        return stats
