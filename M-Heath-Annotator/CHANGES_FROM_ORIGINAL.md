# Changes from Original System

This document outlines the key differences between the distributed annotation system and the original Google Colab notebook.

---

## ✅ What Was PRESERVED (100% Identical)

### 1. **All Domain Prompts**
The exact original prompts for all 6 domains are preserved verbatim in `config/domains.yaml`:
- ✅ Urgency Level (LEVEL_0 to LEVEL_4)
- ✅ Therapeutic Approach (TA-1 to TA-9)
- ✅ Intervention Intensity (INT-1 to INT-5)
- ✅ Adjunct Services (ADJ-1 to ADJ-8)
- ✅ Treatment Modality (MOD-1 to MOD-6)
- ✅ Redressal Points (JSON array extraction)

**No modifications** were made to the prompts - they contain the exact same:
- Clinical guidelines
- Step-by-step instructions
- Examples
- Output format requirements

### 2. **AI Model**
- ✅ Uses **Gemma 3 27B IT** (`gemma-3-27b-it`) - exact same model
- ✅ Same Google Gemini API
- Configured in `config/settings.yaml`:
  ```yaml
  model:
    name: gemma-3-27b-it
    provider: google
  ```

### 3. **Response Validation Logic**
- ✅ Same regex patterns for parsing `<< >>` tags
- ✅ Same validation rules per domain
- ✅ Same error classification (parsing_error vs validity_error)
- Location: `src/utils/validators.py`

### 4. **Checkpoint Logic**
- ✅ Same concept: track completed samples per annotator per domain
- ✅ Same resume capability after crashes
- ✅ Enhanced with Redis for distributed coordination

---

## 🔄 What Was CHANGED (Architecture Improvements)

### 1. **Data Source: Google Sheets → Local Excel**

**Original:**
```python
# Used Google Sheets API
gspread.authorize(creds)
source_ss = gc.open("M-Help Dataset")
```

**New:**
```python
# Uses local Excel file
loader = ExcelDataLoader("data/mhelp_dataset.xlsx")
df = loader.load_all_sheets()  # Loads Train, Validation, Test
```

**Benefits:**
- ✅ No need for Google authentication
- ✅ Faster data loading
- ✅ Works offline
- ✅ Easier to version control dataset
- ✅ No API quotas or rate limits

**Configuration:** `config/settings.yaml`
```yaml
data:
  source_type: excel
  excel_path: data/mhelp_dataset.xlsx
  sheets:
    - Train
    - Validation
    - Test
```

### 2. **Execution: Sequential → Distributed**

**Original:**
```python
# Sequential processing
for domain in DOMAINS:
    for idx, row in samples_df.iterrows():
        annotate_sample(...)
```

**New:**
```python
# Distributed processing with Celery
@app.task
def annotate_sample(annotator_id, domain, sample_id, text):
    # Processed in parallel across 30 queues
```

**Benefits:**
- ✅ 30 parallel workers (5 annotators × 6 domains)
- ✅ True parallelization vs sequential
- ✅ Better crash recovery
- ✅ Real-time monitoring via Flower

### 3. **Checkpointing: JSON File → Redis**

**Original:**
```python
# Saved to local JSON
checkpoint_path = f"{CHECKPOINT_DIR}/annotator_{id}_checkpoint.json"
with open(checkpoint_path, 'w') as f:
    json.dump(checkpoint, f)
```

**New:**
```python
# Redis with atomic operations
checkpoint.mark_completed(annotator_id, domain, sample_id)
# Uses Redis Sets: checkpoint:1:urgency
```

**Benefits:**
- ✅ Distributed coordination (multiple workers can share state)
- ✅ Atomic operations (no race conditions)
- ✅ Faster access
- ✅ Built-in expiration and cleanup

### 4. **Configuration: Hardcoded → YAML**

**Original:**
```python
MODEL_NAME = "gemma-3-27b-it"
ANNOTATOR_ID = 1
DOMAINS = ["Urgency", "Therapeutic", ...]
```

**New:**
```yaml
# config/settings.yaml
model:
  name: gemma-3-27b-it

# config/annotators.yaml
annotators:
  1:
    name: Annotator One
    api_key: YOUR_KEY

# config/domains.yaml
domains:
  urgency:
    prompt_template: |
      (exact original prompt)
```

**Benefits:**
- ✅ Hot-reload without code changes
- ✅ Easier to manage multiple annotators
- ✅ Version control configuration
- ✅ Schema validation with Pydantic

---

## 📊 Comparison Table

| Feature | Original System | New System |
|---------|----------------|------------|
| **Prompts** | ✅ Exact same | ✅ Exact same (preserved) |
| **AI Model** | `gemma-3-27b-it` | ✅ `gemma-3-27b-it` |
| **Data Source** | Google Sheets | Local Excel (.xlsx) |
| **Execution** | Sequential (Colab) | Distributed (Celery) |
| **Parallelization** | None | 30 parallel queues |
| **Checkpointing** | JSON file | Redis (atomic) |
| **Monitoring** | Print statements | Flower web UI |
| **Configuration** | Hardcoded | YAML files |
| **Crash Recovery** | Manual resume | Automatic |
| **Multi-Annotator** | Manual switching | Simultaneous |

---

## 🎯 Core Logic Equivalence

The **annotation logic** is 100% preserved:

```python
# ORIGINAL FLOW
1. Load sample text
2. Build prompt with template.format(text=text)
3. Call Gemini API with gemma-3-27b-it
4. Parse response for << >> tags
5. Validate label against domain rules
6. Mark as completed in checkpoint
7. Save to output

# NEW FLOW (SAME LOGIC)
1. Load sample text (from Excel instead of Sheets)
2. Build prompt with template.format(text=text)  # SAME
3. Call Gemini API with gemma-3-27b-it  # SAME
4. Parse response for << >> tags  # SAME
5. Validate label against domain rules  # SAME
6. Mark as completed in checkpoint (Redis instead of JSON)
7. Save to output (Excel instead of Sheets)
```

---

## 🚀 Migration Guide

To migrate your existing Google Sheets dataset:

### Step 1: Export to Excel
```python
# In Google Colab
import gspread
import pandas as pd

gc = gspread.authorize(creds)
ss = gc.open("M-Help Dataset")

with pd.ExcelWriter('mhelp_dataset.xlsx') as writer:
    for sheet_name in ['Train', 'Validation', 'Test']:
        sheet = ss.worksheet(sheet_name)
        df = pd.DataFrame(sheet.get_all_values())
        df.to_excel(writer, sheet_name=sheet_name, index=False)
```

### Step 2: Place in data directory
```bash
mkdir -p M-Heath-Annotator/data
mv mhelp_dataset.xlsx M-Heath-Annotator/data/
```

### Step 3: Verify structure
Excel file should have 3 sheets with columns:
- `ID` - Sample identifier
- `Text` - Mental health text to annotate
- (Other columns optional)

---

## ✅ Verification Checklist

- [x] All original prompts preserved exactly
- [x] Same AI model (gemma-3-27b-it)
- [x] Same response parsing logic
- [x] Same validation rules
- [x] Same checkpoint concept
- [x] Improved: Local Excel vs Google Sheets
- [x] Improved: Distributed vs Sequential
- [x] Improved: Redis vs JSON checkpoints
- [x] Improved: YAML config vs Hardcoded

---

## 📝 Summary

The new system **preserves 100% of the core annotation logic** while improving:
- **Infrastructure** (distributed vs sequential)
- **Data management** (local Excel vs Google Sheets)
- **Reliability** (Redis checkpointing, automatic retry)
- **Monitoring** (Flower UI vs print statements)
- **Scalability** (30 parallel workers vs 1 sequential)

**No changes to:**
- Domain prompts (exact copies)
- AI model (same Gemma model)
- Validation logic (same rules)
- Output format (same labels)
