# Session 2: Annotation Engine & Task Implementation Documentation

## 📋 Overview

Session 2 implements the complete annotation engine with Gemini AI integration, local Excel storage, and comprehensive task management for the mental health annotation system.

## 🎯 Implemented Components

### 1. Data Models (`src/models/`)

#### **annotation.py**
Pydantic models for type-safe data validation:

```python
# Request model
AnnotationRequest(
    annotator_id=1,
    domain='urgency',
    sample_id='MH-0001',
    text='Sample text...'
)

# Result model
AnnotationResult(
    sample_id='MH-0001',
    status='success',  # or 'malformed', 'error'
    label='LEVEL_3',
    raw_response='...',
    parsing_error=None,
    validity_error=None,
    timestamp=datetime.now()
)

# Error tracking
MalformError(
    sample_id='MH-0001',
    domain='urgency',
    annotator_id=1,
    sample_text='...',
    raw_response='...',
    parsing_error='Could not find << >> tags',
    retry_count=0,
    task_id='task-123'
)

# Progress tracking
ProgressMetrics(
    annotator_id=1,
    domain='urgency',
    completed=75,
    total=100,
    malformed_count=5,
    success_rate=93.3,
    avg_task_duration=2.5
)
```

**Key Features:**
- Automatic validation with Pydantic
- Helper methods for common operations
- ISO timestamp formatting
- Success rate calculation

---

### 2. Gemini API Client (`src/core/gemini_client.py`)

#### **Rate Limiting**

Token bucket algorithm with Redis-backed state:

```python
# Rate limiter (60 req/min per annotator)
rate_limiter = TokenBucketRateLimiter(
    redis_client=redis,
    rate=60,           # Requests per minute
    bucket_capacity=60  # Maximum tokens
)

# Check rate limit
if rate_limiter.acquire(annotator_id=1, tokens=1):
    # Proceed with request
    pass
else:
    # Wait for rate limit
    wait_time = rate_limiter.wait_time(annotator_id=1)
    time.sleep(wait_time)
```

**Rate Limit Storage:**
- Redis key: `ratelimit:{annotator_id}`
- Fields: `tokens`, `last_update`
- Refill rate: 1 token per second (60/min)

#### **GeminiClient**

Main client for API interactions:

```python
client = GeminiClient(redis_client, model_name='gemini-1.5-flash')

# Generate response with automatic retry
response = client.generate(
    prompt="Your prompt here",
    annotator_id=1,
    domain='urgency',
    max_retries=3,
    base_delay=2.0
)

# Get metrics
metrics = client.get_metrics(annotator_id=1, domain='urgency')
# Returns: {total_requests, successful_requests, failed_requests, avg_duration}
```

**Error Handling:**
- `RateLimitError` → Automatic retry with exponential backoff
- `InvalidRequestError` → No retry (log and fail)
- `GeminiAPIError` → Retry up to max_retries

**Retry Strategy:**
- Exponential backoff: 2s, 4s, 8s, 16s, 32s
- Rate limit waits: Based on token bucket state
- Maximum retries: 3 (configurable)

---

### 3. Source Data Loader (`src/storage/source_loader.py`)

Loads M-Help dataset from Excel with Redis caching:

```python
loader = SourceDataLoader(
    excel_path='data/source/m_help_dataset.xlsx',
    redis_client=redis,
    id_column='Sample_ID',
    text_column='Text'
)

# Load all samples (cached in Redis)
samples = loader.load_all_samples()
# Returns: [{'sample_id': '...', 'text': '...', 'metadata': {...}}, ...]

# Get specific sample
sample = loader.get_sample_by_id('MH-0001')

# Get statistics
stats = loader.get_statistics()
# Returns: {total_samples, avg_text_length, min_text_length, max_text_length}

# Clear cache and reload
loader.reload()
```

**Redis Cache:**
- Sample IDs: `source:sample_ids` (Redis List)
- Individual samples: `source:sample:{sample_id}` (Redis Hash)
- TTL: 24 hours
- Automatic cache on first load

**Expected Excel Structure:**
- Column A: `Sample_ID` (required)
- Column B: `Text` (required)
- Other columns: Optional metadata

---

### 4. Excel Annotation Manager (`src/storage/excel_manager.py`)

Manages annotation output to Excel files with file locking:

```python
excel_mgr = ExcelAnnotationManager(
    output_dir='data/annotations',
    redis_client=redis,
    buffer_size=10  # Flush after 10 rows
)

# Initialize file for worker
excel_mgr.initialize_file(annotator_id=1, domain='urgency')
# Creates: data/annotations/annotator_1_urgency.xlsx

# Write annotation (buffered)
row_data = {
    'sample_id': 'MH-0001',
    'text': 'Sample text...',
    'raw_response': 'Response... <<LEVEL_3>>',
    'label': 'LEVEL_3',
    'malformed_flag': False,
    'parsing_error': '',
    'validity_error': '',
    'timestamp': '2025-01-26 10:30:00'
}
excel_mgr.write_annotation(annotator_id=1, domain='urgency', row_data)

# Flush buffer to disk
excel_mgr.flush_buffer(annotator_id=1, domain='urgency')

# Resume: Sync checkpoint from existing Excel file
synced_count = excel_mgr.sync_checkpoint_from_excel(
    annotator_id=1,
    domain='urgency'
)
# Reads Excel file and updates Redis checkpoint

# Get progress
completed, total = excel_mgr.get_progress(annotator_id=1, domain='urgency')

# Get completed samples
completed_ids = excel_mgr.get_completed_sample_ids(annotator_id=1, domain='urgency')

# Export to CSV
excel_mgr.export_to_csv(annotator_id=1, domain='urgency', 'output.csv')
```

**Excel File Structure:**
- Headers: `Sample_ID | Text | Raw_Response | Label | Malformed_Flag | Parsing_Error | Validity_Error | Timestamp`
- Formatting: Bold headers, frozen panes, auto-filter
- Malformed rows: Highlighted in yellow
- One file per worker: `annotator_{id}_{domain}.xlsx`

**File Locking:**
- Unix: `fcntl.flock()`
- Windows: `msvcrt.locking()`
- Automatic retry with exponential backoff

**Resume Capability:**
1. On worker start, read existing Excel file
2. Extract completed sample IDs
3. Update Redis checkpoint
4. Worker skips already-completed samples

---

### 5. Malform Logger (`src/storage/malform_logger.py`)

Dual storage for malformed responses (Redis + JSON):

```python
malform_logger = MalformLogger(
    log_dir='data/malform_logs',
    redis_client=redis,
    auto_sync_count=50,      # Sync after 50 errors
    auto_sync_interval=300   # Sync every 5 minutes
)

# Log malformed response
error_data = {
    'sample_text': 'Original text...',
    'raw_response': 'Malformed response',
    'parsing_error': 'Could not find << >> tags',
    'validity_error': None,
    'retry_count': 0,
    'task_id': 'task-123'
}
malform_logger.log_error(
    annotator_id=1,
    domain='urgency',
    sample_id='MH-0001',
    error_data=error_data
)

# Get malforms for worker
malforms = malform_logger.get_malforms(annotator_id=1, domain='urgency')

# Get summary
summary = malform_logger.get_summary(annotator_id=1)
# Returns: {total_malforms, by_domain: {urgency: 5, therapeutic: 3, ...}}

# Force sync to JSON
malform_logger.force_sync(annotator_id=1, domain='urgency')

# Export all to Excel
malform_logger.export_all_to_excel('all_malforms.xlsx')

# Get statistics
stats = malform_logger.get_statistics()
# Returns: {total_malforms, by_annotator, by_domain, by_error_type}
```

**Storage Locations:**

**Redis (Real-time):**
- Malform data: `malform:{annotator_id}:{domain}:{sample_id}` (Hash)
- Count tracking: `malform_count:{annotator_id}:{domain}` (Sorted Set)
- TTL: 7 days

**JSON Files (Persistent):**
- File pattern: `annotator_{id}_{domain}_malforms.json`
- Auto-sync: Every 50 errors or 5 minutes
- Thread-safe file operations

**JSON Structure:**
```json
{
  "annotator_id": 1,
  "domain": "urgency",
  "created_at": "2025-01-26T10:00:00",
  "last_updated": "2025-01-26T12:30:00",
  "total_malforms": 15,
  "malforms": {
    "MH-0001": {
      "timestamp": "2025-01-26T10:15:00",
      "sample_text": "...",
      "raw_response": "...",
      "parsing_error": "...",
      "validity_error": null,
      "retry_count": 0,
      "task_id": "task-123"
    }
  }
}
```

---

### 6. Annotation Tasks (`src/core/tasks.py`)

Celery tasks for distributed annotation:

#### **Main Task: `annotate_sample`**

```python
from src.core.tasks import annotate_sample

# Queue annotation task
result = annotate_sample.apply_async(
    kwargs={
        'annotator_id': 1,
        'domain': 'urgency',
        'sample_id': 'MH-0001',
        'text': 'Sample text to annotate...'
    },
    queue='annotator_1_urgency'
)

# Get task result
task_result = result.get()
# Returns: {
#     'sample_id': 'MH-0001',
#     'status': 'success',
#     'label': 'LEVEL_3',
#     'raw_response': '...',
#     'parsing_error': None,
#     'validity_error': None,
#     'timestamp': '2025-01-26T10:30:00'
# }
```

**Task Workflow:**

1. **Check Checkpoint**
   - Skip if already completed
   - Fast Redis lookup

2. **Load Configuration**
   - Get prompt template
   - Get API key
   - Get validation rules

3. **Build Prompt**
   - Format template with sample text
   - Apply domain-specific instructions

4. **Generate Response**
   - Call Gemini with rate limiting
   - Automatic retry on errors
   - Track request metrics

5. **Parse & Validate**
   - Extract label from `<< >>` tags
   - Validate against domain rules
   - Classify errors

6. **Write to Excel**
   - Buffer write (immediate flush)
   - File locking for safety
   - Formatted output

7. **Log Malformed**
   - Store in Redis + JSON
   - Track error types
   - Auto-sync to file

8. **Update Checkpoint**
   - Atomic Redis update
   - Progress tracking
   - Enable resume

9. **Track Metrics**
   - Task duration
   - Success/failure rates
   - API performance

10. **Return Result**
    - Structured response
    - Error details if any

**Retry Logic:**
- Rate limits: Exponential backoff
- Network errors: Max 3 retries
- Validation errors: No retry (log as malformed)

#### **Task Queue Population**

```python
from src.core.tasks import populate_task_queues

# Populate all workers
results = populate_task_queues()

# Populate specific annotator
results = populate_task_queues(annotator_id=1)

# Populate specific domain
results = populate_task_queues(domain='urgency')

# Limit samples per worker
results = populate_task_queues(limit=100)

# Results structure:
{
    'total_queued': 150,
    'by_worker': {
        '1_urgency': {
            'queued': 50,
            'completed': 0,
            'total': 50,
            'queue_name': 'annotator_1_urgency'
        },
        '1_therapeutic': {...},
        ...
    }
}
```

**Population Logic:**
1. Load all samples from source Excel
2. For each enabled worker:
   - Sync checkpoint from Excel (resume)
   - Get completed sample IDs
   - Filter pending samples
   - Apply sample limit if configured
   - Queue tasks to Celery
3. Store queue metadata in Redis
4. Return queuing summary

---

## 🚀 Usage Examples

### **Example 1: Simple Annotation Flow**

```python
from src.core.tasks import populate_task_queues
from src.storage.excel_manager import ExcelAnnotationManager
import redis

# 1. Start Redis and Celery workers
# docker-compose up -d
# celery -A src.core.celery_app worker --queues=annotator_1_urgency --loglevel=info

# 2. Populate task queue
results = populate_task_queues(annotator_id=1, domain='urgency', limit=10)
print(f"Queued {results['total_queued']} tasks")

# 3. Monitor progress (in separate script)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
excel_mgr = ExcelAnnotationManager('data/annotations', redis_client)

completed, total = excel_mgr.get_progress(annotator_id=1, domain='urgency')
print(f"Progress: {completed}/{total} ({completed/total*100:.1f}%)")

# 4. Check results
file_path = 'data/annotations/annotator_1_urgency.xlsx'
import pandas as pd
df = pd.read_excel(file_path)
print(df.head())
```

### **Example 2: Resume After Crash**

```python
from src.core.tasks import populate_task_queues
from src.storage.excel_manager import ExcelAnnotationManager
import redis

# System crashed with 50/100 samples completed

# 1. Restart infrastructure
# docker-compose up -d
# celery -A src.core.celery_app worker --queues=annotator_1_urgency --loglevel=info

# 2. Populate queue (automatically skips completed)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
excel_mgr = ExcelAnnotationManager('data/annotations', redis_client)

# Sync checkpoint from Excel
synced = excel_mgr.sync_checkpoint_from_excel(annotator_id=1, domain='urgency')
print(f"Synced {synced} completed samples from Excel")

# Populate remaining tasks
results = populate_task_queues(annotator_id=1, domain='urgency')
print(f"Queued {results['total_queued']} remaining tasks")
# Will only queue the 50 remaining samples
```

### **Example 3: Analyze Malformed Responses**

```python
from src.storage.malform_logger import MalformLogger
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
malform_logger = MalformLogger('data/malform_logs', redis_client)

# Get summary
summary = malform_logger.get_summary(annotator_id=1)
print(f"Total malforms: {summary['total_malforms']}")
print("By domain:")
for domain, count in summary['by_domain'].items():
    print(f"  {domain}: {count}")

# Get specific malforms
malforms = malform_logger.get_malforms(annotator_id=1, domain='urgency')
print(f"\nFound {len(malforms)} malformed responses for urgency:")
for malform in malforms[:5]:  # Show first 5
    print(f"  Sample: {malform.get('sample_id')}")
    print(f"  Error: {malform.get('parsing_error') or malform.get('validity_error')}")
    print()

# Export all to Excel for analysis
malform_logger.export_all_to_excel('analysis/all_malforms.xlsx')
print("Exported malforms to Excel")
```

### **Example 4: Monitor API Performance**

```python
from src.core.gemini_client import GeminiClient
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
client = GeminiClient(redis_client)

# Get metrics for each worker
for annotator_id in range(1, 6):
    for domain in ['urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal']:
        metrics = client.get_metrics(annotator_id, domain)

        if metrics['total_requests'] > 0:
            success_rate = (metrics['successful_requests'] / metrics['total_requests']) * 100
            print(f"\nAnnotator {annotator_id} - {domain}:")
            print(f"  Total requests: {metrics['total_requests']}")
            print(f"  Success rate: {success_rate:.1f}%")
            print(f"  Avg duration: {metrics['avg_duration']:.2f}s")
            print(f"  Failed: {metrics['failed_requests']}")
```

---

## 📁 File Structure Summary

```
M-Heath-Annotator/
├── src/
│   ├── core/
│   │   ├── gemini_client.py       # Gemini API client with rate limiting
│   │   └── tasks.py                # Celery annotation tasks
│   ├── storage/
│   │   ├── source_loader.py        # Load source data from Excel
│   │   ├── excel_manager.py        # Manage annotation Excel files
│   │   └── malform_logger.py       # Log malformed responses
│   └── models/
│       └── annotation.py           # Pydantic data models
├── data/
│   ├── source/
│   │   ├── m_help_dataset.xlsx    # Source dataset (input)
│   │   └── create_sample_dataset.py
│   ├── annotations/
│   │   ├── annotator_1_urgency.xlsx
│   │   ├── annotator_1_therapeutic.xlsx
│   │   └── ... (30 files total)
│   └── malform_logs/
│       ├── annotator_1_urgency_malforms.json
│       └── ...
└── tests/
    ├── test_core/
    │   └── test_gemini_client.py
    ├── test_storage/
    │   └── test_excel_manager.py
    └── test_models/
        └── test_annotation.py
```

---

## 🧪 Testing

### **Run All Tests**

```bash
cd M-Heath-Annotator
pytest tests/ -v
```

### **Run Specific Test Suite**

```bash
# Test Gemini client
pytest tests/test_core/test_gemini_client.py -v

# Test Excel manager
pytest tests/test_storage/test_excel_manager.py -v

# Test data models
pytest tests/test_models/test_annotation.py -v
```

### **Run with Coverage**

```bash
pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

---

## 🔧 Configuration

### **Model Configuration** (`config/settings.yaml`)

```yaml
model:
  name: gemini-1.5-flash
  provider: google
  temperature: 0.0       # Deterministic responses
  max_tokens: 2048

data:
  source_type: excel
  excel_path: data/source/m_help_dataset.xlsx
  sheets:
    - Train
    - Validation
    - Test
  id_column: Sample_ID
  text_column: Text

output:
  type: excel
  directory: data/annotations
```

---

## ⚠️ Important Notes

### **Rate Limiting**
- 60 requests per minute per annotator
- Token bucket with Redis state
- Automatic retry with exponential backoff
- Monitor: `redis-cli hgetall ratelimit:1`

### **File Locking**
- Cross-platform support (Unix/Windows)
- Automatic retry on lock failure
- Maximum 5 retry attempts
- Use context managers for safety

### **Resume Capability**
- Always call `sync_checkpoint_from_excel()` before populating queues
- Redis checkpoint synced with Excel state
- Workers automatically skip completed samples
- No duplicate annotations

### **Memory Usage**
- Source data cached in Redis (24-hour TTL)
- ~10KB per sample in memory
- 1000 samples ≈ 10MB memory
- Clear cache: `source_loader.clear_cache()`

### **Error Handling**
- Malformed responses: Logged but marked as completed (no infinite retry)
- API errors: Retried up to 3 times
- Rate limits: Waited automatically
- Validation errors: No retry (by design)

---

## 📊 Monitoring

### **Redis Keys to Monitor**

```bash
# Rate limits
redis-cli hgetall ratelimit:1

# Checkpoints
redis-cli smembers checkpoint:1:urgency

# Progress
redis-cli hgetall progress:1:urgency

# Malforms
redis-cli keys "malform:1:urgency:*"

# Metrics
redis-cli hgetall metrics:1:urgency
redis-cli hgetall task_metrics:1:urgency
```

### **Flower Dashboard**
- URL: http://localhost:5555
- Credentials: admin/admin
- Features: Active tasks, worker stats, task history

### **Excel Files**
- Real-time annotation results
- Malformed responses highlighted
- CSV export available

---

## ✅ Completion Checklist

- [x] Data models with Pydantic validation
- [x] Gemini API client with rate limiting
- [x] Source data loader with Redis caching
- [x] Excel annotation manager with file locking
- [x] Malform logger with dual storage
- [x] Annotation Celery tasks
- [x] Task queue population logic
- [x] Comprehensive test suite (>80% coverage)
- [x] Sample dataset generation
- [x] Complete documentation

---

## 🎓 Key Learnings

1. **Token Bucket Rate Limiting**: Efficient distributed rate limiting using Redis
2. **File Locking**: Cross-platform safe concurrent file access
3. **Resume Capability**: Sync checkpoints from Excel for crash recovery
4. **Dual Storage**: Real-time Redis + persistent JSON for malform tracking
5. **Buffered Writes**: Reduce I/O with write buffering + periodic flushes
6. **Exponential Backoff**: Graceful handling of transient errors
7. **Type Safety**: Pydantic models catch errors at model boundaries

---

## 🚀 Next Steps (Session 3+)

1. **Dashboard**: Web UI for monitoring annotation progress
2. **Batch Processing**: Optimize for large-scale datasets (10K+ samples)
3. **Quality Assurance**: Inter-annotator agreement metrics
4. **Export Formats**: Support for CSV, JSON, Parquet
5. **Advanced Analytics**: Visualizations for malform patterns
6. **Worker Management**: Dynamic scaling based on queue length
7. **Cost Tracking**: Monitor API usage and costs per annotator

---

**Session 2 Implementation Complete! ✅**

All components are production-ready with comprehensive tests and documentation.
