"""
Source data loader for mental health dataset with Redis caching.
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd
import redis


logger = logging.getLogger(__name__)


class SourceDataLoader:
    """
    Loads M-Help dataset from local Excel file with Redis caching.

    Features:
    - Load entire dataset into memory
    - Cache samples in Redis for fast access
    - Validate source file structure
    - Batch loading support
    """

    def __init__(
        self,
        excel_path: str,
        redis_client: redis.Redis,
        id_column: str = "Sample_ID",
        text_column: str = "Text"
    ):
        """
        Initialize source data loader.

        Args:
            excel_path: Path to source Excel file
            redis_client: Redis client for caching
            id_column: Name of ID column
            text_column: Name of text column
        """
        self.excel_path = Path(excel_path)
        self.redis = redis_client
        self.id_column = id_column
        self.text_column = text_column

        # In-memory cache
        self._samples: Optional[List[Dict]] = None
        self._sample_ids: Optional[List[str]] = None

        logger.info(f"SourceDataLoader initialized with file: {self.excel_path}")

    def validate_source_file(self) -> bool:
        """
        Validate that source file exists and has required columns.

        Returns:
            True if valid, False otherwise

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If required columns missing
        """
        if not self.excel_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.excel_path}")

        # Read first few rows to check columns
        try:
            df = pd.read_excel(self.excel_path, nrows=5)

            # Check required columns
            if self.id_column not in df.columns:
                raise ValueError(f"Missing required column: {self.id_column}")

            if self.text_column not in df.columns:
                raise ValueError(f"Missing required column: {self.text_column}")

            logger.info("Source file validation passed")
            return True

        except Exception as e:
            logger.error(f"Source file validation failed: {e}")
            raise

    def load_all_samples(self, force_reload: bool = False) -> List[Dict]:
        """
        Load all samples from Excel file.

        Args:
            force_reload: Force reload from file (ignore cache)

        Returns:
            List of sample dictionaries
        """
        # Check in-memory cache first
        if not force_reload and self._samples is not None:
            logger.debug(f"Returning {len(self._samples)} samples from memory cache")
            return self._samples

        # Check Redis cache
        if not force_reload:
            cached_ids = self.redis.lrange('source:sample_ids', 0, -1)
            if cached_ids:
                logger.info(f"Loading {len(cached_ids)} samples from Redis cache")
                samples = []
                for sample_id in cached_ids:
                    sample_data = self.redis.hgetall(f'source:sample:{sample_id}')
                    if sample_data:
                        # Convert Redis hash to dict with proper types
                        sample = {
                            'sample_id': sample_data.get('sample_id', sample_id),
                            'text': sample_data.get('text', ''),
                            'metadata': json.loads(sample_data.get('metadata', '{}'))
                        }
                        samples.append(sample)

                if len(samples) == len(cached_ids):
                    self._samples = samples
                    self._sample_ids = cached_ids
                    return samples

        # Load from Excel file
        logger.info(f"Loading samples from Excel file: {self.excel_path}")

        try:
            df = pd.read_excel(self.excel_path)

            # Validate columns
            if self.id_column not in df.columns:
                raise ValueError(f"Missing column: {self.id_column}")
            if self.text_column not in df.columns:
                raise ValueError(f"Missing column: {self.text_column}")

            # Convert to list of dicts
            samples = []
            sample_ids = []

            for idx, row in df.iterrows():
                sample_id = str(row[self.id_column])
                text = str(row[self.text_column])

                # Collect metadata from other columns
                metadata = {}
                for col in df.columns:
                    if col not in [self.id_column, self.text_column]:
                        metadata[col] = row[col]

                sample = {
                    'sample_id': sample_id,
                    'text': text,
                    'metadata': metadata
                }

                samples.append(sample)
                sample_ids.append(sample_id)

            logger.info(f"Loaded {len(samples)} samples from Excel file")

            # Cache in memory
            self._samples = samples
            self._sample_ids = sample_ids

            # Cache in Redis
            self._cache_in_redis(samples, sample_ids)

            return samples

        except Exception as e:
            logger.error(f"Error loading samples from Excel: {e}")
            raise

    def _cache_in_redis(self, samples: List[Dict], sample_ids: List[str]) -> None:
        """Cache samples in Redis with 24-hour TTL."""
        try:
            pipe = self.redis.pipeline()

            # Store sample IDs list
            pipe.delete('source:sample_ids')
            if sample_ids:
                pipe.rpush('source:sample_ids', *sample_ids)
                pipe.expire('source:sample_ids', 86400)  # 24 hours

            # Store each sample as hash
            for sample in samples:
                key = f"source:sample:{sample['sample_id']}"
                pipe.hset(key, mapping={
                    'sample_id': sample['sample_id'],
                    'text': sample['text'],
                    'metadata': json.dumps(sample['metadata'])
                })
                pipe.expire(key, 86400)  # 24 hours

            pipe.execute()
            logger.info(f"Cached {len(samples)} samples in Redis")

        except Exception as e:
            logger.warning(f"Error caching samples in Redis: {e}")

    def load_sample_batch(self, start_idx: int, batch_size: int) -> List[Dict]:
        """
        Load batch of samples.

        Args:
            start_idx: Starting index
            batch_size: Number of samples to load

        Returns:
            List of sample dictionaries
        """
        all_samples = self.load_all_samples()
        end_idx = min(start_idx + batch_size, len(all_samples))

        batch = all_samples[start_idx:end_idx]
        logger.debug(f"Loaded batch: {len(batch)} samples (indices {start_idx}-{end_idx})")

        return batch

    def get_sample_by_id(self, sample_id: str) -> Optional[Dict]:
        """
        Get single sample by ID.

        Args:
            sample_id: Sample identifier

        Returns:
            Sample dictionary or None if not found
        """
        # Try Redis cache first
        key = f"source:sample:{sample_id}"
        cached_data = self.redis.hgetall(key)

        if cached_data:
            return {
                'sample_id': cached_data.get('sample_id', sample_id),
                'text': cached_data.get('text', ''),
                'metadata': json.loads(cached_data.get('metadata', '{}'))
            }

        # Search in memory or load all samples
        all_samples = self.load_all_samples()

        for sample in all_samples:
            if sample['sample_id'] == sample_id:
                return sample

        logger.warning(f"Sample not found: {sample_id}")
        return None

    def get_total_count(self) -> int:
        """
        Get total number of samples.

        Returns:
            Total sample count
        """
        # Try Redis cache first
        count = self.redis.llen('source:sample_ids')
        if count > 0:
            return count

        # Load from file
        all_samples = self.load_all_samples()
        return len(all_samples)

    def get_sample_ids(self) -> List[str]:
        """
        Get list of all sample IDs.

        Returns:
            List of sample IDs
        """
        # Try Redis cache first
        cached_ids = self.redis.lrange('source:sample_ids', 0, -1)
        if cached_ids:
            return cached_ids

        # Load from file
        all_samples = self.load_all_samples()
        return [s['sample_id'] for s in all_samples]

    def clear_cache(self) -> None:
        """Clear Redis cache."""
        try:
            # Delete sample IDs list
            self.redis.delete('source:sample_ids')

            # Delete all sample hashes
            pattern = 'source:sample:*'
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)

            logger.info("Cleared source data cache from Redis")

        except Exception as e:
            logger.warning(f"Error clearing cache: {e}")

        # Clear memory cache
        self._samples = None
        self._sample_ids = None

    def reload(self) -> List[Dict]:
        """
        Force reload samples from Excel file.

        Returns:
            List of samples
        """
        self.clear_cache()
        return self.load_all_samples(force_reload=True)

    def get_statistics(self) -> Dict:
        """
        Get dataset statistics.

        Returns:
            Dictionary with statistics
        """
        samples = self.load_all_samples()

        if not samples:
            return {
                'total_samples': 0,
                'avg_text_length': 0,
                'min_text_length': 0,
                'max_text_length': 0
            }

        text_lengths = [len(s['text']) for s in samples]

        return {
            'total_samples': len(samples),
            'avg_text_length': sum(text_lengths) / len(text_lengths),
            'min_text_length': min(text_lengths),
            'max_text_length': max(text_lengths),
            'unique_ids': len(set(s['sample_id'] for s in samples))
        }

    def export_to_csv(self, output_path: str) -> None:
        """
        Export samples to CSV file.

        Args:
            output_path: Output CSV file path
        """
        samples = self.load_all_samples()

        # Convert to DataFrame
        data = []
        for sample in samples:
            row = {
                'sample_id': sample['sample_id'],
                'text': sample['text']
            }
            # Add metadata columns
            row.update(sample.get('metadata', {}))
            data.append(row)

        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False)

        logger.info(f"Exported {len(samples)} samples to {output_path}")
