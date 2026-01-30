# 🎧 AudioMason v2

**Ultra-modular audiobook processing framework**

## 🎯 Status: Alpha Development

This is AudioMason v2 - a complete rewrite with plugin-first architecture.

### ✅ Implemented (Core)

- **Context System** - ProcessingContext with all data flow
- **5 Generic Interfaces** - IProcessor, IProvider, IUI, IStorage, IEnricher
- **Config Resolver** - 4-level priority (CLI > ENV > CONFIG > DEFAULT)
- **Plugin Loader** - Discovery and loading from multiple sources
- **Event Bus** - Pub/sub for plugin communication
- **Pipeline Executor** - YAML → DAG → async execution
- **Detection Utilities** - Preflight helpers (guess author, title, etc.)
- **Error Handling** - Friendly error messages

### 🔄 In Progress

- Essential plugins (audio, metadata, covers, I/O)
- CLI UI plugin
- Pipeline YAML definitions
- Documentation

### ❌ Not Yet Implemented

- Full plugin validation (mypy, pytest, ruff)
- Daemon mode
- Web UI
- API server
- Checkpoint/resume system
- Full test coverage

---

## 📋 Requirements

- Python 3.11+
- FFmpeg (for audio processing)
- PyYAML
- (more dependencies will be added as plugins are implemented)

---

## 🚀 Installation (Raspberry Pi)

### 1. Clone/Transfer Project

```bash
# If using git:
git clone <repo> audiomason-v2
cd audiomason-v2

# Or transfer the entire directory to your Raspberry Pi
```

### 2. Install Dependencies

```bash
# Install system packages
sudo apt-get update
sudo apt-get install -y python3 python3-pip ffmpeg

# Install Python packages
pip3 install pyyaml
```

### 3. Install AudioMason

```bash
# Install in editable mode
pip3 install -e .
```

---

## 📁 Project Structure

```
audiomason-v2-implementation/
├── src/audiomason/
│   └── core/               # Ultra-minimal core (~800 lines)
│       ├── __init__.py
│       ├── context.py      # ProcessingContext
│       ├── interfaces.py   # 5 Protocol definitions
│       ├── config.py       # ConfigResolver
│       ├── errors.py       # Error classes
│       ├── loader.py       # PluginLoader
│       ├── events.py       # EventBus
│       ├── pipeline.py     # PipelineExecutor
│       └── detection.py    # Preflight utilities
│
├── tests/                  # Tests
├── pipelines/              # Pipeline YAML definitions
├── docs/                   # Documentation
└── pyproject.toml          # Project config
```

---

## 🧪 Testing Core

```bash
# Simple config test
python3 tests/simple_test_config.py

# Should output:
# ✓ CLI has highest priority
# ✓ User config overrides system config
# ✓ Defaults work when nothing else provides value
# ✓ Nested keys with dot notation work
# ✅ All tests passed!
```

---

## 📖 Architecture

### Core Principles

1. **Ultra-minimal core** (~800 lines) - just infrastructure
2. **Everything else is a plugin** - even CLI, audio processing
3. **Generic interfaces** - maximum flexibility
4. **Declarative pipelines** - YAML → DAG → execution
5. **4-level config** - CLI > ENV > CONFIG > DEFAULT
6. **3-phase execution** - Preflight → Input → Processing

### Interfaces

```python
class IProcessor(Protocol):
    """Process media. Must be non-interactive."""
    async def process(self, context: Context) -> Context: ...

class IProvider(Protocol):
    """Provide external data (metadata, covers)."""
    async def fetch(self, query: dict) -> dict: ...

class IUI(Protocol):
    """User interface. Handles ALL interaction."""
    async def run(self) -> None: ...

class IStorage(Protocol):
    """Storage backend."""
    async def read(self, path: str) -> bytes: ...
    async def write(self, path: str, data: bytes) -> None: ...

class IEnricher(Protocol):
    """Enrich context with additional data."""
    async def enrich(self, context: Context) -> Context: ...
```

---

## 🔌 Plugin System

### Plugin Structure

```
my_plugin/
├── plugin.yaml         # Manifest
└── plugin.py           # Implementation
```

### Plugin Manifest Example

```yaml
name: my_plugin
version: 1.0.0
description: "My awesome plugin"
author: "Your Name <you@example.com>"
license: MIT

entrypoint: plugin:MyPlugin
interfaces: [IProcessor]
hooks: [post_convert]

dependencies:
  python: ">=3.11"

config_schema:
  my_option:
    type: string
    default: "value"

test_level: basic
```

### Plugin Implementation Example

```python
# plugin.py
from audiomason.core import IProcessor, ProcessingContext

class MyPlugin(IProcessor):
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        # Do something with context
        context.add_warning("Plugin executed!")
        return context
```

---

## ⚙️ Configuration

### Config Priority

```
1. CLI arguments        (--option value)
2. Environment vars     (AUDIOMASON_*)
3. User config          (~/.config/audiomason/config.yaml)
4. System config        (/etc/audiomason/config.yaml)
5. Defaults             (hardcoded)
```

### Example Config

```yaml
# ~/.config/audiomason/config.yaml

# Paths
ffmpeg_path: /usr/bin/ffmpeg
output_dir: ~/Audiobooks/output
plugins_dir: ~/.audiomason/plugins

# Audio
bitrate: 128k
loudnorm: true
split_chapters: false

# Metadata
metadata_providers:
  - googlebooks
  - openlibrary

# Logging
logging:
  level: normal  # quiet | normal | verbose | debug
  file: ~/.audiomason/logs/audiomason.log
  color: true
```

---

## 🎬 Usage (Once Implemented)

### Basic Processing

```bash
# Process single file
audiomason process book.m4a

# Batch processing
audiomason process /inbox/*.m4a

# With options
audiomason process book.m4a --bitrate 320k --loudnorm
```

### Verbosity Modes

```bash
# Quiet (errors only)
audiomason process book.m4a --quiet

# Normal (default)
audiomason process book.m4a

# Verbose (detailed)
audiomason process book.m4a --verbose

# Debug (full trace)
audiomason process book.m4a --debug
```

---

## 📚 Documentation

- [Requirements Document](AUDIOMASON_V2_FINAL_REQUIREMENTS.md) - Complete specification
- [AM1 vs AM2 Comparison](porovnanie_am1_am2.md) - What changed

---

## 🐛 Known Issues

1. Plugin validation not implemented (mypy/pytest/ruff checks)
2. No plugins implemented yet
3. No CLI implemented yet
4. Detection utilities don't actually detect (placeholders)
5. Pipeline executor doesn't handle IProvider correctly
6. No checkpointing/resume support
7. No tests for most modules

---

## 🚧 Next Steps

### Immediate (Critical)

1. ✅ Core infrastructure (DONE)
2. 🔄 Audio processing plugin
3. 🔄 CLI UI plugin
4. 🔄 Pipeline YAML definitions

### Short-term

5. Metadata plugins (Google Books, OpenLibrary)
6. Cover plugins (extractor, downloader, embedder)
7. I/O plugins (importer, exporter)
8. Test coverage
9. Documentation

### Long-term

10. Daemon mode
11. Web UI
12. API server
13. Plugin marketplace
14. CI/CD pipeline

---

## 🤝 Contributing

This is alpha software. Everything is subject to change.

---

## 📄 License

MIT

---

## 👤 Author

Michal Holeš <michal@holes.sk>

---

**Status:** Core complete, plugins in progress 🚀
