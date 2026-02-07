# [WIZARD] AudioMason v2 - Wizard Engine Documentation

**Date:** 2026-01-30  
**Status:** OK COMPLETE  
**Version:** 2.0.0

---

## [LIST] Overview

The Wizard Engine is a flexible, YAML-based workflow system that guides users through audiobook processing with step-by-step interactive prompts.

---

## ? Features

- **YAML-based workflows** - Easy to create and modify
- **Interactive prompts** - User-friendly CLI interface
- **Step types** - input, choice, plugin_call, condition, set_value
- **Error handling** - Graceful failure recovery
- **Progress tracking** - Visual feedback
- **Conditional logic** - if/else branching
- **Plugin integration** - Call any plugin method

---

## [ROCKET] Quick Start

### List Available Wizards
```bash
audiomason wizard
```

### Run a Wizard
```bash
audiomason wizard quick_import
```

---

## [PKG] Included Wizards

### 1. **quick_import.yaml** ?
**Description:** Fast single audiobook import with minimal questions

**Steps:**
1. Enter author name
2. Enter book title
3. Enter year (optional)
4. Choose bitrate
5. Convert audio
6. Apply ID3 tags
7. Organize files

**Use when:** You want quick processing without extra options

---

### 2. **batch_import.yaml** ?
**Description:** Process multiple audiobooks at once from a folder

**Steps:**
1. Select source folder
2. Enable parallel processing (yes/no)
3. Choose number of parallel jobs
4. Set default bitrate
5. Enable loudness normalization
6. Batch process all books

**Use when:** You have multiple audiobooks in one folder

---

### 3. **complete_import.yaml** [GOAL]
**Description:** Full audiobook import with metadata fetching and cover download

**Steps:**
1. Enter author and title
2. Fetch metadata (Google Books, OpenLibrary, Both)
3. Download cover image
4. Configure audio processing
5. Convert and normalize
6. Apply ID3 tags
7. Embed cover
8. Organize output

**Use when:** You want maximum metadata quality

---

### 4. **merge_multipart.yaml** ?
**Description:** Merge multiple parts of a single audiobook

**Steps:**
1. Enter author and title
2. Select parts (manual, auto-detect, by date)
3. Choose numbering format
4. Set bitrate and normalization
5. Merge all parts
6. Apply unified ID3 tags
7. Handle cover image
8. Organize output

**Use when:** Your audiobook is split into multiple parts

---

### 5. **advanced.yaml** ?
**Description:** Full-featured import with all options

**Sections:**
1. **Source** - File, folder, or archive
2. **Metadata** - Manual, preflight, online, or hybrid
3. **Cover** - Multiple handling modes
4. **Audio** - All processing options
5. **ID3 Tags** - Wipe, preserve, or merge
6. **Output** - Structure and filename format
7. **Cleanup** - Source and temp file handling

**Use when:** You need full control over every option

---

## ?? Creating Custom Wizards

### Basic Structure

```yaml
wizard:
  name: "My Custom Wizard"
  description: "What this wizard does"
  
  steps:
    - id: step1
      type: input
      prompt: "Enter value"
      required: true
    
    - id: step2
      type: choice
      prompt: "Select option"
      choices:
        - "Option 1"
        - "Option 2"
      default: "Option 1"
    
    - id: step3
      type: plugin_call
      plugin: audio_processor
      method: process
  
  cleanup:
    on_success:
      source_files: "move"
      temp_files: "delete"
```

---

## [DOC] Step Types

### 1. **input** - Text Input
```yaml
- id: author
  type: input
  prompt: "Author name"
  required: true
  default: "Unknown"
  default_from: preflight  # Get from preflight detection
  fallback: "Unknown Author"
  validate: "not_empty"
```

**Options:**
- `prompt` - Question to ask user
- `required` - Must provide value (true/false)
- `default` - Default value
- `default_from` - Get default from context field
- `fallback` - Use if required but empty
- `validate` - Validation rule

---

### 2. **choice** - Multiple Choice
```yaml
- id: bitrate
  type: choice
  prompt: "Audio bitrate"
  choices:
    - "128k"
    - "192k"
    - "256k"
  default: "128k"
```

**Options:**
- `prompt` - Question to ask user
- `choices` - List of options
- `default` - Default selection

---

### 3. **plugin_call** - Execute Plugin
```yaml
- id: convert
  type: plugin_call
  plugin: audio_processor
  method: process
  params:
    loudnorm: true
    split_chapters: false
  on_error: "continue"  # or "stop"
```

**Options:**
- `plugin` - Plugin name
- `method` - Method to call (default: "process")
- `params` - Parameters to pass
- `on_error` - Error handling ("continue" or "stop")

---

### 4. **condition** - Conditional Logic
```yaml
- id: check_year
  type: condition
  condition: "year exists"
  if_true:
    - id: use_year
      type: set_value
      field: has_year
      value: true
  if_false:
    - id: no_year
      type: set_value
      field: has_year
      value: false
```

**Condition Syntax:**
- `field == "value"` - Equality check
- `field != "value"` - Not equal
- `field exists` - Field has value

---

### 5. **set_value** - Set Context Value
```yaml
- id: set_default
  type: set_value
  field: bitrate
  value: "192k"
```

---

## ? Advanced Features

### Variable Substitution
```yaml
params:
  source: "${source_folder}"
  parallel: "${parallel}"
  loudnorm: "${loudnorm == 'yes'}"
```

### Nested Conditions
```yaml
- id: metadata_check
  type: condition
  condition: "fetch_metadata == 'yes'"
  if_true:
    - id: provider_check
      type: condition
      condition: "provider != 'OpenLibrary'"
      if_true:
        - id: fetch_google
          type: plugin_call
          plugin: metadata_googlebooks
```

### Progress Callbacks
```python
engine.set_progress_callback(lambda step, current, total: 
    print(f"[{current}/{total}] {step}...")
)
```

### Custom Input Handlers
```python
def my_handler(prompt: str, options: dict) -> str:
    # Custom input logic
    return user_value

engine.set_input_handler(my_handler)
```

---

## ? Programmatic Usage

### Python API

```python
from pathlib import Path
from audiomason.wizard_engine import WizardEngine
from audiomason.core import PluginLoader, ProcessingContext

# Create engine
loader = PluginLoader()
engine = WizardEngine(loader)

# Load wizard
wizard_file = Path("wizards/quick_import.yaml")
wizard_def = engine.load_yaml(wizard_file)

# Run wizard
context = engine.run_wizard(wizard_def)

print(f"Processed: {context.author} - {context.title}")
```

### With Custom Context

```python
# Create pre-populated context
context = ProcessingContext(
    id="my-book",
    source=Path("book.m4a"),
    author="Known Author",
    title="Known Title"
)

# Run wizard with existing context
result = engine.run_wizard(wizard_def, context)
```

---

## ? Error Handling

### Step-level Error Handling
```yaml
- id: risky_step
  type: plugin_call
  plugin: some_plugin
  on_error: "continue"  # Don't stop wizard on error
```

### Wizard-level Cleanup
```yaml
cleanup:
  on_success:
    source_files: "move"    # or "delete", "keep"
    temp_files: "delete"
  on_error:
    action: "continue"      # or "stop", "ask"
  on_duplicate:
    action: "skip"          # or "overwrite", "ask"
```

---

## [STATS] Wizard Engine Architecture

```
+-----------------------------------------+
|         WizardEngine                    |
|  +--------------------------------+    |
|  |  load_yaml()                   |    |
|  |  +- Parse YAML                 |    |
|  |  +- Validate structure         |    |
|  |  +- Return wizard_def          |    |
|  +--------------------------------+    |
|                                         |
|  +--------------------------------+    |
|  |  run_wizard()                  |    |
|  |  +- Loop through steps         |    |
|  |  +- Call execute_step()        |    |
|  |  +- Update context             |    |
|  |  +- Handle errors              |    |
|  +--------------------------------+    |
|                                         |
|  +--------------------------------+    |
|  |  execute_step()                |    |
|  |  +- input -> _execute_input     |    |
|  |  +- choice -> _execute_choice   |    |
|  |  +- plugin_call -> _execute...  |    |
|  |  +- condition -> _execute...    |    |
|  |  +- set_value -> _execute...    |    |
|  +--------------------------------+    |
+-----------------------------------------+
```

---

## [NOTE] Best Practices

### 1. **Start Simple**
- Begin with quick_import.yaml as template
- Add complexity gradually
- Test each step individually

### 2. **Use Descriptive IDs**
- `id: author` not `id: step1`
- Makes debugging easier
- Self-documenting code

### 3. **Provide Defaults**
- Always set sensible defaults
- Use `default_from: preflight` when possible
- Reduces user input required

### 4. **Handle Errors Gracefully**
- Use `on_error: continue` for non-critical steps
- Provide fallback values
- Test error scenarios

### 5. **Group Related Steps**
- Use comments to separate sections
- Logical flow: source -> metadata -> processing -> output
- Makes wizards easier to maintain

---

## ? Debugging

### Verbose Mode
```bash
audiomason wizard quick_import -v
```

### Debug Mode
```bash
audiomason wizard quick_import -d
```

### Manual Step Execution
```python
# Test single step
step = {
    'id': 'test',
    'type': 'input',
    'prompt': 'Test prompt'
}

result = engine.execute_step(step, context)
print(f"Success: {result.success}")
print(f"Value: {result.value}")
print(f"Error: {result.error}")
```

---

## ? Performance Tips

### 1. **Parallel Processing**
- Use batch_import for multiple books
- Configure max_parallel wisely
- Monitor system resources

### 2. **Preflight First**
- Always run preflight detection
- Reduces user input
- Speeds up workflow

### 3. **Cache Metadata**
- Metadata fetching is slow
- Cache results when possible
- Use hybrid mode efficiently

---

## [GOAL] Use Cases

### Personal Library Organization
```bash
audiomason wizard batch_import
# Process entire folder
# Consistent naming
# Metadata enrichment
```

### Quick Single Book
```bash
audiomason wizard quick_import
# Minimal questions
# Fast processing
# Good for known books
```

### Multi-part Series
```bash
audiomason wizard merge_multipart
# Combine all parts
# Unified metadata
# Sequential numbering
```

### Maximum Quality
```bash
audiomason wizard complete_import
# Full metadata fetch
# Cover download
# All optimizations
```

---

## ? Support

### Common Issues

**Q: Wizard not found**
```bash
# Check available wizards
audiomason wizard

# Verify file exists
ls ~/audiomason2-git/wizards/
```

**Q: Plugin not found in wizard**
```bash
# Check plugin is installed
ls ~/audiomason2-git/plugins/

# Check plugin name in YAML matches directory name
```

**Q: Step fails silently**
```bash
# Run in debug mode
audiomason wizard quick_import -d

# Check plugin method exists
```

---

## [ROCKET] Next Steps

1. **Try the included wizards**
   ```bash
   audiomason wizard
   audiomason wizard quick_import
   ```

2. **Create your own wizard**
   ```bash
   cp wizards/quick_import.yaml wizards/my_wizard.yaml
   # Edit my_wizard.yaml
   audiomason wizard my_wizard
   ```

3. **Share your wizards**
   - Package as ZIP
   - Upload to GitHub
   - Share with community

---

**Created:** 2026-01-30  
**Author:** AudioMason Team  
**Status:** Production Ready OK
