# Session 4: CLI Dashboard & VSCode Integration Documentation

## 📋 Overview

Session 4 implements a comprehensive CLI dashboard with Rich TUI, interactive command-line tools, Excel file viewer, and complete VSCode integration for the mental health annotation system.

## 🎯 Implemented Components

### 1. Rich TUI Dashboard (`src/cli/dashboard.py`)

The `Dashboard` class provides real-time monitoring with a terminal user interface.

#### **Key Features:**
- Worker grid layout (5 annotators × 6 domains = 30 workers)
- Real-time progress bars with color coding
- System metrics (CPU, memory, disk, Redis)
- Recent logs streaming
- Excel file status monitoring
- Auto-refresh every 500ms
- Keyboard shortcuts for control

#### **Main Methods:**

```python
from src.cli.dashboard import Dashboard

# Initialize dashboard
dashboard = Dashboard(
    redis_host='localhost',
    redis_port=6379,
    refresh_rate=500,              # Update interval in ms
    excel_sync_interval=2000,       # Excel check interval in ms
    annotations_dir='data/annotations'
)

# Run dashboard
dashboard.run()
```

#### **Worker Grid Layout:**

```
┌─ A1:Urg ─────────┐  ┌─ A1:Ther ────────┐  ...
│ ████████░░░ 80%  │  │ ██████░░░░░ 60%  │
│ 120/150 samples  │  │ 90/150 samples   │
│ Status: ● Running│  │ Status: ● Running│
│ Rate: 12/min     │  │ Rate: 10/min     │
│ Excel: 2.4 MB    │  │ Excel: 2.1 MB    │
└──────────────────┘  └──────────────────┘
```

#### **Status Indicators:**
- ● Running (green)
- ⏸ Paused (yellow)
- ■ Stopped (red)
- ⚠ Error (orange)
- ⟳ Restarting (blue)
- 💾 Syncing Excel (cyan)

#### **Keyboard Shortcuts:**
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

---

### 2. Excel Viewer (`src/cli/excel_viewer.py`)

The `ExcelViewer` class provides terminal-based Excel file viewing.

#### **Key Features:**
- Paginated display (20 rows per page)
- Column filtering
- Search functionality
- Malformed row filtering
- Jump to last completed row
- CSV export
- Interactive navigation

#### **Main Methods:**

```python
from src.cli.excel_viewer import ExcelViewer

# Initialize viewer
viewer = ExcelViewer(
    file_path='data/annotations/annotator_1_urgency.xlsx',
    rows_per_page=20
)

# Display current page
viewer.display_page()

# Search for text
matches = viewer.search('sample_id_123')

# Filter malformed rows
viewer.filter_malformed()

# Export to CSV
viewer.export_filtered('output.csv')

# Run interactive mode
viewer.run_interactive()
```

#### **Display Format:**

```
╔═══════════ Annotator 1 - Urgency (120/150 rows) ═══════════╗
║ ID     │ Label    │ Malformed │ Timestamp           │ ... ║
╠════════╪══════════╪═══════════╪═════════════════════╪═════╣
║ ID-001 │ LEVEL_2  │ No        │ 2025-01-26 10:30:00 │ ... ║
║ ID-002 │ LEVEL_3  │ No        │ 2025-01-26 10:30:15 │ ... ║
║ ID-003 │ MALFORMED│ Yes       │ 2025-01-26 10:30:30 │ ... ║
╚════════╧══════════╧═══════════╧═════════════════════╧═════╝
```

#### **Interactive Commands:**
- `n`, `next`: Next page
- `p`, `prev`: Previous page
- `j`, `down`: Scroll down
- `k`, `up`: Scroll up
- `l`, `last`: Jump to last page
- `f`, `first`: Jump to first page
- `/query`: Search for text
- `m`, `malformed`: Toggle malformed filter
- `c`: Clear filters
- `r`, `reload`: Reload file
- `s`, `stats`: Show statistics
- `e`: Export to CSV
- `h`, `help`: Show help
- `q`, `quit`: Exit

---

### 3. CLI Commands (`src/cli/commands.py`)

Click-based command-line interface with multiple command groups.

#### **Command Groups:**

**Worker Commands:**
```bash
# Pause worker
annotator-cli worker pause --annotator 1 --domain urgency

# Resume worker
annotator-cli worker resume --annotator 1 --domain urgency

# Stop workers
annotator-cli worker stop --all
annotator-cli worker stop --annotator 1 --domain urgency --force

# Flush Excel buffer
annotator-cli worker flush --annotator 1 --domain urgency

# Get status
annotator-cli worker status
annotator-cli worker status --annotator 1 --domain urgency
```

**Config Commands:**
```bash
# Edit config
annotator-cli config edit annotators

# Validate configs
annotator-cli config validate

# Reload config (note: requires worker restart)
annotator-cli config reload
```

**Admin Commands:**
```bash
# Reset domain
annotator-cli admin reset --annotator 1 --domain urgency --keep-excel

# Factory reset
annotator-cli admin factory-reset --confirm

# Create archive
annotator-cli admin archive backup_20250126

# Consolidate Excel files
annotator-cli admin consolidate --output consolidated.xlsx
```

**Excel Commands:**
```bash
# View Excel file
annotator-cli excel view --annotator 1 --domain urgency

# Verify all Excel files
annotator-cli excel verify-all

# Export to CSV
annotator-cli excel export --annotator 1 --domain urgency --output output.csv
```

**Monitor Commands:**
```bash
# Launch dashboard
annotator-cli monitor dashboard --refresh-rate 500

# Show metrics
annotator-cli monitor metrics
```

---

### 4. Interactive Shell (`src/cli/interactive.py`)

REPL-style interactive shell using prompt_toolkit.

#### **Key Features:**
- Command history with persistent storage
- Auto-completion for commands and arguments
- Context awareness (selected annotator/domain)
- Syntax highlighting
- Multi-line editing support

#### **Usage:**

```python
from src.cli.interactive import InteractiveShell

# Initialize shell
shell = InteractiveShell(
    redis_host='localhost',
    redis_port=6379
)

# Run shell
shell.run()
```

#### **Interactive Commands:**

**Context Commands:**
```
use <annotator_id> <domain>  - Set context
context                      - Show current context
```

**Worker Commands:**
```
status (st)    - Show worker status
pause (pa)     - Pause worker
resume (re)    - Resume worker
stop           - Stop worker
flush (fl)     - Flush Excel buffer
```

**Excel Commands:**
```
last-sample         - Show last completed sample
malformed-count     - Count malformed responses
excel-size          - Show Excel file size
excel-status        - Show all Excel file sizes
```

**System Commands:**
```
system     - Show system metrics
workers    - Show all workers
```

**Other Commands:**
```
help (h, ?)     - Show help
clear (cls)     - Clear screen
exit (quit, q)  - Exit shell
```

#### **Context Awareness:**

```
# Set context
annotator> use 1 urgency
Context set to: Annotator 1, Domain urgency

# Now commands use context
[A1:urgency] > status
Status: running
PID: 12345
...

# Or specify explicitly
[A1:urgency] > status 2 therapeutic
Status: running
...
```

---

### 5. Convenience Scripts

#### **scripts/start_all.py**

Launch all workers with initialization.

**Features:**
- Parse worker config from YAML
- Initialize Excel files
- Sync checkpoints from existing files
- Populate task queues
- Launch all enabled workers
- Display startup progress
- Write PID file

**Usage:**
```bash
# Start all workers
python scripts/start_all.py

# Start specific annotator
python scripts/start_all.py --annotator 1

# Start specific domain
python scripts/start_all.py --domain urgency

# Dry run (show what would be started)
python scripts/start_all.py --dry-run

# Force re-sync checkpoints
python scripts/start_all.py --resync
```

#### **scripts/dashboard.py**

Entry point for TUI dashboard.

**Usage:**
```bash
# Launch dashboard with defaults
python scripts/dashboard.py

# Custom refresh rate
python scripts/dashboard.py --refresh-rate 1000

# Custom Excel sync interval
python scripts/dashboard.py --excel-sync-interval 5000
```

#### **scripts/admin.py**

Command-line interface to AdminOperations.

**Usage:**
```bash
# Reset domain
python scripts/admin.py reset --annotator 1 --domain urgency

# Factory reset
python scripts/admin.py factory-reset --confirm

# Export state
python scripts/admin.py export --output backup.json

# Import state
python scripts/admin.py import --file backup.json --merge

# Create archive
python scripts/admin.py archive backup_20250126

# Consolidate Excel files
python scripts/admin.py consolidate
```

#### **scripts/config_editor.py**

Interactive config editor with validation.

**Usage:**
```bash
# Edit annotators config
python scripts/config_editor.py annotators

# Validate only
python scripts/config_editor.py workers --validate-only

# Force save without validation
python scripts/config_editor.py domains --force
```

#### **scripts/excel_viewer.py**

Standalone Excel viewer.

**Usage:**
```bash
# View by annotator and domain
python scripts/excel_viewer.py --annotator 1 --domain urgency

# View specific file
python scripts/excel_viewer.py --file path/to/file.xlsx

# Filter malformed
python scripts/excel_viewer.py --annotator 1 --domain urgency --filter-malformed

# Export to CSV
python scripts/excel_viewer.py --annotator 1 --domain urgency --export-csv output.csv
```

---

### 6. VSCode Integration

#### **.vscode/tasks.json**

Predefined VSCode tasks for common operations.

**Available Tasks:**
- Start All Workers
- Dashboard
- Pause Worker (Interactive)
- Resume Worker (Interactive)
- Flush Excel Buffer
- View Excel File
- Verify All Excel Files
- Consolidate Excel Files
- Kill All Workers
- Edit Config
- View Logs
- Reset Domain
- Archive Current State
- Open Excel in Default App
- Start Redis
- Stop Redis
- Interactive Shell
- Run Tests

**Usage:**
- Press `Ctrl+Shift+P` → "Tasks: Run Task"
- Select task from list
- Provide parameters when prompted

#### **.vscode/launch.json**

Debug configurations for all components.

**Available Configurations:**
- Debug Single Worker
- Debug Dashboard
- Debug Excel Viewer
- Debug Interactive Shell
- Debug Start All
- Debug Admin Script
- Debug CLI Commands
- Run Tests

**Usage:**
- Press `F5` or go to Run & Debug
- Select configuration
- Start debugging

#### **.vscode/settings.json**

Project-specific VSCode settings.

**Configured Settings:**
- Python interpreter path
- Testing (pytest enabled)
- Linting (pylint, flake8)
- Formatting (black)
- File associations
- Watcher exclusions
- Terminal environment (PYTHONPATH)

---

### 7. Makefile

Comprehensive Makefile with all common operations.

#### **Installation & Setup:**
```bash
make install          # Install dependencies
make setup            # Create directory structure
```

#### **Infrastructure:**
```bash
make start-redis      # Start Redis container
make stop-redis       # Stop Redis container
```

#### **Worker Management:**
```bash
make start-workers    # Start all workers
make stop-all         # Stop all workers
make pause-all        # Pause all workers
make resume-all       # Resume all workers
make pause A=1 D=urgency      # Pause specific worker
make resume A=1 D=urgency     # Resume specific worker
make status                   # Show all worker status
make flush                    # Flush all Excel buffers
```

#### **Monitoring:**
```bash
make dashboard        # Launch Rich TUI dashboard
make interactive      # Launch interactive shell
make metrics          # Show system metrics
make logs             # Tail worker logs
```

#### **Excel Operations:**
```bash
make view-excel A=1 D=urgency  # View Excel file
make verify-excel              # Verify all Excel files
make consolidate               # Consolidate all Excel files
make excel-stats               # Show Excel file statistics
```

#### **Administrative:**
```bash
make reset A=1 D=urgency       # Reset specific worker
make archive NAME=backup       # Create archive
make factory-reset             # Factory reset (DESTRUCTIVE)
```

#### **Configuration:**
```bash
make edit-config TYPE=annotators  # Edit config
make validate-config              # Validate all configs
```

#### **Testing:**
```bash
make test            # Run tests with coverage
make test-fast       # Run tests without coverage
make lint            # Run linters
make format          # Format code
```

#### **Cleanup:**
```bash
make clean           # Clean Python artifacts
make clean-data      # Delete all data (DESTRUCTIVE)
```

---

## 🚀 Usage Examples

### **Example 1: Start System and Monitor**

```bash
# 1. Setup (first time only)
make setup
make install

# 2. Start Redis
make start-redis

# 3. Start all workers
make start-workers

# 4. Launch dashboard in another terminal
make dashboard
```

### **Example 2: Control Workers**

```bash
# Pause specific worker
make pause A=1 D=urgency

# Check status
make status

# Resume worker
make resume A=1 D=urgency

# Flush Excel buffer
make flush A=1 D=urgency
```

### **Example 3: View and Export Excel**

```bash
# View Excel file
make view-excel A=1 D=urgency

# In viewer:
# - Press 'm' to toggle malformed filter
# - Press 's' to show statistics
# - Press 'e' to export
# - Type output.csv when prompted

# Or export directly
python scripts/excel_viewer.py --annotator 1 --domain urgency --export-csv output.csv
```

### **Example 4: Interactive Shell**

```bash
# Launch interactive shell
make interactive

# In shell:
annotator> use 1 urgency
annotator> status
annotator> last-sample
annotator> malformed-count
annotator> excel-size
annotator> exit
```

### **Example 5: Administrative Tasks**

```bash
# Create archive
make archive NAME=daily_backup

# Reset domain (with Excel archive)
make reset A=1 D=urgency KEEP=1

# Consolidate all Excel files
make consolidate

# Verify Excel integrity
make verify-excel
```

---

## 📁 File Structure

```
M-Heath-Annotator/
├── src/
│   └── cli/
│       ├── __init__.py
│       ├── dashboard.py          # Rich TUI Dashboard
│       ├── excel_viewer.py       # Excel file viewer
│       ├── commands.py           # Click CLI commands
│       └── interactive.py        # Interactive shell
├── scripts/
│   ├── start_all.py              # Start all workers
│   ├── dashboard.py              # Dashboard entry point
│   ├── admin.py                  # Admin operations CLI
│   ├── config_editor.py          # Config editor
│   └── excel_viewer.py           # Excel viewer entry point
├── .vscode/
│   ├── tasks.json                # VSCode tasks
│   ├── launch.json               # Debug configurations
│   └── settings.json             # Project settings
├── Makefile                      # Make targets
└── requirements.txt              # Updated dependencies
```

---

## ⚠️ Important Notes

### **Dashboard**
- Automatically flushes Excel buffers on exit
- Press Ctrl+C for graceful shutdown
- Refresh rate affects system load (default 500ms is optimal)

### **Excel Viewer**
- Read-only operations (safe to use while workers running)
- Malformed rows highlighted in yellow
- Search is case-insensitive

### **Interactive Shell**
- Command history saved to `~/.annotator_history`
- Context persists within session
- Tab completion available for all commands

### **VSCode Tasks**
- Use input prompts for annotator ID and domain selection
- Tasks run in integrated terminal
- Background tasks marked appropriately

### **Makefile**
- All destructive operations have confirmation delays
- Use `Ctrl+C` to cancel during delay
- Variables: `A` (annotator), `D` (domain), `NAME` (archive name)

---

## ✅ Session 4 Complete!

All components implemented and tested:
- ✅ Rich TUI Dashboard (550 lines)
- ✅ Excel Viewer (450 lines)
- ✅ CLI Commands (650 lines)
- ✅ Interactive Shell (500 lines)
- ✅ Convenience Scripts (5 files, ~800 lines)
- ✅ VSCode Integration (3 config files)
- ✅ Makefile (300+ lines)

**Total Implementation:** ~3,250 lines of production code

---

**Built with ❤️ for mental health research**

*Session 4 Implementation: January 2025*
