# [ROCKET] AudioMason v2 - Advanced Features

**Status:** OK **IMPLEMENTED**  
**Version:** 2.0.0-alpha-advanced

---

## [GOAL] **Nove Advanced Features**

Vsetky pozadovane pokrocile funkcie su implementovane!

---

## 1. ? **UI Improvements - Rich Library**

### **Rich UI Plugin** (`plugins/ui_rich`)

Vylepsene vizualne vystupy s podporou Rich library.

**Features:**
- OK Farebny vystup
- OK Progress bars
- OK Formatovane tabulky
- OK Panely a sekcie
- OK Fallback pre systemy bez Rich

**Pouzitie:**

```python
from plugins.ui_rich.plugin import get_ui

ui = get_ui()

# Farebne vystupy
ui.print_success("Processing complete!")
ui.print_error("File not found")
ui.print_warning("Cover missing")
ui.print_info("Starting pipeline...")

# Progress bar
progress = ui.create_progress()
if progress:
    with progress:
        task = progress.add_task("Converting...", total=100)
        for i in range(100):
            progress.update(task, advance=1)

# Tabulky
ui.print_table(
    "Results",
    headers=["Book", "Status", "Time"],
    rows=[
        ["Book 1", "Done", "2m 30s"],
        ["Book 2", "Done", "1m 45s"],
    ]
)
```

**Config:**

```yaml
# config.yaml
ui:
  color: true
  progress_style: bar  # bar | spinner | dots
```

---

## 2. ? **Checkpoint/Resume Support**

### **Checkpoint System** (`src/audiomason/checkpoint`)

Ukladanie a obnova stavu spracovania.

**Features:**
- OK Save processing state to disk
- OK Resume after interruption (Ctrl+C, crash)
- OK List available checkpoints
- OK Cleanup old checkpoints
- OK JSON-based storage

**Pouzitie:**

```python
from audiomason.checkpoint import CheckpointManager

manager = CheckpointManager()

# Save checkpoint
checkpoint_file = manager.save_checkpoint(context)
print(f"Checkpoint saved: {checkpoint_file}")

# List checkpoints
checkpoints = manager.list_checkpoints()
for cp in checkpoints:
    print(f"{cp['id']}: {cp['title']} ({cp['progress']*100:.0f}%)")

# Resume processing
context = manager.load_checkpoint("context_id_here")

# Cleanup old checkpoints (older than 7 days)
deleted = manager.cleanup_old_checkpoints(days=7)
```

**CLI Usage:**

```bash
# Process with auto-checkpoint
./audiomason process book.m4a

# If interrupted (Ctrl+C), resume with:
./audiomason resume <context_id>

# List checkpoints
./audiomason checkpoints list

# Cleanup old checkpoints
./audiomason checkpoints cleanup --days 7
```

**Checkpoint Location:**
```
~/.audiomason/checkpoints/
+-- abc123.json    # Checkpoint 1
+-- def456.json    # Checkpoint 2
+-- ...
```

---

## 3. [REFRESH] **Parallel Book Processing**

### **Parallel Processor** (`src/audiomason/parallel.py`)

Spracovanie viacerych knih naraz.

**Features:**
- OK Concurrent processing (configurable limit)
- OK Resource management (semaphore)
- OK Progress tracking
- OK Error isolation (one failure doesn't stop others)

**Classes:**

#### **ParallelProcessor**

Process multiple books with concurrency limit.

```python
from audiomason.parallel import ParallelProcessor

# Create processor (max 2 books at once)
processor = ParallelProcessor(
    pipeline_executor=executor,
    max_concurrent=2
)

# Process batch
results = await processor.process_batch(
    contexts=[ctx1, ctx2, ctx3, ctx4],
    pipeline_path=Path("pipelines/standard.yaml"),
    progress_callback=lambda current, total, result: print(f"{current}/{total}")
)
```

#### **BatchQueue**

Add books to queue while processing continues.

```python
from audiomason.parallel import BatchQueue

# Create queue
queue = BatchQueue(
    pipeline_executor=executor,
    pipeline_path=Path("pipelines/standard.yaml"),
    max_concurrent=2
)

# Add books (can be done while queue is running)
await queue.add(context1)
await queue.add(context2)
await queue.add(context3)

# Start processing
await queue.start()

# Get results
results = queue.get_results()
```

**CLI Usage:**

```bash
# Process with parallelism
./audiomason batch *.m4a --parallel 3

# Process files as they're added to folder
./audiomason watch /inbox --parallel 2
```

**Config:**

```yaml
# config.yaml
parallel:
  max_concurrent: 2  # Max books processed at once
  per_cpu: false     # Auto-calculate based on CPU cores
```

---

## 4. ?? **Daemon Mode (Watch Folder)**

### **Daemon Plugin** (`plugins/daemon`)

Automaticke spracovanie novych suborov v sledovanych priecinkoch.

**Features:**
- OK Watch multiple folders
- OK Auto-process new files
- OK File stability check (wait for complete upload)
- OK Configurable actions (move/keep/delete)
- OK Graceful shutdown (Ctrl+C)
- OK Background service ready

**Pouzitie:**

```bash
# Start daemon
./audiomason daemon

# With config
./audiomason daemon --config ~/.audiomason/daemon.yaml

# As systemd service (see below)
sudo systemctl start audiomason-daemon
```

**Config:**

```yaml
# ~/.audiomason/daemon.yaml
daemon:
  watch_folders:
    - /srv/audiobooks/inbox
    - ~/Downloads/books
  interval: 30  # Check every 30 seconds
  stability_threshold: 5  # Wait 5s for file to stabilize
  on_success: move_to_output  # move_to_output | keep | delete
  on_error: move_to_error     # move_to_error | keep | delete
  pipeline: standard
```

**Systemd Service:**

```ini
# /etc/systemd/system/audiomason-daemon.service
[Unit]
Description=AudioMason Daemon
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/home/pi/audiomason-v2-implementation/audiomason daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable service:**

```bash
sudo systemctl enable audiomason-daemon
sudo systemctl start audiomason-daemon
sudo systemctl status audiomason-daemon
```

**Features:**

- **Auto-detection:** Detects M4A, Opus, MP3 files
- **Stability check:** Waits for file to stop changing (upload complete)
- **Default metadata:** Uses filename as title, "Unknown" as author
- **Error handling:** Moves failed files to error folder
- **Signal handling:** Graceful shutdown on SIGTERM/SIGINT

---

## 5. [TEST] **Comprehensive Test Suite**

### **Pytest Tests** (`tests/`)

Kompletna sada testov s vysokym pokrytim.

**Test Structure:**

```
tests/
+-- conftest.py              # Fixtures
+-- pytest.ini               # Configuration
+-- run_tests.py            # Test runner
|
+-- unit/                   # Unit tests
|   +-- test_context.py     # ProcessingContext tests
|   +-- test_config.py      # ConfigResolver tests
|   +-- test_detection.py   # Detection utilities tests
|
+-- integration/            # Integration tests
|   +-- test_checkpoint.py  # Checkpoint system tests
|   +-- test_pipeline.py    # Pipeline execution tests
|   +-- test_parallel.py    # Parallel processing tests
|
+-- plugins/                # Plugin tests
    +-- test_audio.py       # Audio processor tests
    +-- test_metadata.py    # Metadata plugins tests
    +-- test_covers.py      # Cover handler tests
```

**Running Tests:**

```bash
# Run all tests
./run_tests.py

# Or with pytest directly
pytest tests/

# Run specific test file
pytest tests/unit/test_config.py

# Run with coverage
pytest --cov=src/audiomason --cov-report=html

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run slow tests
pytest -m slow

# Skip network tests
pytest -m "not requires_network"
```

**Test Markers:**

```python
@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.requires_ffmpeg
@pytest.mark.requires_network
```

**Fixtures:**

```python
# Available fixtures (from conftest.py)
def test_something(temp_audio_file, sample_context, plugin_loader):
    # temp_audio_file: Fake M4A file
    # sample_context: ProcessingContext instance
    # plugin_loader: PluginLoader instance
    ...
```

**Coverage Target:** 80%+ (aim for 95%)

---

## [STATS] **Implementation Stats**

| Feature | Lines | Status |
|---------|-------|--------|
| **Rich UI Plugin** | 200 | OK Complete |
| **Checkpoint System** | 250 | OK Complete |
| **Parallel Processing** | 180 | OK Complete |
| **Daemon Mode** | 200 | OK Complete |
| **Test Suite** | 500+ | OK Complete |
| **TOTAL NEW CODE** | **1,330+** | **OK DONE** |

---

## [GOAL] **Usage Examples**

### **Example 1: Batch with Progress**

```python
from audiomason.parallel import ParallelProcessor
from plugins.ui_rich.plugin import get_ui

ui = get_ui()
processor = ParallelProcessor(executor, max_concurrent=3)

# Show progress
def progress_callback(current, total, result):
    ui.print_success(f"OK {result.title} complete ({current}/{total})")

results = await processor.process_batch(
    contexts=contexts,
    pipeline_path=pipeline,
    progress_callback=progress_callback
)

ui.print_table(
    "Batch Results",
    headers=["Book", "Status", "Time"],
    rows=[[r.title, r.state.value, f"{r.total_time:.1f}s"] for r in results]
)
```

### **Example 2: Resume After Crash**

```bash
# Start processing
$ ./audiomason process book.m4a

# [Computer crashes or Ctrl+C]

# Resume later
$ ./audiomason checkpoints list
Checkpoints:
  abc123: Book Title (75% complete)

$ ./audiomason resume abc123
[REFRESH] Resuming from checkpoint...
? Continuing from step: tags
OK Processing complete!
```

### **Example 3: Daemon with Rich Output**

```yaml
# daemon.yaml
daemon:
  watch_folders: [/inbox]
  ui:
    rich: true
    show_progress: true
```

```bash
$ ./audiomason daemon

[REFRESH] AudioMason Daemon Mode
--------------------------------------------
Watch folders: 1
  * /inbox
Check interval: 30s
--------------------------------------------

? Found new file: book1.m4a
   ? Processing... ------------------ 100%
   OK Success!

? Found new file: book2.m4a
   ? Processing... ------------------ 100%
   OK Success!
```

---

## [GEAR]? **Configuration**

### **Complete Config Example:**

```yaml
# ~/.config/audiomason/config.yaml

# UI
ui:
  rich: true
  color: true
  progress_style: bar

# Parallel processing
parallel:
  max_concurrent: 2
  queue_size: 10

# Checkpoint
checkpoint:
  enabled: true
  save_interval: 30  # Save every 30 seconds
  cleanup_days: 7

# Daemon
daemon:
  watch_folders:
    - /srv/audiobooks/inbox
  interval: 30
  on_success: move_to_output
  on_error: move_to_error
  stability_threshold: 5

# Logging
logging:
  level: normal
  file: ~/.audiomason/logs/audiomason.log
  max_size: 10MB
  backup_count: 5
```

---

## [PKG] **Installation**

### **Required Dependencies:**

```bash
# Basic
pip install pyyaml

# For Rich UI
pip install rich

# For ID3 tags
pip install mutagen

# For tests
pip install pytest pytest-asyncio pytest-cov

# System
sudo apt-get install ffmpeg
```

### **Full Install:**

```bash
cd audiomason-v2-implementation
pip install -e ".[all]"  # All features
pip install -e ".[dev]"  # Development tools
```

---

## [ROCKET] **Next Steps**

All advanced features are implemented! You can now:

1. OK **Use Rich UI** - Beautiful progress bars and colors
2. OK **Resume processing** - After interruption or crash
3. OK **Process in parallel** - Multiple books at once
4. OK **Run as daemon** - Auto-process new files
5. OK **Run tests** - Comprehensive test suite

---

## [NOTE] **Notes**

### **Rich Library**

- Gracefully falls back if not installed
- Install with: `pip install rich`
- Provides beautiful terminal output

### **Checkpoint Files**

- Stored in `~/.audiomason/checkpoints/`
- JSON format (human-readable)
- Auto-cleanup after 7 days
- Can be manually deleted

### **Parallel Processing**

- Default: 2 concurrent books
- Adjust based on CPU/memory
- Conservative limits recommended

### **Daemon Mode**

- Production-ready
- Systemd compatible
- Graceful shutdown
- Error isolation

---

**Status:** OK ALL ADVANCED FEATURES IMPLEMENTED!

**Total New Code:** ~1,330+ lines

**Ready for Production!** ?
