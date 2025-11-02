# Mental Health Annotation System - Distributed Architecture

A distributed, fault-tolerant mental health dataset annotation system using **Celery + Redis** for coordinating AI-powered annotations across 6 clinical domains.

---

## 🎯 Overview

This system enables **5 annotators** to independently annotate mental health text samples across **6 clinical assessment domains** using Google's Gemini AI, with **30 parallel worker queues** for maximum throughput.

### Key Features

✅ **Distributed Processing** - Celery workers with Redis message broker
✅ **Fault Tolerance** - Redis checkpointing with crash recovery
✅ **YAML Configuration** - Hot-reloadable configs with Pydantic validation
✅ **Response Validation** - Domain-specific parsers with error tracking
✅ **Real-time Monitoring** - Flower web UI + Redis Commander
✅ **Atomic Operations** - Redis transactions for consistency
✅ **Rate Limit Handling** - Automatic retry with exponential backoff

---

## 📐 Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    MENTAL HEALTH ANNOTATOR                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │   Annotator  │────▶│    Celery    │────▶│    Redis    │ │
│  │   Workers    │     │    Broker    │     │  Database   │ │
│  │   (5 × 6)    │◀────│   (Queue)    │◀────│ (Checkpoint)│ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│         │                     │                     │        │
│         │                     ▼                     ▼        │
│         │              ┌──────────────┐     ┌─────────────┐ │
│         │              │    Flower    │     │   Config    │ │
│         │              │  Monitoring  │     │   Loader    │ │
│         │              └──────────────┘     └─────────────┘ │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                           │
│  │   Gemini AI  │                                           │
│  │   (Google)   │                                           │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

### Queue Architecture

**30 Dedicated Queues** (5 annotators × 6 domains):

```
Annotator 1:                    Annotator 2:
  ├─ annotator_1_urgency          ├─ annotator_2_urgency
  ├─ annotator_1_therapeutic      ├─ annotator_2_therapeutic
  ├─ annotator_1_intensity        ├─ annotator_2_intensity
  ├─ annotator_1_adjunct          ├─ annotator_2_adjunct
  ├─ annotator_1_modality         ├─ annotator_2_modality
  └─ annotator_1_redressal        └─ annotator_2_redressal

... (Annotators 3, 4, 5 follow same pattern)
```

### Redis Key Schema

```
checkpoint:{annotator_id}:{domain}     → Set of completed sample IDs
progress:{annotator_id}:{domain}       → Hash {completed, total, last_updated}
worker:{annotator_id}:{domain}         → Hash {status, pid, started_at}
config:{type}:full                     → JSON config cache
config:{type}:updated                  → Last update timestamp
error:{task_id}                        → Error details hash
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Google Gemini API keys

### 2. Installation

```bash
# Clone repository
cd M-Heath-Annotator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env and add your API keys
```

### 3. Start Infrastructure

```bash
# Start Redis + Flower
docker-compose up -d

# Verify services
docker-compose ps
```

**Access Points:**
- Flower UI: http://localhost:5555 (admin/admin)
- Redis Commander: http://localhost:8081

### 4. Configuration

Edit YAML files in `config/`:

```bash
config/
├── annotators.yaml   # API keys, rate limits
├── domains.yaml      # Prompt templates, validation rules
├── workers.yaml      # Queue assignments, concurrency
└── settings.yaml     # Redis, Celery, logging
```

### 5. Validate Configuration

```python
from src.core.config_loader import get_config_loader

loader = get_config_loader()
health = loader.health_check()
print(health)
# {'config_dir_exists': True, 'redis_connected': True, 'configs_valid': {...}}
```

---

## 📚 Core Components

### 1. Configuration System (`src/core/config_loader.py`)

**Singleton pattern** with YAML loading, Pydantic validation, and Redis caching.

```python
from src.core.config_loader import get_config_loader

loader = get_config_loader()

# Get annotator config
annotator = loader.get_annotator_config(annotator_id=1)
# Returns: {'name': '...', 'api_key': '...', 'rate_limit': 60}

# Get domain config
domain = loader.get_domain_config('urgency')
# Returns: {'name': '...', 'prompt_template': '...', 'validation': {...}}

# Hot reload
loader.reload_config('domains')
```

**Key Methods:**
- `get_annotator_config(annotator_id)` - Get annotator settings
- `get_domain_config(domain)` - Get domain prompt + validation
- `get_worker_config(annotator_id, domain)` - Get worker settings
- `reload_config(type)` - Force reload from file
- `health_check()` - System health status

### 2. Checkpoint Manager (`src/core/checkpoint.py`)

**Redis-based** checkpoint system with atomic operations.

```python
from src.core.checkpoint import RedisCheckpointManager
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
checkpoint = RedisCheckpointManager(redis_client)

# Check if sample completed
is_done = checkpoint.is_completed(annotator_id=1, domain='urgency', sample_id='ID-123')

# Mark sample as completed
checkpoint.mark_completed(annotator_id=1, domain='urgency', sample_id='ID-123')

# Get progress
completed, total = checkpoint.get_progress(annotator_id=1, domain='urgency')
print(f"Progress: {completed}/{total} ({completed/total*100:.1f}%)")

# Get pending samples
pending = checkpoint.get_pending_samples(
    annotator_id=1,
    domain='urgency',
    all_sample_ids=['ID-1', 'ID-2', 'ID-3']
)

# Save snapshot
snapshot_path = checkpoint.save_snapshot(run_id='run_001')

# Factory reset (CAUTION!)
checkpoint.factory_reset()
```

**Key Methods:**
- `is_completed(annotator_id, domain, sample_id)` - Check completion
- `mark_completed(annotator_id, domain, sample_id)` - Mark done
- `get_progress(annotator_id, domain)` - Get (completed, total)
- `get_pending_samples(...)` - Get unfinished samples
- `save_snapshot(run_id)` - Export to JSON
- `restore_snapshot(path)` - Import from JSON

### 3. Response Validators (`src/utils/validators.py`)

**Domain-specific parsers** with regex extraction and validation.

```python
from src.utils.validators import validate_response

# Validate urgency response
response = "Analysis... <<LEVEL_3>>"
result = validate_response('urgency', response)

if result.is_valid:
    print(f"Label: {result.label}")
else:
    print(f"Error: {result.parsing_error or result.validity_error}")
```

**Supported Domains:**
- `urgency` - LEVEL_0 to LEVEL_4
- `therapeutic` - TA-1 to TA-9 (multi-label)
- `intensity` - INT-1 to INT-5
- `adjunct` - ADJ-1 to ADJ-8 or NONE (multi-label)
- `modality` - MOD-1 to MOD-6 (multi-label)
- `redressal` - JSON array of strings

### 4. Celery Application (`src/core/celery_app.py`)

**Custom task base class** with automatic retry on rate limits.

```python
from src.core.celery_app import app, AnnotationTask

@app.task(base=AnnotationTask, bind=True)
def annotate_sample(self, annotator_id, domain, sample_id, text):
    # Your annotation logic here
    pass

# Get health status
from src.core.celery_app import get_celery_health
health = get_celery_health()
print(health)
# {'broker_connected': True, 'active_workers': 5, 'total_queues': 30}
```

---

## 📋 Configuration Reference

### Annotators (`config/annotators.yaml`)

```yaml
annotators:
  1:
    name: Annotator One
    api_key: YOUR_API_KEY
    email: annotator1@example.com
    rate_limit: 60        # Requests per minute
    max_retries: 3
```

### Domains (`config/domains.yaml`)

```yaml
domains:
  urgency:
    name: Urgency Level Assessment
    prompt_template: |
      Prompt text with {text} placeholder...
    validation:
      pattern: 'LEVEL[_\s]*([0-4])'
      type: single
      valid_codes:
        - LEVEL_0
        - LEVEL_1
        - LEVEL_2
        - LEVEL_3
        - LEVEL_4
```

### Workers (`config/workers.yaml`)

```yaml
worker_pools:
  annotator_1:
    domains:
      urgency:
        enabled: true
        concurrency: 1
        queue: annotator_1_urgency
        sample_limit: null    # Process all
        batch_size: 1
```

### Settings (`config/settings.yaml`)

```yaml
redis:
  host: localhost
  port: 6379
  db_broker: 0
  db_backend: 1

celery:
  task_time_limit: 300
  task_soft_time_limit: 240
  worker_prefetch_multiplier: 1

logging:
  level: INFO
  file: logs/annotator.log
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_core/test_validators.py

# Run specific test
pytest tests/test_core/test_validators.py::TestUrgencyParser::test_valid_urgency_level_0
```

**Test Coverage:**
- ✅ Response validators (all 6 domains)
- ✅ Pydantic models validation
- ✅ Configuration loading
- ✅ Checkpoint operations

---

## 🔧 Development Workflow

### Starting Workers

```bash
# Start a single worker for annotator 1, urgency domain
celery -A src.core.celery_app worker \
  --loglevel=info \
  --queues=annotator_1_urgency \
  --concurrency=1 \
  --hostname=worker_1_urgency@%h

# Start all workers for annotator 1
celery -A src.core.celery_app worker \
  --loglevel=info \
  --queues=annotator_1_urgency,annotator_1_therapeutic,annotator_1_intensity,annotator_1_adjunct,annotator_1_modality,annotator_1_redressal \
  --concurrency=6 \
  --hostname=worker_annotator_1@%h
```

### Monitoring

```bash
# Check Redis keys
redis-cli keys "checkpoint:*"
redis-cli keys "progress:*"

# Get progress for annotator 1, urgency
redis-cli hgetall progress:1:urgency

# Get completed samples
redis-cli smembers checkpoint:1:urgency

# Check Celery tasks
celery -A src.core.celery_app inspect active
celery -A src.core.celery_app inspect stats
```

### Debugging

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check config health
from src.core.config_loader import get_config_loader
loader = get_config_loader()
print(loader.health_check())

# Check checkpoint health
from src.core.checkpoint import RedisCheckpointManager
import redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
checkpoint = RedisCheckpointManager(redis_client)
print(checkpoint.health_check())

# Get system summary
summary = checkpoint.get_summary()
print(summary)
```

---

## 📊 Monitoring & Observability

### Flower Dashboard

Access at http://localhost:5555 (credentials: admin/admin)

**Features:**
- Task history and status
- Worker performance metrics
- Queue lengths
- Task execution times
- Retry statistics

### Redis Commander

Access at http://localhost:8081

**Features:**
- Browse all Redis keys
- View set members (completed samples)
- Inspect hash values (progress, worker state)
- Export data

### System Health Check

```python
from src.core.config_loader import get_config_loader
from src.core.checkpoint import RedisCheckpointManager
from src.core.celery_app import get_celery_health
import redis

# Config health
config_health = get_config_loader().health_check()

# Checkpoint health
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
checkpoint_health = RedisCheckpointManager(redis_client).health_check()

# Celery health
celery_health = get_celery_health()

print("=== SYSTEM HEALTH ===")
print(f"Config: {config_health}")
print(f"Checkpoint: {checkpoint_health}")
print(f"Celery: {celery_health}")
```

---

## 🚨 Error Handling

### Rate Limit Errors

The system **automatically retries** on rate limit errors with exponential backoff:

```
Retry 1: Wait 2 minutes
Retry 2: Wait 4 minutes
Retry 3: Wait 8 minutes
Retry 4: Wait 16 minutes
Retry 5: Wait 32 minutes
```

### Malformed Responses

Responses that fail parsing are:
1. Logged to Redis (`error:{task_id}`)
2. Tracked in validation result
3. Marked as completed (to avoid infinite retry)

Retrieve errors:

```bash
redis-cli keys "error:*"
redis-cli hgetall error:task-id-here
```

### Worker Crashes

If a worker crashes:
1. Task is **not acknowledged** (due to `task_acks_late=True`)
2. Task returns to queue automatically
3. Another worker picks it up
4. Checkpoint prevents duplicate processing

---

## 📦 Production Deployment

### Docker Deployment

```bash
# Build custom worker image
docker build -t mh-annotator-worker .

# Run with docker-compose (production)
docker-compose -f docker-compose.prod.yml up -d
```

### Environment Variables

Set in `.env`:

```bash
REDIS_HOST=redis-prod.example.com
REDIS_PASSWORD=your_secure_password
GEMINI_API_KEY_1=...
GEMINI_API_KEY_2=...
```

### Scaling Workers

```bash
# Scale up workers
docker-compose up -d --scale worker=10

# Or manually
celery -A src.core.celery_app worker --autoscale=10,3
```

---

## 📝 License

This project is part of the M-Help mental health annotation research initiative.

---

## 🤝 Contributing

1. Follow existing code structure
2. Add tests for new features
3. Run `black` and `flake8` before committing
4. Update documentation

---

## 📧 Support

For issues or questions, please create an issue in the repository.

---

**Built with ❤️ for mental health research**
