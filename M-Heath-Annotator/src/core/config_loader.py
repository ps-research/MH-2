"""
Configuration loader with singleton pattern and Redis caching.
"""
import os
import yaml
import json
import redis
from pathlib import Path
from typing import Dict, Any, Optional
from threading import Lock
from datetime import datetime
import logging
from pydantic import ValidationError

from .models import (
    validate_config,
    AnnotatorsConfig,
    DomainsConfig,
    WorkersConfig,
    SettingsConfig
)


logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Singleton configuration loader with Redis caching and hot-reload support.

    This class loads YAML configuration files, validates them using Pydantic models,
    and caches them in Redis for fast access. Supports hot-reloading of configs.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls, config_dir: Optional[str] = None, redis_client: Optional[redis.Redis] = None):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_dir: Optional[str] = None, redis_client: Optional[redis.Redis] = None):
        """
        Initialize the configuration loader.

        Args:
            config_dir: Path to configuration directory (default: ./config)
            redis_client: Redis client instance (creates new if None)
        """
        # Only initialize once
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.config_dir = Path(config_dir or os.path.join(os.getcwd(), 'M-Heath-Annotator', 'config'))

        # Initialize Redis client
        if redis_client is None:
            # Load basic settings to get Redis config
            settings_path = self.config_dir / 'settings.yaml'
            if settings_path.exists():
                with open(settings_path, 'r') as f:
                    settings_dict = yaml.safe_load(f)
                    redis_config = settings_dict.get('redis', {})
            else:
                redis_config = {}

            self.redis_client = redis.Redis(
                host=redis_config.get('host', 'localhost'),
                port=redis_config.get('port', 6379),
                db=redis_config.get('db_broker', 0),
                password=redis_config.get('password'),
                decode_responses=True
            )
        else:
            self.redis_client = redis_client

        # Cache for validated config objects
        self._config_cache: Dict[str, Any] = {}
        self._file_mtimes: Dict[str, float] = {}

        self._initialized = True
        logger.info(f"ConfigLoader initialized with config_dir: {self.config_dir}")

    # ═══════════════════════════════════════════════════════════
    # CORE LOADING METHODS
    # ═══════════════════════════════════════════════════════════

    def _load_yaml_file(self, config_type: str) -> dict:
        """
        Load and parse YAML configuration file.

        Args:
            config_type: Type of config ('annotators', 'domains', 'workers', 'settings')

        Returns:
            Parsed YAML as dictionary

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        file_path = self.config_dir / f'{config_type}.yaml'

        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(file_path, 'r') as f:
            config_dict = yaml.safe_load(f)

        # Track file modification time
        self._file_mtimes[config_type] = file_path.stat().st_mtime

        logger.debug(f"Loaded YAML file: {file_path}")
        return config_dict

    def _save_to_redis(self, config_type: str, config_dict: dict) -> None:
        """
        Save configuration to Redis for caching.

        Args:
            config_type: Type of config
            config_dict: Configuration dictionary to save
        """
        # Save entire config as JSON
        redis_key = f"config:{config_type}:full"
        self.redis_client.set(redis_key, json.dumps(config_dict))

        # Save last updated timestamp
        timestamp_key = f"config:{config_type}:updated"
        self.redis_client.set(timestamp_key, datetime.now().isoformat())

        logger.debug(f"Saved {config_type} config to Redis")

    def _load_from_redis(self, config_type: str) -> Optional[dict]:
        """
        Load configuration from Redis cache.

        Args:
            config_type: Type of config

        Returns:
            Configuration dictionary or None if not cached
        """
        redis_key = f"config:{config_type}:full"
        cached_data = self.redis_client.get(redis_key)

        if cached_data:
            logger.debug(f"Loaded {config_type} config from Redis cache")
            return json.loads(cached_data)

        return None

    def _check_file_modified(self, config_type: str) -> bool:
        """
        Check if configuration file has been modified since last load.

        Args:
            config_type: Type of config

        Returns:
            True if file was modified, False otherwise
        """
        file_path = self.config_dir / f'{config_type}.yaml'

        if not file_path.exists():
            return False

        current_mtime = file_path.stat().st_mtime
        last_mtime = self._file_mtimes.get(config_type, 0)

        return current_mtime > last_mtime

    def load_config(self, config_type: str, force_reload: bool = False) -> Any:
        """
        Load and validate configuration with caching.

        Args:
            config_type: Type of config ('annotators', 'domains', 'workers', 'settings')
            force_reload: Force reload from file even if cached

        Returns:
            Validated Pydantic model instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValidationError: If config doesn't match schema
        """
        # Check if we need to reload
        if not force_reload and config_type in self._config_cache:
            # Check if file was modified
            if not self._check_file_modified(config_type):
                logger.debug(f"Using cached {config_type} config")
                return self._config_cache[config_type]

        # Try to load from Redis first
        if not force_reload:
            cached_dict = self._load_from_redis(config_type)
            if cached_dict and not self._check_file_modified(config_type):
                try:
                    validated_config = validate_config(config_type, cached_dict)
                    self._config_cache[config_type] = validated_config
                    return validated_config
                except ValidationError as e:
                    logger.warning(f"Redis cache validation failed for {config_type}: {e}")

        # Load from file
        config_dict = self._load_yaml_file(config_type)

        # Validate against schema
        try:
            validated_config = validate_config(config_type, config_dict)
        except ValidationError as e:
            logger.error(f"Validation failed for {config_type}: {e}")
            raise

        # Cache in memory and Redis
        self._config_cache[config_type] = validated_config
        self._save_to_redis(config_type, config_dict)

        logger.info(f"Loaded and validated {config_type} configuration")
        return validated_config

    def reload_config(self, config_type: str) -> Any:
        """
        Force reload configuration from file.

        Args:
            config_type: Type of config to reload

        Returns:
            Validated Pydantic model instance
        """
        logger.info(f"Force reloading {config_type} configuration")
        return self.load_config(config_type, force_reload=True)

    # ═══════════════════════════════════════════════════════════
    # CONVENIENCE METHODS
    # ═══════════════════════════════════════════════════════════

    def get_annotator_config(self, annotator_id: int) -> dict:
        """
        Get configuration for a specific annotator.

        Args:
            annotator_id: Annotator ID (1-5)

        Returns:
            Annotator configuration dictionary

        Raises:
            KeyError: If annotator_id doesn't exist
        """
        config: AnnotatorsConfig = self.load_config('annotators')

        if annotator_id not in config.annotators:
            raise KeyError(f"Annotator {annotator_id} not found in configuration")

        annotator = config.annotators[annotator_id]
        return annotator.dict()

    def get_domain_config(self, domain: str) -> dict:
        """
        Get configuration for a specific domain.

        Args:
            domain: Domain name ('urgency', 'therapeutic', etc.)

        Returns:
            Domain configuration dictionary

        Raises:
            KeyError: If domain doesn't exist
        """
        config: DomainsConfig = self.load_config('domains')

        if domain not in config.domains:
            raise KeyError(f"Domain '{domain}' not found in configuration")

        domain_config = config.domains[domain]
        return domain_config.dict()

    def get_worker_config(self, annotator_id: int, domain: str) -> dict:
        """
        Get worker configuration for a specific annotator-domain pair.

        Args:
            annotator_id: Annotator ID (1-5)
            domain: Domain name

        Returns:
            Worker configuration dictionary

        Raises:
            KeyError: If configuration doesn't exist
        """
        config: WorkersConfig = self.load_config('workers')

        pool_name = f"annotator_{annotator_id}"
        if pool_name not in config.worker_pools:
            raise KeyError(f"Worker pool '{pool_name}' not found in configuration")

        pool = config.worker_pools[pool_name]
        if domain not in pool.domains:
            raise KeyError(f"Domain '{domain}' not found for worker pool '{pool_name}'")

        worker_config = pool.domains[domain]
        return worker_config.dict()

    def get_settings_config(self) -> dict:
        """
        Get application settings configuration.

        Returns:
            Settings configuration dictionary
        """
        config: SettingsConfig = self.load_config('settings')
        return config.dict()

    def get_all_annotator_ids(self) -> list[int]:
        """
        Get list of all configured annotator IDs.

        Returns:
            List of annotator IDs
        """
        config: AnnotatorsConfig = self.load_config('annotators')
        return list(config.annotators.keys())

    def get_all_domain_names(self) -> list[str]:
        """
        Get list of all configured domain names.

        Returns:
            List of domain names
        """
        config: DomainsConfig = self.load_config('domains')
        return list(config.domains.keys())

    def get_enabled_workers(self, annotator_id: int) -> dict[str, dict]:
        """
        Get all enabled workers for an annotator.

        Args:
            annotator_id: Annotator ID

        Returns:
            Dictionary mapping domain names to worker configs (only enabled ones)
        """
        config: WorkersConfig = self.load_config('workers')

        pool_name = f"annotator_{annotator_id}"
        if pool_name not in config.worker_pools:
            return {}

        pool = config.worker_pools[pool_name]
        enabled_workers = {}

        for domain, worker_config in pool.domains.items():
            if worker_config.enabled:
                enabled_workers[domain] = worker_config.dict()

        return enabled_workers

    # ═══════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════

    def validate_all_configs(self) -> Dict[str, bool]:
        """
        Validate all configuration files.

        Returns:
            Dictionary mapping config types to validation status
        """
        results = {}
        config_types = ['annotators', 'domains', 'workers', 'settings']

        for config_type in config_types:
            try:
                self.load_config(config_type)
                results[config_type] = True
                logger.info(f"✓ {config_type} configuration valid")
            except Exception as e:
                results[config_type] = False
                logger.error(f"✗ {config_type} configuration invalid: {e}")

        return results

    def clear_cache(self) -> None:
        """Clear in-memory configuration cache."""
        self._config_cache.clear()
        logger.info("Configuration cache cleared")

    def clear_redis_cache(self, config_type: Optional[str] = None) -> None:
        """
        Clear Redis configuration cache.

        Args:
            config_type: Specific config type to clear, or None for all
        """
        if config_type:
            pattern = f"config:{config_type}:*"
        else:
            pattern = "config:*"

        keys = self.redis_client.keys(pattern)
        if keys:
            self.redis_client.delete(*keys)
            logger.info(f"Cleared Redis cache for pattern: {pattern}")

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on configuration system.

        Returns:
            Dictionary with health status information
        """
        health = {
            'config_dir_exists': self.config_dir.exists(),
            'redis_connected': False,
            'configs_valid': {},
            'timestamp': datetime.now().isoformat()
        }

        # Check Redis connection
        try:
            self.redis_client.ping()
            health['redis_connected'] = True
        except Exception as e:
            health['redis_error'] = str(e)

        # Check all configs
        health['configs_valid'] = self.validate_all_configs()

        return health


# ═══════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════════

def get_config_loader(config_dir: Optional[str] = None, redis_client: Optional[redis.Redis] = None) -> ConfigLoader:
    """
    Get or create ConfigLoader singleton instance.

    Args:
        config_dir: Path to configuration directory
        redis_client: Redis client instance

    Returns:
        ConfigLoader instance
    """
    return ConfigLoader(config_dir=config_dir, redis_client=redis_client)
