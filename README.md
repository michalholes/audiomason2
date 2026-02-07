# [AUDIO] AudioMason v2

**Ultra-Modular Audiobook Processing Framework**

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-90%25%20complete-yellow.svg)]()

---

## [ROCKET] Quick Start

```bash
# Install dependencies
pip install -e ".[all]"

# Process audiobook
./audiomason process book.m4a

# Start web server
./audiomason web

# Start daemon mode
./audiomason daemon
```

---

## ? Features

- OK **Audio Conversion** - M4A/Opus -> MP3
- OK **Chapter Detection** - Automatic splitting
- OK **Metadata Fetching** - Google Books, OpenLibrary
- OK **Cover Handling** - Extract/download/embed
- OK **ID3 Tagging** - Uniform tags
- OK **CLI Interface** - Interactive wizard
- OK **Web UI** - REST API + management interface
- OK **Daemon Mode** - Watch folders, auto-process
- OK **Checkpoint/Resume** - Resume after interruption
- OK **Parallel Processing** - Multiple books at once

---

## [PKG] Installation

### Prerequisites

```bash
# System dependencies
sudo apt-get install ffmpeg python3 python3-pip

# Python dependencies
pip install pyyaml mutagen
```

### From Source

```bash
git clone https://github.com/michalholes/audiomason2.git
cd audiomason2
pip install -e ".[all]"
```

---

## [DOC] Documentation

- **[QUICKSTART.md](docs/QUICKSTART.md)** - Quick start guide
- **[COMPLETE.md](docs/COMPLETE.md)** - Complete feature list
- **[ADVANCED_FEATURES.md](docs/ADVANCED_FEATURES.md)** - Advanced features
- **[WEB_SERVER.md](docs/WEB_SERVER.md)** - Web UI documentation
- **[MASTER_SUMMARY.md](docs/MASTER_SUMMARY.md)** - Complete project summary

---

## [GOAL] Usage Examples

### Basic Processing

```bash
./audiomason process book.m4a
```

### With Options

```bash
./audiomason process book.m4a \
  --author "George Orwell" \
  --title "1984" \
  --year 1949 \
  --bitrate 320k \
  --loudnorm \
  --split-chapters
```

### Web Server

```bash
./audiomason web --port 8080
# Open http://localhost:8080
```

### Daemon Mode

```bash
./audiomason daemon
# Watches folders and auto-processes new files
```

---

## [BUILD]? Architecture

```
audiomason2/
+-- src/audiomason/       # Core system
|   +-- core/            # Core modules
|   +-- api/             # REST API
|   +-- checkpoint/      # Resume support
+-- plugins/             # Plugin system
|   +-- audio_processor/
|   +-- cli/
|   +-- web_server/
|   +-- ...
+-- pipelines/           # Processing pipelines
+-- tests/              # Test suite
+-- docs/               # Documentation
```

---

## [PLUG] Plugin System

AudioMason v2 is **ultra-modular**. Everything is a plugin:

```yaml
# plugins/my_plugin/plugin.yaml
name: my_plugin
version: 1.0.0
entrypoint: plugin:MyPlugin
interfaces:
  - IProcessor
```

---

## [WEB] Web Interface

Start web server:

```bash
./audiomason web
```

Features:
- [STATS] Dashboard
- [MUSIC] Process books (upload + configure)
- [LIST] Job queue
- [GEAR]? Configuration
- [PLUG] Plugin management
- [NOTE] Wizard builder

---

## [TEST] Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/audiomason
```

---

## [STATS] Status

| Component | Status |
|-----------|--------|
| Core System | OK Complete |
| Essential Plugins | OK Complete |
| CLI Interface | OK Complete |
| Web API | OK Complete |
| Web UI (basic) | OK Complete |
| Web UI (advanced) | [REFRESH] 90% |
| Ncurses TUI | [REFRESH] Planned |
| Wizard System | [REFRESH] 90% |

**Overall: 90% Complete**

---

## [SHAKE] Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

---

## [NOTE] License

MIT License - see [LICENSE](LICENSE) file.

---

## ? Author

**Michal Holes**
- Email: michal@holes.sk
- GitHub: [@michalholes](https://github.com/michalholes)

---

## [THANKS] Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/)
- [FFmpeg](https://ffmpeg.org/)
- [Mutagen](https://mutagen.readthedocs.io/)
- [Rich](https://rich.readthedocs.io/)

---

**AudioMason v2 - Transform your audiobook chaos into organized bliss!** [AUDIO]?
