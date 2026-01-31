# 🎧 AudioMason v2

**Ultra-Modular Audiobook Processing Framework**

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-90%25%20complete-yellow.svg)]()

---

## 🚀 Quick Start

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

## ✨ Features

- ✅ **Audio Conversion** - M4A/Opus → MP3
- ✅ **Chapter Detection** - Automatic splitting
- ✅ **Metadata Fetching** - Google Books, OpenLibrary
- ✅ **Cover Handling** - Extract/download/embed
- ✅ **ID3 Tagging** - Uniform tags
- ✅ **CLI Interface** - Interactive wizard
- ✅ **Web UI** - REST API + management interface
- ✅ **Daemon Mode** - Watch folders, auto-process
- ✅ **Checkpoint/Resume** - Resume after interruption
- ✅ **Parallel Processing** - Multiple books at once

---

## 📦 Installation

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

## 📖 Documentation

- **[QUICKSTART.md](docs/QUICKSTART.md)** - Quick start guide
- **[COMPLETE.md](docs/COMPLETE.md)** - Complete feature list
- **[ADVANCED_FEATURES.md](docs/ADVANCED_FEATURES.md)** - Advanced features
- **[WEB_SERVER.md](docs/WEB_SERVER.md)** - Web UI documentation
- **[MASTER_SUMMARY.md](docs/MASTER_SUMMARY.md)** - Complete project summary

---

## 🎯 Usage Examples

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

## 🏗️ Architecture

```
audiomason2/
├── src/audiomason/       # Core system
│   ├── core/            # Core modules
│   ├── api/             # REST API
│   └── checkpoint/      # Resume support
├── plugins/             # Plugin system
│   ├── audio_processor/
│   ├── cli/
│   ├── web_server/
│   └── ...
├── pipelines/           # Processing pipelines
├── tests/              # Test suite
└── docs/               # Documentation
```

---

## 🔌 Plugin System

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

## 🌐 Web Interface

Start web server:

```bash
./audiomason web
```

Features:
- 📊 Dashboard
- 🎵 Process books (upload + configure)
- 📋 Job queue
- ⚙️ Configuration
- 🔌 Plugin management
- 📝 Wizard builder

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/audiomason
```

---

## 📊 Status

| Component | Status |
|-----------|--------|
| Core System | ✅ Complete |
| Essential Plugins | ✅ Complete |
| CLI Interface | ✅ Complete |
| Web API | ✅ Complete |
| Web UI (basic) | ✅ Complete |
| Web UI (advanced) | 🔄 90% |
| Ncurses TUI | 🔄 Planned |
| Wizard System | 🔄 90% |

**Overall: 90% Complete**

---

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file.

---

## 👤 Author

**Michal Holeš**
- Email: michal@holes.sk
- GitHub: [@michalholes](https://github.com/michalholes)

---

## 🙏 Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/)
- [FFmpeg](https://ffmpeg.org/)
- [Mutagen](https://mutagen.readthedocs.io/)
- [Rich](https://rich.readthedocs.io/)

---

**AudioMason v2 - Transform your audiobook chaos into organized bliss!** 🎧✨
