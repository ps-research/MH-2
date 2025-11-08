# Mental Health Annotation System - Complete Guide

 

## 📋 Table of Contents

 

1. [Overview](#overview)

2. [System Architecture](#system-architecture)

3. [Prerequisites](#prerequisites)

4. [Installation](#installation)

5. [Configuration](#configuration)

6. [Starting the System](#starting-the-system)

7. [Monitoring & Control](#monitoring--control)

8. [Excel Operations](#excel-operations)

9. [Administrative Operations](#administrative-operations)

10. [Testing](#testing)

11. [Complete Workflows](#complete-workflows)

12. [Troubleshooting](#troubleshooting)

13. [API Reference](#api-reference)

14. [VSCode Integration](#vscode-integration)

15. [Advanced Usage](#advanced-usage)

 

---

 

## Overview

 

The Mental Health Annotation System is a distributed, scalable annotation platform using Celery workers, Redis for state management, and Gemini AI for automated annotation. The system features:

 

- **30 Parallel Workers** (5 annotators × 6 domains)

- **Real-time Dashboard** with Rich TUI

- **Excel-based Storage** with checkpoint recovery

- **Interactive CLI Tools** for control and monitoring

- **VSCode Integration** for developer productivity

- **Comprehensive Makefile** for common operations

 

### Session Overview

 

**Session 1**: Core infrastructure (Celery, Redis, checkpoints, configuration)

**Session 2**: Annotation engine (Gemini API, Excel storage, task management)

**Session 3**: Worker management (launcher, controller, monitor, admin operations)

**Session 4**: CLI dashboard (Rich TUI, Excel viewer, interactive shell, VSCode integration)

 

---

 

## System Architecture

 

```

┌─────────────────────────────────────────────────────────────┐

│                     User Interface Layer                    │

│  Dashboard │ CLI Commands │ Interactive Shell │ VSCode     │

├─────────────────────────────────────────────────────────────┤

│                    Control & Admin Layer                    │

│  ControlAPI │ AdminOperations │ WorkerController           │

├─────────────────────────────────────────────────────────────┤

│                      Worker Layer                           │

│  WorkerLauncher │ WorkerMonitor │ 30 Celery Workers        │

├─────────────────────────────────────────────────────────────┤

│                   Processing Layer                          │

│  Annotation Tasks │ Gemini Client │ Rate Limiter           │

├─────────────────────────────────────────────────────────────┤

│                     Storage Layer                           │

│  Excel Manager │ Malform Logger │ Source Loader            │

├─────────────────────────────────────────────────────────────┤

│                 Infrastructure Layer                        │

│  Redis (State & Queue) │ File System (Excel, Logs)         │

└─────────────────────────────────────────────────────────────┘

```

 

### Data Flow

 

1. **Source Data** → Load from Excel → Cache in Redis

2. **Task Queue** → Populate with pending samples → Distribute to workers

3. **Workers** → Fetch tasks → Call Gemini API → Process responses

4. **Results** → Write to Excel → Update checkpoints → Log malforms

5. **Monitoring** → Read Redis state → Display in dashboard → Control workers

 

---

 

## Prerequisites

 

### System Requirements

 

- **OS**: Linux, macOS, or Windows (WSL recommended)

- **Python**: 3.9 or higher

- **Docker**: For Redis (or install Redis locally)

- **Memory**: 4GB+ RAM recommended

- **Disk**: 10GB+ free space for data storage

 

### Required Software

 

```bash

# Check Python version

python --version  # Should be 3.9+

 

# Check Docker (if using)

docker --version

 

# Check Git

git --version

```

 

---

 

## Installation

 

### 1. Clone Repository

 

```bash

git clone <repository-url>

cd MH-2/M-Heath-Annotator

```

 

### 2. Create Virtual Environment

 

```bash

# Create virtual environment

python -m venv venv

 

# Activate virtual environment

# On Linux/macOS:

source venv/bin/activate

 

# On Windows:

venv\Scripts\activate

```

 

### 3. Install Dependencies

 

```bash

# Using Makefile (recommended)

make install

 

# Or manually

pip install -r requirements.txt

```

 

### 4. Setup Directory Structure

 

```bash

# Create all required directories

make setup

 

# This creates:

# - data/logs/

# - data/checkpoints/

# - data/malform_logs/

# - data/annotations/

# - data/source/

# - data/archive/

# - data/exports/

```

 

### 5. Start Redis

 

```bash

# Using Docker (recommended)

make start-redis

 

# Or using docker-compose directly

docker-compose up -d redis

 

# Or install Redis locally (Linux)

sudo apt-get install redis-server

sudo systemctl start redis

```

 

### 6. Verify Installation

 

```bash

# Check Redis connection

python -c "import redis; r = redis.Redis(host='localhost', port=6379); r.ping(); print('Redis OK')"

 

# Check all configurations

make validate-config

 

# Run tests

make test

```

 

---

 

## Configuration

 

### Configuration Files

 

All configuration is in the `config/` directory:

 

```

config/

├── annotators.yaml    # Annotator API keys and settings

├── domains.yaml       # Domain definitions and prompts

├── workers.yaml       # Worker assignments and settings

└── settings.yaml      # System-wide settings

```

 

### 1. Configure Annotators

 

Edit `config/annotators.yaml`:

 

```yaml

annotators:

  - id: 1

    name: "Annotator 1"

    api_key: "YOUR_GEMINI_API_KEY_HERE"

    enabled: true

    rate_limit: 60  # Requests per minute

 

  - id: 2

    name: "Annotator 2"

    api_key: "YOUR_GEMINI_API_KEY_HERE"

    enabled: true

    rate_limit: 60

 

  # ... continue for annotators 3, 4, 5

```

 

**Get Gemini API Keys:**

1. Visit https://makersuite.google.com/app/apikey

2. Create API key

3. Copy to `api_key` field above

 

### 2. Configure Domains

 

Edit `config/domains.yaml`:

 

```yaml

domains:

  - name: "urgency"

    description: "Urgency level assessment"

    valid_labels:

      - "LEVEL_0"  # No urgency

      - "LEVEL_1"  # Low urgency

      - "LEVEL_2"  # Moderate urgency

      - "LEVEL_3"  # High urgency

      - "LEVEL_4"  # Critical urgency

    prompt_template: |

      Analyze the following mental health scenario and assess the urgency level...

 

      Text: {text}

 

      Respond with ONLY one of: LEVEL_0, LEVEL_1, LEVEL_2, LEVEL_3, LEVEL_4

      Format: <<LEVEL_X>>

 

  # ... other domains (therapeutic, intensity, adjunct, modality, redressal)

```

 

### 3. Configure Workers

 

Edit `config/workers.yaml`:

 

```yaml

workers:

  - annotator_id: 1

    domain: "urgency"

    enabled: true

    concurrency: 1

 

  - annotator_id: 1

    domain: "therapeutic"

    enabled: true

    concurrency: 1

 

  # ... configure all 30 workers (5 annotators × 6 domains)

```

 

### 4. System Settings

 

Edit `config/settings.yaml`:

 

```yaml

model:

  name: "gemini-1.5-flash"

  temperature: 0.0

  max_tokens: 2048

 

data:

  source_type: "excel"

  excel_path: "data/source/m_help_dataset.xlsx"

  id_column: "Sample_ID"

  text_column: "Text"

 

output:

  type: "excel"

  directory: "data/annotations"

  buffer_size: 10  # Flush after 10 rows

 

redis:

  host: "localhost"

  port: 6379

  db: 0

```

 

### 5. Validate Configuration

 

```bash

# Validate all configs

make validate-config

 

# Or manually

python -m src.cli.commands config validate

```

 

### 6. Edit Configs Interactively

 

```bash

# Edit specific config type

make edit-config TYPE=annotators

make edit-config TYPE=domains

make edit-config TYPE=workers

make edit-config TYPE=settings

 

# Or use the config editor

python scripts/config_editor.py annotators

```

 

---

 

## Starting the System

 

### Quick Start (All Workers)

 

```bash

# 1. Ensure Redis is running

make start-redis

 

# 2. Start all workers

make start-workers

 

# 3. Monitor with dashboard (in another terminal)

make dashboard

```

 

### Detailed Startup

 

#### Step 1: Prepare Source Data

 

Place your dataset in `data/source/m_help_dataset.xlsx` with columns:

- `Sample_ID`: Unique identifier for each sample

- `Text`: The mental health scenario text

- (Optional) Other metadata columns

 

**Or create sample data:**

 

```bash

# Create sample dataset (50 samples)

python data/source/create_sample_dataset.py

```

 

#### Step 2: Start Redis

 

```bash

# Using Makefile

make start-redis

 

# Verify Redis is running

docker ps | grep redis

 

# Check Redis connection

redis-cli ping  # Should return "PONG"

```

 

#### Step 3: Launch Workers

 

**Option A: Start All Workers (Recommended)**

 

```bash

python scripts/start_all.py

 

# This will:

# 1. Check prerequisites

# 2. Initialize Excel files

# 3. Sync checkpoints from existing files

# 4. Populate task queues

# 5. Launch all 30 workers

# 6. Write PID file to data/workers.pid

```

 

**Option B: Start Specific Annotator**

 

```bash

python scripts/start_all.py --annotator 1

 

# Or using Makefile

make start-annotator A=1

```

 

**Option C: Start Specific Domain**

 

```bash

python scripts/start_all.py --domain urgency

 

# Or using Makefile

make start-domain D=urgency

```

 

**Option D: Dry Run (See What Would Start)**

 

```bash

python scripts/start_all.py --dry-run

```

 

**Option E: Force Resync Checkpoints**

 

```bash

# Resync all checkpoints from Excel before starting

python scripts/start_all.py --resync

```

 

#### Step 4: Verify Workers Started

 

```bash

# Check worker status

make status

 

# Or use CLI

python -m src.cli.commands worker status

 

# Check PID file

cat data/workers.pid

 

# Check logs

tail -f data/logs/*.log

 

# Check Redis for worker metadata

redis-cli keys "worker:*"

```

 

### Startup Troubleshooting

 

**Workers not starting:**

```bash

# Check Redis connection

redis-cli ping

 

# Check for port conflicts

netstat -tulpn | grep 6379

 

# Check Python version

python --version  # Should be 3.9+

 

# Check dependencies

pip list | grep -E "celery|redis|rich"

```

 

**Queue not populating:**

```bash

# Check source data exists

ls -lh data/source/m_help_dataset.xlsx

 

# Check queue manually

redis-cli llen annotator_1_urgency

 

# Populate manually

python -c "from src.core.tasks import populate_task_queues; populate_task_queues()"

```

 

---

 

## Monitoring & Control

 

### 1. Rich TUI Dashboard (Recommended)

 

**Launch Dashboard:**

 

```bash

make dashboard

 

# Or with options

python scripts/dashboard.py --refresh-rate 500 --excel-sync-interval 2000

```

 

**Dashboard Layout:**

 

```

┌─────────────────────────────────────────────────────────────┐

│                    System Overview                          │

│  Workers: 28/30 running | 2 paused | 0 stopped             │

│  System: CPU: 45.2% | Memory: 62.1% | Disk: 35.8%         │

│  Progress: 1,234/1,500 samples (82.3%)                     │

├─────────────────────────────────────────────────────────────┤

│                                                             │

│  ┌─ A1:Urg ──┐  ┌─ A1:Ther ─┐  ┌─ A1:Inten ─┐  ...      │

│  │ ████░░ 80% │  │ ███░░░ 60% │  │ █████░ 90% │          │

│  │ 120/150    │  │ 90/150     │  │ 135/150    │          │

│  │ ● Running  │  │ ● Running  │  │ ● Running  │          │

│  │ 12/min     │  │ 10/min     │  │ 15/min     │          │

│  │ 2.4 MB     │  │ 2.1 MB     │  │ 2.8 MB     │          │

│  └────────────┘  └────────────┘  └────────────┘          │

│                                                             │

│  (5 rows × 6 columns = 30 workers)                         │

│                                                             │

├─────────────────────────────────────────────────────────────┤

│  Recent Logs:                                               │

│  [10:30:15] [1_urgency] Sample ID-123 completed            │

│  [10:30:16] [2_therapeutic] Sample ID-124 completed        │

│  [10:30:17] [1_urgency] Excel buffer flushed (10 rows)    │

└─────────────────────────────────────────────────────────────┘

```

 

**Keyboard Shortcuts:**

- `q`: Quit dashboard

- `p`: Pause selected worker

- `r`: Resume selected worker

- `k`: Kill selected worker

- `f`: Flush Excel buffer

- `a`: Kill all workers

- `c`: Clear logs

- `e`: Open Excel viewer

- `s`: Show system metrics

- `v`: Verify Excel integrity

- `:`: Enter command mode

 

**Exit Dashboard:**

- Press `q` or `Ctrl+C`

- Dashboard will automatically flush all Excel buffers before exiting

 

### 2. Interactive Shell

 

**Launch Shell:**

 

```bash

make interactive

 

# Or directly

python -m src.cli.interactive

```

 

**Basic Commands:**

 

```

# Set context (so you don't have to specify annotator/domain each time)

annotator> use 1 urgency

Context set to: Annotator 1, Domain urgency

 

# Now commands use context

[A1:urgency] > status

Status: running

PID: 12345

Uptime: 3600s

Tasks Processed: 120

Tasks Remaining: 30

Excel File: data/annotations/annotator_1_urgency.xlsx

 

# Control commands

[A1:urgency] > pause

✓ Paused worker 1:urgency

 

[A1:urgency] > resume

✓ Resumed worker 1:urgency

 

[A1:urgency] > flush

✓ Flushed 5 rows to Excel

 

# Excel commands

[A1:urgency] > last-sample

Sample ID: MH-0120

Label: LEVEL_3

Malformed: False

Timestamp: 2025-01-26 10:30:00

 

[A1:urgency] > malformed-count

Malformed: 5/120 (4.2%)

 

[A1:urgency] > excel-size

Excel file size: 2.45 MB (2,568,192 bytes)

 

# System commands

[A1:urgency] > system

CPU: 45.2%

Memory: 62.1%

Disk: 35.8%

Redis Memory: 128.5 MB

 

[A1:urgency] > workers

All Workers:

  1_urgency: Running (120/150)

  1_therapeutic: Running (90/150)

  ...

 

# Help

[A1:urgency] > help

 

# Exit

[A1:urgency] > exit

```

 

**Command Reference:**

 

| Command | Shortcut | Description |

|---------|----------|-------------|

| `use <id> <domain>` | - | Set context |

| `status` | `st` | Show worker status |

| `pause` | `pa` | Pause worker |

| `resume` | `re` | Resume worker |

| `stop` | - | Stop worker |

| `flush` | `fl` | Flush Excel buffer |

| `last-sample` | - | Show last sample |

| `malformed-count` | - | Count malformed |

| `excel-size` | - | Show file size |

| `excel-status` | - | All file sizes |

| `system` | - | System metrics |

| `workers` | - | All workers |

| `help` | `h`, `?` | Show help |

| `clear` | `cls` | Clear screen |

| `exit` | `quit`, `q` | Exit shell |

 

### 3. CLI Commands

 

**Worker Commands:**

 

```bash

# Pause worker

python -m src.cli.commands worker pause --annotator 1 --domain urgency

make pause A=1 D=urgency

 

# Resume worker

python -m src.cli.commands worker resume --annotator 1 --domain urgency

make resume A=1 D=urgency

 

# Stop worker

python -m src.cli.commands worker stop --annotator 1 --domain urgency

 

# Stop all workers

python -m src.cli.commands worker stop --all

make stop-all

 

# Flush Excel buffer

python -m src.cli.commands worker flush --annotator 1 --domain urgency

make flush A=1 D=urgency

 

# Flush all buffers

make flush

 

# Get status

python -m src.cli.commands worker status

make status

 

# Get specific worker status

python -m src.cli.commands worker status --annotator 1 --domain urgency

```

 

**Monitor Commands:**

 

```bash

# Launch dashboard

python -m src.cli.commands monitor dashboard

make dashboard

 

# Show system metrics

python -m src.cli.commands monitor metrics

make metrics

```

 

### 4. Viewing Logs

 

**Tail All Logs:**

 

```bash

make logs

 

# Or manually

tail -f data/logs/*.log

```

 

**View Specific Worker Log:**

 

```bash

tail -f data/logs/1_urgency.log

```

 

**View Last 100 Lines:**

 

```bash

tail -n 100 data/logs/1_urgency.log

```

 

**Search Logs:**

 

```bash

grep "ERROR" data/logs/*.log

grep "malformed" data/logs/*.log

grep "Sample ID-123" data/logs/*.log

```

 

---

 

## Excel Operations

 

### 1. View Excel Files

 

**Terminal Viewer (Interactive):**

 

```bash

# View by annotator and domain

make view-excel A=1 D=urgency

 

# Or directly

python scripts/excel_viewer.py --annotator 1 --domain urgency

 

# View specific file

python scripts/excel_viewer.py --file path/to/file.xlsx

```

 

**Viewer Commands:**

 

| Command | Description |

|---------|-------------|

| `n`, `next` | Next page |

| `p`, `prev` | Previous page |

| `j`, `down` | Scroll down |

| `k`, `up` | Scroll up |

| `l`, `last` | Jump to last page |

| `f`, `first` | Jump to first page |

| `/query` | Search for text |

| `m`, `malformed` | Toggle malformed filter |

| `c` | Clear filters |

| `r`, `reload` | Reload file |

| `s`, `stats` | Show statistics |

| `e` | Export to CSV |

| `h`, `help` | Show help |

| `q`, `quit` | Exit |

 

**Open in Default App:**

 

```bash

# Linux

xdg-open data/annotations/annotator_1_urgency.xlsx

 

# macOS

open data/annotations/annotator_1_urgency.xlsx

 

# Windows

start data/annotations/annotator_1_urgency.xlsx

```

 

### 2. Verify Excel Integrity

 

```bash

# Verify all Excel files

make verify-excel

 

# Or using CLI

python -m src.cli.commands excel verify-all

```

 

This checks:

- File accessibility

- File corruption

- Header integrity

- First/last row readability

 

### 3. Export to CSV

 

**From CLI:**

 

```bash

python -m src.cli.commands excel export \

  --annotator 1 \

  --domain urgency \

  --output data/exports/annotator_1_urgency.csv

```

 

**From Viewer:**

 

```bash

# In viewer, press 'e' and enter output path

make view-excel A=1 D=urgency

# Press 'e'

# Enter: data/exports/output.csv

```

 

**Batch Export:**

 

```bash

# Export all Excel files to CSV

for file in data/annotations/*.xlsx; do

  python scripts/excel_viewer.py \

    --file "$file" \

    --export-csv "${file%.xlsx}.csv"

done

```

 

### 4. Consolidate Excel Files

 

**Consolidate All Files:**

 

```bash

# Create single consolidated file

make consolidate

 

# Or with CLI

python -m src.cli.commands admin consolidate

```

 

**Output:**

- File: `data/consolidated_annotations_<timestamp>.xlsx`

- Worksheets: One per annotator (all domains combined)

- Summary: Statistics worksheet

- Columns: Domain column added for context

 

**Consolidation Summary:**

 

```

✓ Consolidation complete

Output: data/consolidated_annotations_20250126_103000.xlsx

Total rows: 2,500

 

Worksheets:

  Annotator_1: 500 rows

  Annotator_2: 500 rows

  Annotator_3: 500 rows

  Annotator_4: 500 rows

  Annotator_5: 500 rows

  Summary: Statistics

```

 

### 5. Excel File Statistics

 

```bash

# Show all Excel file statistics

make excel-stats

 

# Output:

# Excel File Statistics:

# ======================

# annotator_1_urgency.xlsx: 2.4 MB (120 rows)

# annotator_1_therapeutic.xlsx: 2.1 MB (90 rows)

# ...

```

 

### 6. Flush Excel Buffers

 

**Why Flush:**

- Ensures data written to disk immediately

- Required before pausing/stopping workers

- Prevents data loss

 

**Flush All:**

 

```bash

make flush

```

 

**Flush Specific Worker:**

 

```bash

make flush A=1 D=urgency

```

 

**Auto-Flush:**

- Automatically flushed on worker pause/stop

- Automatically flushed on dashboard exit

- Periodically flushed (every N rows, configurable)

 

---

 

## Administrative Operations

 

### 1. Create Archive

 

**Create Backup:**

 

```bash

# Create archive with current timestamp

make archive NAME=daily_backup

 

# Or use admin script

python scripts/admin.py archive backup_20250126

```

 

**Archive Contents:**

```

data/archive/backup_20250126_103000/

├── annotations/           # All Excel files

├── malform_logs/          # All malform JSON files

├── logs/                  # All worker logs

├── redis_state.json       # Redis dump

└── archive_metadata.json  # Checksums and metadata

```

 

**Compressed Archive:**

 

```bash

# Creates .tar.gz file

python scripts/admin.py archive backup_20250126 --compress

 

# Output: data/archive/backup_20250126_103000.tar.gz

```

 

### 2. Reset Operations

 

**Reset Specific Domain:**

 

```bash

# Reset with Excel archive (safe)

make reset A=1 D=urgency KEEP=1

 

# Reset without Excel archive (deletes Excel file)

make reset A=1 D=urgency

 

# Or with admin script

python scripts/admin.py reset \

  --annotator 1 \

  --domain urgency \

  --keep-excel

```

 

**What Gets Reset:**

- Redis checkpoints for domain

- Malform logs

- Task queue

- Excel file (archived or deleted based on --keep-excel)

 

**Reset All Domains for Annotator:**

 

```bash

python scripts/admin.py reset --annotator 1 --keep-excel

```

 

### 3. Factory Reset (DESTRUCTIVE!)

 

**⚠️ Warning:** This deletes ALL data!

 

```bash

# Requires --confirm flag for safety

make factory-reset

 

# Or with admin script

python scripts/admin.py factory-reset --confirm

```

 

**What Factory Reset Does:**

1. Stops all workers

2. Creates full archive of all data

3. Clears all Redis databases

4. Archives all Excel files

5. Archives all logs and malform logs

6. Reinitializes directory structure

 

**After Factory Reset:**

- System is in clean state

- All data preserved in archive

- Ready for new annotation run

- Archive location shown in output

 

### 4. Export/Import State

 

**Export Redis State:**

 

```bash

# Export to JSON

python scripts/admin.py export --output data/state_backup.json

```

 

**Import Redis State:**

 

```bash

# Replace existing state

python scripts/admin.py import --file data/state_backup.json

 

# Merge with existing state

python scripts/admin.py import --file data/state_backup.json --merge

```

 

**Use Cases:**

- Backup before risky operations

- Transfer state between environments

- Restore after Redis crash

- Debugging and analysis

 

---

 

## Testing

 

### 1. Run All Tests

 

```bash

# Run full test suite with coverage

make test

 

# Output:

# ===== test session starts =====

# tests/test_core/test_gemini_client.py::TestTokenBucketRateLimiter::test_initialization PASSED

# tests/test_core/test_gemini_client.py::TestTokenBucketRateLimiter::test_acquire_token_success PASSED

# ...

# ===== 31 passed in 2.45s =====

#

# ---------- coverage: ... ----------

# Name                        Stmts   Miss  Cover

# -----------------------------------------------

# src/core/gemini_client.py    420     35    92%

# src/storage/excel_manager.py 450     45    90%

# ...

# -----------------------------------------------

# TOTAL                       2135    189    91%

```

 

### 2. Run Fast Tests (No Coverage)

 

```bash

make test-fast

```

 

### 3. Run Specific Test Suite

 

```bash

# Test Gemini client

pytest tests/test_core/test_gemini_client.py -v

 

# Test Excel manager

pytest tests/test_storage/test_excel_manager.py -v

 

# Test worker launcher

pytest tests/test_workers/test_launcher.py -v

```

 

### 4. Run Tests with Specific Pattern

 

```bash

# Run tests matching pattern

pytest tests/ -k "test_rate" -v

 

# Run tests in specific file matching pattern

pytest tests/test_core/test_gemini_client.py -k "acquire" -v

```

 

### 5. Code Quality Checks

 

**Linting:**

 

```bash

make lint

 

# Or manually

flake8 src/ tests/

```

 

**Formatting:**

 

```bash

# Check formatting

make lint

 

# Auto-format code

make format

```

 

**Type Checking:**

 

```bash

make type-check

 

# Or manually

mypy src/

```

 

### 6. Integration Testing

 

**Test Complete Workflow:**

 

```bash

# 1. Start system

make start-redis

make start-workers

 

# 2. Wait for some processing

sleep 60

 

# 3. Check status

make status

 

# 4. Verify Excel files

make verify-excel

 

# 5. Check data integrity

python -c "

from src.api.control import ControlAPI

import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

api = ControlAPI(r)

verification = api.verify_data_integrity()

print('Status:', verification['overall_status'])

print('Issues:', verification['issues'])

"

 

# 6. Consolidate

make consolidate

 

# 7. View results

make view-excel A=1 D=urgency

 

# 8. Stop system

make stop-all

```

 

### 7. Performance Testing

 

**Test Rate Limiting:**

 

```bash

python -c "

import redis

import time

from src.core.gemini_client import TokenBucketRateLimiter

 

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

limiter = TokenBucketRateLimiter(r, rate=60, bucket_capacity=60)

 

# Try to acquire 100 tokens rapidly

start = time.time()

acquired = 0

for i in range(100):

    if limiter.acquire(annotator_id=1, tokens=1):

        acquired += 1

    time.sleep(0.1)

elapsed = time.time() - start

 

print(f'Acquired: {acquired}/100 tokens in {elapsed:.1f}s')

print(f'Rate: {acquired/elapsed*60:.1f} requests/min')

"

```

 

**Test Worker Throughput:**

 

```bash

# Start system and monitor

make start-redis

make start-workers

 

# Monitor throughput

watch -n 1 'redis-cli get processed_count'

 

# Or use dashboard

make dashboard

```

 

---

 

## Complete Workflows

 

### Workflow 1: Fresh Start with New Dataset

 

```bash

# 1. Prepare dataset

cp /path/to/your/dataset.xlsx data/source/m_help_dataset.xlsx

 

# 2. Validate dataset structure

python -c "

import pandas as pd

df = pd.read_excel('data/source/m_help_dataset.xlsx')

print('Columns:', df.columns.tolist())

print('Rows:', len(df))

assert 'Sample_ID' in df.columns

assert 'Text' in df.columns

print('✓ Dataset valid')

"

 

# 3. Configure system

make edit-config TYPE=annotators  # Add API keys

make validate-config

 

# 4. Start system

make start-redis

make start-workers

 

# 5. Monitor progress

make dashboard

 

# 6. When complete, consolidate

make consolidate

 

# 7. Create archive

make archive NAME=completed_run_1

 

# 8. Stop system

make stop-all

```

 

### Workflow 2: Resume After Crash

 

```bash

# 1. Start Redis

make start-redis

 

# 2. Check existing data

ls -lh data/annotations/*.xlsx

 

# 3. Start workers (automatically syncs from Excel)

make start-workers

 

# Workers will:

# - Read existing Excel files

# - Sync Redis checkpoints

# - Skip completed samples

# - Continue from where they left off

 

# 4. Monitor resumed progress

make dashboard

 

# 5. Verify no duplicates

python -c "

from src.api.control import ControlAPI

import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

api = ControlAPI(r)

consolidation = api.consolidate_progress()

print('Discrepancies:', consolidation['discrepancies'])

"

```

 

### Workflow 3: Pause, Modify, Resume

 

```bash

# 1. Pause all workers

make pause-all

 

# 2. Verify all paused

make status

 

# 3. Make changes (e.g., edit prompts)

make edit-config TYPE=domains

 

# 4. Validate changes

make validate-config

 

# 5. Resume workers

# Note: Config changes require restart, not just resume

make stop-all

make start-workers

 

# 6. Monitor

make dashboard

```

 

### Workflow 4: Selective Processing

 

```bash

# Only process specific annotator

make start-annotator A=1

 

# Or only specific domain

make start-domain D=urgency

 

# Or both

python scripts/start_all.py --annotator 1 --domain urgency

 

# Monitor specific worker

python -m src.cli.commands worker status --annotator 1 --domain urgency

```

 

### Workflow 5: Quality Assurance Check

 

```bash

# 1. Check malformed responses

python -c "

from src.storage.malform_logger import MalformLogger

import redis

 

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

logger = MalformLogger('data/malform_logs', r)

 

# Get summary

summary = logger.get_summary(annotator_id=1)

print(f\"Total malforms: {summary['total_malforms']}\")

print(\"By domain:\")

for domain, count in summary['by_domain'].items():

    print(f\"  {domain}: {count}\")

 

# Export to Excel for analysis

logger.export_all_to_excel('data/malform_analysis.xlsx')

print(\"\\nExported to: data/malform_analysis.xlsx\")

"

 

# 2. Verify Excel integrity

make verify-excel

 

# 3. Check data consistency

python -c "

from src.api.control import ControlAPI

import redis

 

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

api = ControlAPI(r)

 

verification = api.verify_data_integrity()

print('Overall Status:', verification['overall_status'])

print('\\nCheck Results:')

for check_name, result in verification['checks'].items():

    print(f\"  {check_name}: {result['status']}\")

 

if verification['issues']:

    print('\\nIssues Found:')

    for issue in verification['issues']:

        print(f\"  - {issue}\")

"

 

# 4. View samples with malformed responses

make view-excel A=1 D=urgency

# In viewer: press 'm' to toggle malformed filter

```

 

### Workflow 6: Daily Production Run

 

```bash

#!/bin/bash

# daily_run.sh

 

DATE=$(date +%Y%m%d)

LOG_FILE="daily_run_${DATE}.log"

 

echo "Starting daily run: $DATE" | tee -a $LOG_FILE

 

# 1. Create pre-run backup

make archive NAME="pre_run_${DATE}" | tee -a $LOG_FILE

 

# 2. Start system

make start-redis | tee -a $LOG_FILE

make start-workers | tee -a $LOG_FILE

 

# 3. Monitor and wait for completion

while true; do

    STATUS=$(python -c "

from src.api.control import ControlAPI

import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

api = ControlAPI(r)

status = api.get_global_status()

print(status['summary']['running'])

    ")

 

    if [ "$STATUS" -eq "0" ]; then

        echo "All workers completed" | tee -a $LOG_FILE

        break

    fi

 

    sleep 300  # Check every 5 minutes

done

 

# 4. Consolidate results

make consolidate | tee -a $LOG_FILE

 

# 5. Verify data

python -m src.cli.commands excel verify-all | tee -a $LOG_FILE

 

# 6. Create post-run archive

make archive NAME="completed_run_${DATE}" | tee -a $LOG_FILE

 

# 7. Stop system

make stop-all | tee -a $LOG_FILE

 

echo "Daily run complete: $DATE" | tee -a $LOG_FILE

```

 

---

 

## Troubleshooting

 

### Common Issues

 

#### 1. Workers Not Starting

 

**Symptoms:**

- `make start-workers` shows errors

- No PIDs in `data/workers.pid`

- No logs in `data/logs/`

 

**Solutions:**

 

```bash

# Check Redis connection

redis-cli ping  # Should return "PONG"

 

# Check for port conflicts

netstat -tulpn | grep 6379

 

# Check Python environment

which python

python --version

 

# Check Celery installation

python -c "import celery; print(celery.__version__)"

 

# Check config files

make validate-config

 

# Check file permissions

ls -la data/

 

# Try starting single worker manually

celery -A src.core.celery_app worker \

  -Q annotator_1_urgency \

  -n worker_1_urgency@%h \

  -c 1 \

  --loglevel=debug

```

 

#### 2. High Error Rate

 

**Symptoms:**

- Many malformed responses

- High error rate in dashboard

- Workers frequently restarting

 

**Solutions:**

 

```bash

# Check malform logs

ls -lh data/malform_logs/

 

# Analyze malforms

python -c "

from src.storage.malform_logger import MalformLogger

import redis

 

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

logger = MalformLogger('data/malform_logs', r)

 

# Get all malforms

for annotator_id in range(1, 6):

    for domain in ['urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal']:

        malforms = logger.get_malforms(annotator_id, domain)

        if malforms:

            print(f\"\\n{annotator_id}_{domain}: {len(malforms)} malforms\")

            # Show first malform

            print(f\"  Example: {malforms[0].get('parsing_error')}\")

"

 

# Check prompt templates

make edit-config TYPE=domains

 

# Test Gemini API directly

python -c "

import google.generativeai as genai

genai.configure(api_key='YOUR_API_KEY')

model = genai.GenerativeModel('gemini-1.5-flash')

response = model.generate_content('Say hello')

print(response.text)

"

```

 

#### 3. Excel File Corruption

 

**Symptoms:**

- `make verify-excel` shows failures

- Can't open Excel files

- Data loss

 

**Solutions:**

 

```bash

# Verify all Excel files

make verify-excel

 

# Check specific file

python -c "

import pandas as pd

try:

    df = pd.read_excel('data/annotations/annotator_1_urgency.xlsx')

    print(f'Rows: {len(df)}')

    print(f'Columns: {df.columns.tolist()}')

except Exception as e:

    print(f'Error: {e}')

"

 

# Restore from archive

ls -lh data/archive/

 

# Extract archive

tar -xzf data/archive/backup_20250126_103000.tar.gz -C data/archive/

 

# Copy Excel file

cp data/archive/backup_20250126_103000/annotations/annotator_1_urgency.xlsx \

   data/annotations/

 

# Resync checkpoint

python -c "

from src.storage.excel_manager import ExcelAnnotationManager

import redis

 

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

mgr = ExcelAnnotationManager('data/annotations', r)

synced = mgr.sync_checkpoint_from_excel(1, 'urgency')

print(f'Synced {synced} samples')

"

```

 

#### 4. Rate Limit Errors

 

**Symptoms:**

- Frequent rate limit errors in logs

- Workers pausing frequently

- Slow progress

 

**Solutions:**

 

```bash

# Check rate limit settings

grep "rate_limit" config/annotators.yaml

 

# Reduce rate limit

make edit-config TYPE=annotators

# Change rate_limit from 60 to 30

 

# Check current rate limit status

redis-cli hgetall ratelimit:1

 

# Monitor rate limiting

watch -n 1 'redis-cli hgetall ratelimit:1'

 

# Increase workers to distribute load

# (But ensure total rate stays within limits)

```

 

#### 5. Disk Space Issues

 

**Symptoms:**

- Excel files not growing

- Write errors in logs

- System slowdown

 

**Solutions:**

 

```bash

# Check disk space

df -h

 

# Check data directory size

du -sh data/

 

# Check Excel file sizes

make excel-stats

 

# Clean up old archives

rm data/archive/old_backup_*.tar.gz

 

# Consolidate and compress

make consolidate

gzip data/consolidated_annotations_*.xlsx

```

 

#### 6. Memory Issues

 

**Symptoms:**

- Workers killed by OS

- OOM (Out of Memory) errors

- System slowdown

 

**Solutions:**

 

```bash

# Check memory usage

free -h

 

# Check worker memory

ps aux | grep celery

 

# Reduce concurrency

make edit-config TYPE=workers

# Change concurrency from 1 to 1 (already optimal)

 

# Reduce number of workers

# Stop some workers

make stop-all

# Edit workers.yaml to disable some workers

make start-workers

 

# Increase system swap

sudo swapon --show

```

 

### Debug Mode

 

**Enable Debug Logging:**

 

```bash

# Edit worker launch command

# In src/workers/launcher.py, change:

# "--loglevel=info" to "--loglevel=debug"

 

# Or start single worker in debug mode

celery -A src.core.celery_app worker \

  -Q annotator_1_urgency \

  -c 1 \

  --loglevel=debug \

  --logfile=debug.log

```

 

**Python Debugger:**

 

```python

# Add breakpoint in code

import pdb; pdb.set_trace()

 

# Or use VS Code debugger (see VSCode Integration section)

```

 

### Getting Help

 

**Check Logs:**

 

```bash

# Worker logs

tail -f data/logs/*.log

 

# Admin audit log

tail -f data/admin_audit.log

 

# Redis logs (if using Docker)

docker logs redis

```

 

**Check Redis State:**

 

```bash

# List all keys

redis-cli keys "*"

 

# Check specific worker

redis-cli hgetall worker:1:urgency

 

# Check checkpoint

redis-cli smembers checkpoint:1:urgency

 

# Check queue length

redis-cli llen annotator_1_urgency

```

 

**System Info:**

 

```bash

# Show system metrics

make metrics

 

# Show all worker status

make status

 

# Show Excel file info

make excel-stats

```

 

---

 

## API Reference

 

### Python API Usage

 

#### ControlAPI

 

```python

from src.api.control import ControlAPI

import redis

 

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

api = ControlAPI(redis_client)

 

# Execute command

result = api.execute_command('pause', annotator_id=1, domain='urgency')

 

# Bulk operation

result = api.bulk_operation('pause', targets=[(1, 'urgency'), (2, 'therapeutic')])

 

# Get global status

status = api.get_global_status()

 

# Consolidate progress

consolidation = api.consolidate_progress()

 

# Verify data integrity

verification = api.verify_data_integrity()

 

# Get queue stats

queue_stats = api.get_queue_stats()

```

 

#### WorkerController

 

```python

from src.workers.controller import WorkerController

import redis

 

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

controller = WorkerController(redis_client)

 

# Pause worker

success = controller.pause_worker(1, 'urgency')

 

# Resume worker

success = controller.resume_worker(1, 'urgency')

 

# Stop worker

success = controller.stop_worker(1, 'urgency', force=False)

 

# Restart worker

success = controller.restart_worker(1, 'urgency')

 

# Get status

status = controller.get_worker_status(1, 'urgency')

 

# Get active tasks

tasks = controller.get_active_tasks(1, 'urgency')

 

# Flush Excel buffer

flushed_rows = controller.flush_excel_buffer(1, 'urgency')

 

# Bulk operations

pause_results = controller.pause_all()

resume_results = controller.resume_all()

stop_results = controller.stop_all()

flush_results = controller.flush_all_excel_buffers()

```

 

#### WorkerMonitor

 

```python

from src.workers.monitor import WorkerMonitor

import redis

 

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

monitor = WorkerMonitor(redis_client)

 

# Check worker health

health = monitor.check_worker_health(1, 'urgency')

 

# Get all worker statuses

statuses = monitor.get_all_worker_statuses()

 

# Get system metrics

metrics = monitor.get_system_metrics()

 

# Detect stalled workers

stalled = monitor.detect_stalled_workers(threshold_seconds=60)

 

# Detect error workers

error_workers = monitor.detect_error_workers(error_threshold=20.0)

 

# Auto-restart stalled workers

restarted_count = monitor.restart_stalled_workers()

 

# Verify Excel integrity

integrity = monitor.verify_excel_integrity()

 

# Get Excel file sizes

sizes = monitor.get_excel_file_sizes()

 

# Collect metrics

monitor.collect_all_metrics()

```

 

#### AdminOperations

 

```python

from src.admin.operations import AdminOperations

import redis

 

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

admin = AdminOperations(redis_client)

 

# Reset domain

result = admin.reset_domain(1, 'urgency', keep_excel=True)

 

# Reset annotator

result = admin.reset_annotator(1, keep_excel=True)

 

# Factory reset

result = admin.factory_reset(confirm=True)

 

# Archive data

archive_path = admin.archive_data('backup_20250126', compress=True)

 

# Export state

state_file = admin.export_state('data/state_backup.json')

 

# Import state

result = admin.import_state('data/state_backup.json', merge=False)

 

# Consolidate Excel files

result = admin.consolidate_excel_files()

```

 

### Redis Key Patterns

 

**Checkpoints:**

- `checkpoint:{annotator_id}:{domain}` - Set of completed sample IDs

 

**Worker Metadata:**

- `worker:{annotator_id}:{domain}` - Hash with worker state

 

**Progress:**

- `progress:{annotator_id}:{domain}` - Hash with progress metrics

 

**Rate Limits:**

- `ratelimit:{annotator_id}` - Hash with token bucket state

 

**Malforms:**

- `malform:{annotator_id}:{domain}:{sample_id}` - Hash with malform data

- `malform_count:{annotator_id}:{domain}` - Sorted set with counts

 

**Metrics:**

- `metrics:{annotator_id}:{domain}` - Hash with aggregated metrics

- `task_metrics:{annotator_id}:{domain}` - Hash with task metrics

 

**Logs:**

- `log:events` - Sorted set with log entries

 

**Locks:**

- `lock:operation:{operation_type}` - Lock for concurrent operations

 

---

 

## VSCode Integration

 

### Using VSCode Tasks

 

**Access Tasks:**

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)

2. Type "Tasks: Run Task"

3. Select task from list

 

**Or use keyboard shortcut:**

- `Ctrl+Shift+B` - Run build task (Start All Workers)

 

**Available Tasks:**

 

| Task | Description |

|------|-------------|

| Start All Workers | Launch all 30 workers |

| Dashboard | Open Rich TUI dashboard |

| Pause Worker (Interactive) | Pause specific worker |

| Resume Worker (Interactive) | Resume specific worker |

| Flush Excel Buffer | Flush buffer for worker |

| View Excel File | Open Excel viewer |

| Verify All Excel Files | Check integrity |

| Consolidate Excel Files | Merge all files |

| Kill All Workers | Stop all workers |

| Edit Config | Open config file |

| View Logs | Tail worker logs |

| Reset Domain | Reset specific domain |

| Archive Current State | Create backup |

| Start Redis | Launch Redis container |

| Stop Redis | Stop Redis container |

| Interactive Shell | Open interactive REPL |

| Run Tests | Execute test suite |

 

### Using Debug Configurations

 

**Start Debugging:**

1. Go to Run & Debug (Ctrl+Shift+D)

2. Select configuration from dropdown

3. Press F5 or click "Start Debugging"

 

**Available Configurations:**

 

| Configuration | Purpose |

|---------------|---------|

| Debug Single Worker | Debug a specific worker |

| Debug Dashboard | Debug the TUI dashboard |

| Debug Excel Viewer | Debug Excel viewer |

| Debug Interactive Shell | Debug the REPL |

| Debug Start All | Debug worker startup |

| Debug Admin Script | Debug admin operations |

| Debug CLI Commands | Debug CLI commands |

| Run Tests | Run tests in debug mode |

 

**Set Breakpoints:**

- Click in left margin next to line number

- Or press F9 on current line

 

**Debug Controls:**

- F5: Continue

- F10: Step Over

- F11: Step Into

- Shift+F11: Step Out

- Ctrl+Shift+F5: Restart

- Shift+F5: Stop

 

### Workspace Settings

 

VSCode is configured with:

- Python interpreter: `venv/bin/python`

- Testing: pytest enabled

- Linting: pylint and flake8

- Formatting: black (on save)

- File associations for YAML and Makefile

- PYTHONPATH set in terminal

 

---

 

## Advanced Usage

 

### Custom Task Processing

 

**Write Custom Task:**

 

```python

# In src/core/tasks.py

 

from celery import shared_task

from src.core.celery_app import celery_app

 

@shared_task(bind=True)

def custom_processing_task(self, sample_id, text, custom_param):

    """Custom processing task"""

    # Your custom logic here

    result = process_custom(text, custom_param)

 

    # Update checkpoint

    checkpoint_manager.mark_completed(

        annotator_id=1,

        domain='custom',

        sample_id=sample_id

    )

 

    return result

```

 

**Queue Custom Task:**

 

```python

from src.core.tasks import custom_processing_task

 

# Queue task

result = custom_processing_task.apply_async(

    kwargs={

        'sample_id': 'CUSTOM-001',

        'text': 'Sample text',

        'custom_param': 'value'

    },

    queue='custom_queue'

)

 

# Get result

task_result = result.get()

```

 

### Custom Domain Configuration

 

**Add New Domain:**

 

1. Edit `config/domains.yaml`:

 

```yaml

domains:

  # ... existing domains ...

 

  - name: "custom_domain"

    description: "Custom domain description"

    valid_labels:

      - "LABEL_A"

      - "LABEL_B"

      - "LABEL_C"

    prompt_template: |

      Your custom prompt here...

 

      Text: {text}

 

      Respond with: <<LABEL_X>>

```

 

2. Add workers in `config/workers.yaml`:

 

```yaml

workers:

  # ... existing workers ...

 

  - annotator_id: 1

    domain: "custom_domain"

    enabled: true

    concurrency: 1

```

 

3. Restart workers:

 

```bash

make stop-all

make validate-config

make start-workers

```

 

### Batch Processing

 

**Process Specific Sample IDs:**

 

```python

from src.core.tasks import annotate_sample

 

# Load specific sample IDs

sample_ids = ['ID-001', 'ID-002', 'ID-003']

 

# Queue tasks

for sample_id in sample_ids:

    # Load sample data

    sample_data = load_sample(sample_id)

 

    # Queue annotation task

    annotate_sample.apply_async(

        kwargs={

            'annotator_id': 1,

            'domain': 'urgency',

            'sample_id': sample_id,

            'text': sample_data['text']

        },

        queue='annotator_1_urgency'

    )

```

 

### Custom Excel Format

 

**Modify Excel Output:**

 

Edit `src/storage/excel_manager.py`:

 

```python

def write_annotation(self, annotator_id, domain, row_data):

    """Write annotation with custom columns"""

 

    # Add custom columns

    row_data['custom_field_1'] = calculate_custom_field_1(row_data)

    row_data['custom_field_2'] = calculate_custom_field_2(row_data)

 

    # Write to Excel

    self._write_to_excel(annotator_id, domain, row_data)

```

 

### Monitoring Hooks

 

**Add Custom Monitoring:**

 

```python

# In src/workers/monitor.py

 

def custom_health_check(self, annotator_id, domain):

    """Custom health check logic"""

 

    # Your custom checks

    custom_metric = calculate_custom_metric(annotator_id, domain)

 

    if custom_metric > threshold:

        # Trigger alert

        send_alert(f"Custom metric high: {custom_metric}")

 

    return custom_metric

```

 

### Integration with External Systems

 

**Webhook Notifications:**

 

```python

import requests

 

def send_webhook_notification(event_type, data):

    """Send webhook on events"""

 

    webhook_url = "https://your-webhook-url.com/events"

 

    payload = {

        'event': event_type,

        'timestamp': datetime.now().isoformat(),

        'data': data

    }

 

    requests.post(webhook_url, json=payload)

 

# Use in tasks

@shared_task(bind=True)

def annotate_sample(self, annotator_id, domain, sample_id, text):

    # ... processing ...

 

    # Send notification

    send_webhook_notification('sample_completed', {

        'annotator_id': annotator_id,

        'domain': domain,

        'sample_id': sample_id,

        'label': label

    })

```

 

---

 

## Appendix

 

### File Structure Reference

 

```

M-Heath-Annotator/

├── config/

│   ├── annotators.yaml        # Annotator configuration

│   ├── domains.yaml            # Domain definitions

│   ├── workers.yaml            # Worker assignments

│   └── settings.yaml           # System settings

├── src/

│   ├── core/                   # Core functionality

│   │   ├── celery_app.py       # Celery application

│   │   ├── config_loader.py    # Config loading

│   │   ├── checkpoint.py       # Checkpoint management

│   │   ├── gemini_client.py    # Gemini API client

│   │   └── tasks.py            # Celery tasks

│   ├── storage/                # Storage layer

│   │   ├── source_loader.py    # Source data loading

│   │   ├── excel_manager.py    # Excel file management

│   │   └── malform_logger.py   # Malform logging

│   ├── workers/                # Worker management

│   │   ├── launcher.py         # Worker launching

│   │   ├── controller.py       # Worker control

│   │   └── monitor.py          # Worker monitoring

│   ├── api/                    # API layer

│   │   └── control.py          # Control API

│   ├── admin/                  # Admin operations

│   │   └── operations.py       # Admin functions

│   ├── cli/                    # CLI tools (Session 4)

│   │   ├── dashboard.py        # Rich TUI dashboard

│   │   ├── excel_viewer.py     # Excel viewer

│   │   ├── commands.py         # CLI commands

│   │   └── interactive.py      # Interactive shell

│   └── models/                 # Data models

│       └── annotation.py       # Pydantic models

├── scripts/                    # Convenience scripts

│   ├── start_all.py            # Start all workers

│   ├── dashboard.py            # Dashboard entry

│   ├── admin.py                # Admin CLI

│   ├── config_editor.py        # Config editor

│   └── excel_viewer.py         # Excel viewer entry

├── tests/                      # Test suite

│   ├── test_core/

│   ├── test_storage/

│   ├── test_workers/

│   └── test_models/

├── data/                       # Data directory

│   ├── source/                 # Source datasets

│   ├── annotations/            # Excel output files

│   ├── logs/                   # Worker logs

│   ├── checkpoints/            # Checkpoint data

│   ├── malform_logs/           # Malform logs

│   ├── archive/                # Archives

│   └── exports/                # Exported data

├── .vscode/                    # VSCode config

│   ├── tasks.json              # Tasks

│   ├── launch.json             # Debug configs

│   └── settings.json           # Settings

├── Makefile                    # Make targets

├── requirements.txt            # Python dependencies

├── docker-compose.yml          # Docker services

├── SESSION_1_DOCUMENTATION.md

├── SESSION_2_DOCUMENTATION.md

├── SESSION_3_DOCUMENTATION.md

├── SESSION_4_DOCUMENTATION.md

└── FINAL_README.md            # This file

```

 

### Quick Command Reference

 

```bash

# Installation

make install setup start-redis

 

# Start system

make start-workers

 

# Monitor

make dashboard          # Rich TUI

make interactive        # Interactive shell

make status            # Quick status

 

# Control

make pause A=1 D=urgency

make resume A=1 D=urgency

make flush A=1 D=urgency

make stop-all

 

# Excel

make view-excel A=1 D=urgency

make verify-excel

make consolidate

 

# Admin

make archive NAME=backup

make reset A=1 D=urgency

make factory-reset

 

# Testing

make test

make test-fast

make lint

 

# Cleanup

make clean

```

 

### Environment Variables

 

```bash

# Optional environment variables

 

# Redis connection

export REDIS_HOST=localhost

export REDIS_PORT=6379

 

# Celery broker

export CELERY_BROKER_URL=redis://localhost:6379/0

 

# Editor for config editing

export EDITOR=nano  # or vim, code, etc.

 

# Log level

export LOG_LEVEL=INFO  # or DEBUG, WARNING, ERROR

```

 

### Support and Resources

 

**Documentation:**

- Session 1: Core infrastructure

- Session 2: Annotation engine

- Session 3: Worker management

- Session 4: CLI dashboard (this guide)

 

**GitHub Issues:**

- Report bugs

- Request features

- Ask questions

 

**Logs:**

- Worker logs: `data/logs/*.log`

- Admin audit: `data/admin_audit.log`

- Redis logs: `docker logs redis`

 

---

 

## Summary

 

This system provides a comprehensive platform for distributed mental health annotation with:

 

✅ **30 Parallel Workers** - High throughput processing

✅ **Real-time Monitoring** - Rich TUI dashboard

✅ **Checkpoint Recovery** - Resume from crashes

✅ **Excel Storage** - Human-readable output

✅ **Interactive Tools** - CLI commands and shell

✅ **VSCode Integration** - Developer productivity

✅ **Comprehensive Testing** - 91% code coverage

✅ **Production Ready** - Tested and documented

 

**For questions or support, refer to the session-specific documentation or create a GitHub issue.**

 

---

 

**Built with ❤️ for mental health research**

 

*Complete System Guide - November 2025*