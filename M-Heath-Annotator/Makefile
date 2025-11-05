.PHONY: install setup start-redis start-workers dashboard stop-all reset clean test consolidate view-excel verify-excel archive factory-reset interactive

# ═══════════════════════════════════════════════════════════
# Installation & Setup
# ═══════════════════════════════════════════════════════════

install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt

setup:
	@echo "Setting up project structure..."
	mkdir -p data/logs data/checkpoints data/malform_logs data/annotations data/source data/archive data/exports
	@if [ ! -f .env ]; then \
		echo "Creating .env file..."; \
		cp .env.example .env 2>/dev/null || echo "No .env.example found, skipping"; \
	fi
	@echo "Setup complete!"

# ═══════════════════════════════════════════════════════════
# Infrastructure
# ═══════════════════════════════════════════════════════════

start-redis:
	@echo "Starting Redis..."
	docker-compose up -d redis
	@echo "Waiting for Redis to be ready..."
	@sleep 2
	@docker-compose ps redis

stop-redis:
	@echo "Stopping Redis..."
	docker-compose stop redis

# ═══════════════════════════════════════════════════════════
# Worker Management
# ═══════════════════════════════════════════════════════════

start-workers:
	@echo "Starting all workers..."
	python scripts/start_all.py

start-annotator:
	@if [ -z "$(A)" ]; then \
		echo "Error: Annotator ID required. Usage: make start-annotator A=1"; \
		exit 1; \
	fi
	@echo "Starting workers for annotator $(A)..."
	python scripts/start_all.py --annotator $(A)

start-domain:
	@if [ -z "$(D)" ]; then \
		echo "Error: Domain required. Usage: make start-domain D=urgency"; \
		exit 1; \
	fi
	@echo "Starting workers for domain $(D)..."
	python scripts/start_all.py --domain $(D)

stop-all:
	@echo "Stopping all workers..."
	python -m src.cli.commands worker stop --all

pause-all:
	@echo "Pausing all workers..."
	python -m src.cli.commands worker pause-all

resume-all:
	@echo "Resuming all workers..."
	python -m src.cli.commands worker resume-all

# ═══════════════════════════════════════════════════════════
# Worker Control (Individual)
# ═══════════════════════════════════════════════════════════

pause:
	@if [ -z "$(A)" ] || [ -z "$(D)" ]; then \
		echo "Error: Annotator and Domain required. Usage: make pause A=1 D=urgency"; \
		exit 1; \
	fi
	@echo "Pausing worker $(A):$(D)..."
	python -m src.cli.commands worker pause --annotator $(A) --domain $(D)

resume:
	@if [ -z "$(A)" ] || [ -z "$(D)" ]; then \
		echo "Error: Annotator and Domain required. Usage: make resume A=1 D=urgency"; \
		exit 1; \
	fi
	@echo "Resuming worker $(A):$(D)..."
	python -m src.cli.commands worker resume --annotator $(A) --domain $(D)

flush:
	@if [ -z "$(A)" ] || [ -z "$(D)" ]; then \
		echo "Flushing all Excel buffers..."; \
		python -m src.cli.commands worker flush; \
	else \
		echo "Flushing Excel buffer for $(A):$(D)..."; \
		python -m src.cli.commands worker flush --annotator $(A) --domain $(D); \
	fi

status:
	@if [ -z "$(A)" ] || [ -z "$(D)" ]; then \
		echo "Getting status for all workers..."; \
		python -m src.cli.commands worker status; \
	else \
		echo "Getting status for $(A):$(D)..."; \
		python -m src.cli.commands worker status --annotator $(A) --domain $(D); \
	fi

# ═══════════════════════════════════════════════════════════
# Monitoring
# ═══════════════════════════════════════════════════════════

dashboard:
	@echo "Launching dashboard..."
	python scripts/dashboard.py

interactive:
	@echo "Launching interactive shell..."
	python -m src.cli.interactive

metrics:
	@echo "System metrics:"
	python -m src.cli.commands monitor metrics

logs:
	@echo "Viewing logs (Ctrl+C to exit)..."
	tail -f data/logs/*.log

# ═══════════════════════════════════════════════════════════
# Excel Operations
# ═══════════════════════════════════════════════════════════

view-excel:
	@if [ -z "$(A)" ] || [ -z "$(D)" ]; then \
		echo "Error: Annotator and Domain required. Usage: make view-excel A=1 D=urgency"; \
		exit 1; \
	fi
	@echo "Opening Excel viewer for $(A):$(D)..."
	python scripts/excel_viewer.py --annotator $(A) --domain $(D)

verify-excel:
	@echo "Verifying all Excel files..."
	python -m src.cli.commands excel verify-all

consolidate:
	@echo "Consolidating Excel files..."
	python -m src.cli.commands admin consolidate
	@if [ -n "$(OUTPUT)" ]; then \
		echo "Output will be saved to: $(OUTPUT)"; \
	fi

excel-stats:
	@echo "Excel File Statistics:"
	@echo "======================"
	@if [ -d "data/annotations" ]; then \
		du -sh data/annotations/*.xlsx 2>/dev/null | sort -h || echo "No Excel files found"; \
		echo ""; \
		echo "Row counts:"; \
		for f in data/annotations/*.xlsx; do \
			if [ -f "$$f" ]; then \
				rows=$$(python -c "import pandas as pd; print(len(pd.read_excel('$$f')))" 2>/dev/null || echo "?"); \
				echo "$$(basename $$f): $$rows rows"; \
			fi; \
		done; \
	else \
		echo "No annotations directory found"; \
	fi

# ═══════════════════════════════════════════════════════════
# Administrative Operations
# ═══════════════════════════════════════════════════════════

reset:
	@if [ -z "$(A)" ] || [ -z "$(D)" ]; then \
		echo "Error: Annotator and Domain required. Usage: make reset A=1 D=urgency"; \
		exit 1; \
	fi
	@echo "Resetting worker $(A):$(D)..."
	python scripts/admin.py reset --annotator $(A) --domain $(D) $(if $(KEEP),--keep-excel,)

factory-reset:
	@echo "WARNING: This will delete all data!"
	@echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
	@sleep 5
	@echo "Performing factory reset..."
	python scripts/admin.py factory-reset --confirm

archive:
	@if [ -z "$(NAME)" ]; then \
		NAME="backup_$$(date +%Y%m%d_%H%M%S)"; \
	fi; \
	echo "Creating archive: $$NAME..."; \
	python scripts/admin.py archive $$NAME

# ═══════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════

edit-config:
	@if [ -z "$(TYPE)" ]; then \
		echo "Error: Config type required. Usage: make edit-config TYPE=annotators"; \
		echo "Valid types: annotators, domains, workers, settings"; \
		exit 1; \
	fi
	@echo "Editing $(TYPE) config..."
	python scripts/config_editor.py $(TYPE)

validate-config:
	@echo "Validating configurations..."
	python -m src.cli.commands config validate

# ═══════════════════════════════════════════════════════════
# Testing & Quality
# ═══════════════════════════════════════════════════════════

test:
	@echo "Running tests..."
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

test-fast:
	@echo "Running fast tests (no coverage)..."
	pytest tests/ -v

lint:
	@echo "Running linters..."
	flake8 src/ tests/
	black --check src/ tests/

format:
	@echo "Formatting code..."
	black src/ tests/

type-check:
	@echo "Type checking..."
	mypy src/

# ═══════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════

clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	@echo "Cleanup complete!"

clean-data:
	@echo "WARNING: This will delete all annotations, logs, and malform logs!"
	@echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
	@sleep 5
	@echo "Cleaning data..."
	rm -rf data/annotations/* data/logs/* data/malform_logs/* data/exports/*
	@echo "Data cleanup complete!"

clean-all: clean clean-data
	@echo "Full cleanup complete!"

# ═══════════════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════════════

help:
	@echo "Mental Health Annotation System - Makefile"
	@echo "==========================================="
	@echo ""
	@echo "Installation & Setup:"
	@echo "  make install         - Install Python dependencies"
	@echo "  make setup           - Create directory structure"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make start-redis     - Start Redis container"
	@echo "  make stop-redis      - Stop Redis container"
	@echo ""
	@echo "Worker Management:"
	@echo "  make start-workers   - Start all workers"
	@echo "  make stop-all        - Stop all workers"
	@echo "  make pause-all       - Pause all workers"
	@echo "  make resume-all      - Resume all workers"
	@echo "  make pause A=1 D=urgency - Pause specific worker"
	@echo "  make resume A=1 D=urgency - Resume specific worker"
	@echo "  make status          - Show all worker status"
	@echo "  make flush           - Flush all Excel buffers"
	@echo ""
	@echo "Monitoring:"
	@echo "  make dashboard       - Launch Rich TUI dashboard"
	@echo "  make interactive     - Launch interactive shell"
	@echo "  make metrics         - Show system metrics"
	@echo "  make logs            - Tail worker logs"
	@echo ""
	@echo "Excel Operations:"
	@echo "  make view-excel A=1 D=urgency - View Excel file"
	@echo "  make verify-excel    - Verify all Excel files"
	@echo "  make consolidate     - Consolidate all Excel files"
	@echo "  make excel-stats     - Show Excel file statistics"
	@echo ""
	@echo "Administrative:"
	@echo "  make reset A=1 D=urgency - Reset specific worker"
	@echo "  make archive NAME=backup - Create archive"
	@echo "  make factory-reset   - Factory reset (DESTRUCTIVE)"
	@echo ""
	@echo "Configuration:"
	@echo "  make edit-config TYPE=annotators - Edit config"
	@echo "  make validate-config - Validate all configs"
	@echo ""
	@echo "Testing:"
	@echo "  make test            - Run tests with coverage"
	@echo "  make test-fast       - Run tests without coverage"
	@echo "  make lint            - Run linters"
	@echo "  make format          - Format code"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           - Clean Python artifacts"
	@echo "  make clean-data      - Delete all data (DESTRUCTIVE)"
	@echo ""

.DEFAULT_GOAL := help
