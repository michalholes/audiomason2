# 📦 AudioMason v2 - Installation Guide for Raspberry Pi

## 🎯 What You Have

You have the **CORE** of AudioMason v2:
- ✅ Ultra-minimal core (~800 lines)
- ✅ Plugin system (loader, events, pipeline)
- ✅ Config resolver (4-level priority)
- ✅ Detection utilities
- ✅ Example plugin
- ✅ Integration tests

**Status:** Core is complete and tested ✅

**Missing:** Actual functional plugins (audio processing, CLI, etc.)

---

## 🚀 Installation Steps

### 1. Transfer Project to Raspberry Pi

```bash
# On your Mac, transfer the entire directory:
scp -r audiomason-v2-implementation pi@raspberrypi.local:~/

# Or if you have the directory on a USB stick:
# Just copy it to your home directory
```

### 2. Install System Dependencies

```bash
ssh pi@raspberrypi.local

# Update system
sudo apt-get update

# Install Python 3.11+ (if not already installed)
sudo apt-get install -y python3 python3-pip python3-venv

# Install FFmpeg (will be needed for audio processing)
sudo apt-get install -y ffmpeg

# Install YAML library
sudo apt-get install -y python3-yaml
```

### 3. Install AudioMason

```bash
cd ~/audiomason-v2-implementation

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Or install globally:
pip3 install -e .
```

---

## 🧪 Verify Installation

### Test 1: Config System

```bash
cd ~/audiomason-v2-implementation
python3 tests/simple_test_config.py
```

**Expected output:**
```
✓ CLI has highest priority
✓ User config overrides system config
✓ Defaults work when nothing else provides value
✓ Nested keys with dot notation work
✅ All tests passed!
```

### Test 2: Integration (Core + Plugin + Pipeline)

```bash
python3 tests/test_integration.py
```

**Expected output:**
```
🧪 Integration Test: Core + Plugin + Pipeline

📁 Created test file: /tmp/.../test_book.m4a
🔌 Loading plugin from: .../example_plugin
✅ Plugin loaded: ['example_plugin']
📦 Created context:
   ID: ...
   Source: test_book.m4a
   Author: Test Author
   Title: Test Book
🔄 Created pipeline:
   Name: test_pipeline
   Steps: 1
   Step 1: example_step (plugin: example_plugin)
⚡ Executing pipeline...
✅ Pipeline completed!
📊 Results:
   State: processing
   Completed steps: ['example_step']
   Warnings: ['ExamplePlugin: Hello from plugin!']
   Timings: {'example_plugin': 0.1}
🎉 All assertions passed!

==================================================
✅ INTEGRATION TEST PASSED
==================================================
```

---

## 📁 What's in the Project

```
audiomason-v2-implementation/
│
├── src/audiomason/core/          # Core system (COMPLETE ✅)
│   ├── __init__.py               # Exports
│   ├── context.py                # ProcessingContext
│   ├── interfaces.py             # 5 Protocols
│   ├── config.py                 # ConfigResolver
│   ├── errors.py                 # Error classes
│   ├── loader.py                 # PluginLoader
│   ├── events.py                 # EventBus
│   ├── pipeline.py               # PipelineExecutor
│   └── detection.py              # Preflight utilities
│
├── plugins/                       # Plugins
│   └── example_plugin/           # Example (WORKING ✅)
│       ├── plugin.yaml
│       └── plugin.py
│
├── tests/                         # Tests (PASSING ✅)
│   ├── simple_test_config.py
│   └── test_integration.py
│
├── docs/                          # Documentation
├── pipelines/                     # Pipeline YAMLs (empty)
│
├── pyproject.toml                 # Project config
├── README.md                      # Main README
└── INSTALL_GUIDE.md              # This file
```

---

## ⚙️ Configuration

### Create User Config

```bash
mkdir -p ~/.config/audiomason
nano ~/.config/audiomason/config.yaml
```

**Example config:**
```yaml
# Paths
ffmpeg_path: /usr/bin/ffmpeg
output_dir: ~/Audiobooks/output
plugins_dir: ~/.audiomason/plugins

# Audio
bitrate: 128k
loudnorm: true

# Logging
logging:
  level: normal  # quiet | normal | verbose | debug
  color: true
```

---

## 🔧 Troubleshooting

### Problem: "No module named 'yaml'"

```bash
# Install PyYAML
pip3 install pyyaml
# Or system-wide:
sudo apt-get install python3-yaml
```

### Problem: "No module named 'audiomason'"

```bash
# Make sure you installed the package:
cd ~/audiomason-v2-implementation
pip3 install -e .

# Or add to PYTHONPATH:
export PYTHONPATH=~/audiomason-v2-implementation/src:$PYTHONPATH
```

### Problem: Tests fail

```bash
# Check Python version (need 3.11+)
python3 --version

# Check if all files are present
ls -la ~/audiomason-v2-implementation/src/audiomason/core/
```

---

## 📋 What's Next?

The core is complete, but to actually process audiobooks, we need to implement:

### Critical Plugins (Must Have)

1. **Audio Processing Plugin**
   - Convert M4A → MP3
   - Convert Opus → MP3
   - Split by chapters
   - Normalize volume

2. **CLI UI Plugin**
   - Command-line interface (Typer)
   - Preflight detection
   - Smart question grouping
   - Progress display

3. **Metadata Plugins**
   - Google Books API
   - OpenLibrary API
   - ID3 tag writer

4. **Cover Plugins**
   - Extract from audio
   - Download from URL
   - Embed in audio
   - Format conversion

5. **I/O Plugins**
   - File importer (copy to stage)
   - File exporter (move to output)

### Pipeline Definitions

Create YAML pipelines in `pipelines/`:
- `minimal.yaml` - Just conversion
- `standard.yaml` - Conversion + metadata + covers
- `full.yaml` - Everything enabled

---

## 🚀 Quick Start (Once Plugins Are Ready)

```bash
# Process single book
audiomason process book.m4a

# Batch process entire folder
audiomason process /inbox/*.m4a

# With custom options
audiomason process book.m4a --bitrate 320k --loudnorm --verbose
```

---

## 🐛 Known Limitations

1. **No CLI yet** - Can't run `audiomason` command
2. **No audio processing** - Can't actually convert files
3. **No metadata fetching** - Can't get book info from APIs
4. **No cover handling** - Can't extract/download covers
5. **Detection utilities are placeholders** - Don't actually detect anything

**But:** The infrastructure is solid and ready for plugins! 🎉

---

## 📞 Support

If tests pass, the core is working correctly!

If you encounter issues:
1. Check Python version (3.11+)
2. Check all dependencies installed
3. Verify file structure is intact
4. Run tests to isolate problem

---

## 📄 Files to Read

1. `README.md` - Project overview
2. `AUDIOMASON_V2_FINAL_REQUIREMENTS.md` - Complete specification
3. `porovnanie_am1_am2.md` - What changed from v1

---

**Status:** Core Ready ✅ | Plugins In Progress 🚧 | CLI Coming Soon 🔜
