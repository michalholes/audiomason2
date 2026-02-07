# AudioMason 2 Sync - Interface Specifications

Kompletna technicka specifikacia vsetkych rozhrani a kontraktov.

---

## 1. PLUGIN INTERFACE

### 1.1 Plugin File Structure

```
plugins/<plugin_name>/
+-- plugin.yaml          # Plugin metadata
+-- plugin.py            # Plugin implementation
```

### 1.2 plugin.yaml Specification

```yaml
# REQUIRED FIELDS
name: string             # Plugin identifier (lowercase, underscores)
version: string          # Semantic version (e.g. "1.0.0")
description: string      # Human-readable description
author: string           # Author name
entrypoint: string       # Python import path (e.g. "plugin:ClassName")

# OPTIONAL FIELDS
interfaces:              # List of implemented interfaces
  - IProcessor          # Standard processing interface

config:                  # Default configuration
  key: value            # Plugin-specific config values
  nested:
    key: value

dependencies:            # Python package dependencies
  - package>=version
```

**Validation Rules:**
- `name` must match directory name
- `name` must be unique across all plugins
- `version` must follow semver (MAJOR.MINOR.PATCH)
- `entrypoint` format: `file:ClassName` (file without .py extension)

**Example:**
```yaml
name: file_io_sync
version: 1.0.0
description: Synchronous file I/O operations
author: Michal Holes
entrypoint: plugin:FileIOSync
interfaces:
  - IProcessor
config:
  inbox_dir: ~/Audiobooks/inbox
  stage_dir: /tmp/audiomason/stage
```

---

### 1.3 Plugin Class Interface

```python
class PluginName:
    """Plugin implementation."""
    
    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.
        
        Args:
            config: Plugin configuration dictionary
                   Merged from: CLI > ENV > CONFIG > plugin.yaml
        
        Required to store:
            self.config: dict
            self.verbosity: int (0-3)
        """
        pass
    
    def process(self, context: ProcessingContext) -> ProcessingContext:
        """Main processing method (IProcessor interface).
        
        Args:
            context: Current processing context
        
        Returns:
            Updated context
        
        Raises:
            AudioMasonError or subclass on failure
        """
        pass
```

**Contract:**
- Constructor MUST accept `config: dict | None`
- Constructor MUST NOT fail if config is None or empty
- Constructor MUST store `self.verbosity` from config
- `process()` method MUST return ProcessingContext
- `process()` method MUST NOT modify context in-place (return new/updated)
- All exceptions MUST inherit from `AudioMasonError`

---

### 1.4 Plugin Methods (Callable from Workflow)

Pluginy mozu mat lubovolne metody, ktore su volatelne z workflow:

```python
class MyPlugin:
    def custom_method(self, context: ProcessingContext, **kwargs) -> Any:
        """Custom method callable from workflow.
        
        Args:
            context: Always first argument
            **kwargs: Additional arguments from workflow
        
        Returns:
            Any value (usually ProcessingContext or specific data)
        """
        pass
```

**Contract:**
- First argument MUST be `context: ProcessingContext`
- Additional arguments via `**kwargs` (optional)
- Return value can be anything
- Modify context or return new context
- Raise exceptions on error

**Workflow Usage:**
```yaml
- id: custom_step
  plugin: my_plugin
  method: custom_method
  enabled: true
```

---

### 1.5 Logging Interface

```python
def _log_debug(self, msg: str) -> None:
    """Log debug message (verbosity >= 3)."""
    if self.verbosity >= 3:
        print(f"[DEBUG] [{self.__class__.__name__}] {msg}")

def _log_verbose(self, msg: str) -> None:
    """Log verbose message (verbosity >= 2)."""
    if self.verbosity >= 2:
        print(f"[VERBOSE] [{self.__class__.__name__}] {msg}")

def _log_info(self, msg: str) -> None:
    """Log info message (verbosity >= 1)."""
    if self.verbosity >= 1:
        print(f"[{self.__class__.__name__}] {msg}")

def _log_error(self, msg: str) -> None:
    """Log error message (always shown)."""
    print(f"[ERROR] [{self.__class__.__name__}] {msg}")
```

**Contract:**
- Logging MUST respect verbosity level
- Error messages MUST always be shown (verbosity ignored)
- Format: `[LEVEL] [plugin_name] message`

---

## 2. WORKFLOW YAML INTERFACE

### 2.1 Top-Level Structure

```yaml
workflow:
  name: string                    # REQUIRED: Workflow display name
  description: string             # OPTIONAL: Human-readable description
  
  preflight_steps: []             # REQUIRED: List of preflight steps
  processing_steps: []            # REQUIRED: List of processing steps

verbosity:                        # OPTIONAL: Verbosity configuration
  quiet: []                       # Level 0 message types
  normal: []                      # Level 1 message types
  verbose: []                     # Level 2 message types
  debug: []                       # Level 3 message types
```

**Validation:**
- `workflow.name` is REQUIRED
- At least one step in `preflight_steps` OR `processing_steps` REQUIRED
- `verbosity` section OPTIONAL (uses defaults if missing)

---

### 2.2 Preflight Step Specification

Preflight steps collect user input before processing.

#### 2.2.1 Type: yes_no

```yaml
- id: string                      # REQUIRED: Unique step identifier
  type: yes_no                    # REQUIRED: Step type
  enabled: boolean                # OPTIONAL: default true
  prompt: string                  # REQUIRED: Question to user
  default: "yes" | "no"           # OPTIONAL: Default answer
  skip_if_set: boolean            # OPTIONAL: Skip if in config/CLI
```

**Behavior:**
- Prompts user with (y/N) or (Y/n) based on default
- Stores boolean in `answers[id]`
- If `skip_if_set: true` and value in config -> skip prompt, use config value

**Example:**
```yaml
- id: clean_inbox
  type: yes_no
  enabled: true
  prompt: "Clean inbox after import"
  default: no
  skip_if_set: true
```

---

#### 2.2.2 Type: input

```yaml
- id: string                      # REQUIRED: Unique identifier
  type: input                     # REQUIRED: Step type
  enabled: boolean                # OPTIONAL: default true
  prompt: string                  # REQUIRED: Input prompt
  required: boolean               # OPTIONAL: Must not be empty
  default: string                 # OPTIONAL: Default value
  hint_from: "source_name"        # OPTIONAL: Extract hint from
  hint_pattern: string            # OPTIONAL: Regex pattern for extraction
```

**Behavior:**
- Prompts user for text input
- Shows default in brackets: `Prompt [default]: `
- If `required: true` and empty -> error
- If `hint_from` and `hint_pattern` -> extract hint from specified source

**Hint Extraction:**
- `hint_from: "source_name"` -> uses current source name
- `hint_pattern` -> regex with capture group (1)
- Example: `"^([^-]+)"` extracts text before first dash

**Example:**
```yaml
- id: author
  type: input
  enabled: true
  prompt: "Author name"
  required: true
  hint_from: source_name
  hint_pattern: "^([^-]+)"
```

For source `"George Orwell - 1984"` -> hint = `"George Orwell"`

---

#### 2.2.3 Type: menu

```yaml
- id: choose_source              # REQUIRED: Must be "choose_source"
  type: menu                     # REQUIRED: Step type
  enabled: boolean               # OPTIONAL: default true
  prompt: string                 # REQUIRED: Selection prompt
  default: string                # OPTIONAL: Default choice
```

**Behavior:**
- Special step for source selection
- Shows numbered list of sources from inbox
- Accepts number (1-N) or 'a' for all
- Cannot be customized beyond prompt

**Example:**
```yaml
- id: choose_source
  type: menu
  enabled: true
  prompt: "Choose source number, or 'a' for all"
  default: "1"
```

---

### 2.3 Processing Step Specification

```yaml
- id: string                      # REQUIRED: Unique identifier
  plugin: string                  # REQUIRED: Plugin name
  method: string                  # REQUIRED: Method to call
  enabled: boolean                # OPTIONAL: default true
  description: string             # OPTIONAL: Display description
  condition: string               # OPTIONAL: Execution condition
```

**Fields:**

**id** (REQUIRED)
- Unique identifier for step
- Used in logs and debugging
- Convention: lowercase with underscores

**plugin** (REQUIRED)
- Plugin name (must exist in `plugins/` directory)
- Must match plugin's `name` in plugin.yaml
- Valid values: `file_io_sync`, `audio_processor_sync`, etc.

**method** (REQUIRED)
- Method name to call on plugin
- Method must exist in plugin class
- Method signature: `def method(self, context: ProcessingContext) -> Any`

**enabled** (OPTIONAL, default: true)
- If false, step is skipped
- Useful for temporarily disabling steps

**description** (OPTIONAL)
- Human-readable description
- Displayed in verbose/debug mode
- Example: `"Import to staging area"`

**condition** (OPTIONAL)
- Conditional execution
- See section 2.4 for syntax

**Example:**
```yaml
- id: import
  plugin: file_io_sync
  method: import_to_stage
  enabled: true
  description: "Import source to staging"

- id: export
  plugin: file_io_sync
  method: export_to_output
  enabled: true
  description: "Export to output directory"
  condition: "answers.publish == true"
```

---

### 2.4 Condition Syntax

Conditions control step execution.

**Supported Operators:**
- `==` : Equals
- `!=` : Not equals

**Supported Contexts:**
- `answers.key` : Value from preflight answers
- `config.key` : Value from configuration

**Value Types:**
- `true` / `false` : Boolean literals
- `"string"` : String literals (with quotes)
- `123` : Numeric literals

**Syntax:**
```
<context>.<key> <operator> <value>
```

**Examples:**
```yaml
condition: "answers.publish == true"
condition: "answers.clean_inbox == false"
condition: "config.fetch_metadata == true"
condition: "answers.author != 'Unknown'"
```

**Evaluation:**
- If condition is missing or empty -> always execute
- If condition evaluates to false -> skip step
- If condition syntax invalid -> execute (fail-open)

**NOT Supported:**
- Complex logic: `and`, `or`, `not`
- Comparison: `>`, `<`, `>=`, `<=`
- Membership: `in`, `contains`
- Nested paths: `context.converted_files.length`

---

### 2.5 Verbosity Configuration

```yaml
verbosity:
  quiet:                          # Level 0 (--quiet)
    - errors                      # Only error messages
  
  normal:                         # Level 1 (default)
    - errors                      # Error messages
    - prompts                     # User prompts
    - progress                    # Progress updates
    - workflow_steps              # Step names
  
  verbose:                        # Level 2 (--verbose)
    - errors
    - prompts
    - progress
    - workflow_steps
    - plugin_calls                # Plugin method calls
    - file_operations             # File operations
  
  debug:                          # Level 3 (--debug)
    - errors
    - prompts
    - progress
    - workflow_steps
    - plugin_calls
    - file_operations
    - config_values               # Config resolution
    - ffmpeg_output               # FFmpeg command output
    - api_responses               # API responses
```

**Supported Message Types:**
- `errors` : Error messages (ALWAYS shown if verbosity allows)
- `prompts` : User input prompts
- `progress` : Progress messages
- `workflow_steps` : Workflow step descriptions
- `plugin_calls` : Plugin method invocations
- `file_operations` : File copy/move/delete operations
- `config_values` : Configuration value resolution
- `ffmpeg_output` : FFmpeg command output
- `api_responses` : HTTP API responses

**Behavior:**
- Message shown IF message type is in current verbosity level list
- Higher levels inherit from lower levels (automatic)
- Unknown message types are ignored

---

## 3. CONFIGURATION INTERFACE

### 3.1 Configuration Priority

```
CLI Arguments > Environment Variables > Config File > Plugin Defaults
```

**Resolution Order:**
1. Check CLI arguments
2. Check environment variables (`AUDIOMASON_*`)
3. Check config file (`~/.config/audiomason/config.yaml`)
4. Check plugin defaults (from plugin.yaml)
5. Fail if key not found anywhere

---

### 3.2 CLI Arguments

```bash
# Verbosity
--quiet                          # verbosity = 0
--verbose                        # verbosity = 2
--debug                          # verbosity = 3

# Paths
--config PATH                    # Config file path
--workflow PATH                  # Workflow YAML path
--inbox-dir PATH                 # Inbox directory
--stage-dir PATH                 # Stage directory
--output-dir PATH                # Output directory

# Processing Options
--clean-inbox yes|no|ask         # Clean inbox after import
--clean-stage yes|no|ask         # Clean stage after import
--publish yes|no|ask             # Publish to output
--wipe-id3 yes|no|ask            # Wipe ID3 tags

# Audio Options
--bitrate BITRATE                # Audio bitrate (e.g. 128k, 320k)
--loudnorm                       # Enable loudness normalization
--split-chapters                 # Enable chapter splitting
```

**Data Types:**
- Paths: Converted to `Path` objects, expanded (~, ..)
- Choices: Validated against allowed values
- Flags: Boolean (presence = true)

---

### 3.3 Environment Variables

```bash
# Format: AUDIOMASON_<KEY>
export AUDIOMASON_INBOX_DIR=/path/to/inbox
export AUDIOMASON_STAGE_DIR=/tmp/stage
export AUDIOMASON_OUTPUT_DIR=/path/to/output
export AUDIOMASON_VERBOSITY=2
export AUDIOMASON_BITRATE=192k
export AUDIOMASON_LOUDNORM=true
export AUDIOMASON_SPLIT_CHAPTERS=false
```

**Naming Convention:**
- Prefix: `AUDIOMASON_`
- Key: UPPERCASE, underscores replace dots
- Example: `logging.level` -> `AUDIOMASON_LOGGING_LEVEL`

**Value Parsing:**
- Strings: Used as-is
- Booleans: `true`, `false`, `yes`, `no`, `1`, `0`
- Numbers: Parsed to int/float

---

### 3.4 Config File Format

**Location:** `~/.config/audiomason/config.yaml`

```yaml
# Paths
inbox_dir: ~/Audiobooks/inbox
stage_dir: /tmp/audiomason/stage
output_dir: ~/Audiobooks/output

# Processing defaults
clean_inbox: ask                  # ask | yes | no
clean_stage: yes
publish: ask
wipe_id3: no

# Audio settings
bitrate: 128k
loudnorm: false
split_chapters: false
target_format: mp3

# Metadata
fetch_metadata: true
metadata_providers:
  - googlebooks
  - openlibrary

# Verbosity
verbosity: 1                      # 0-3

# Logging (nested keys)
logging:
  level: normal
  file: ~/audiomason.log
  color: true
```

**Nested Keys:**
- Access via dot notation: `logging.level`
- Environment var: `AUDIOMASON_LOGGING_LEVEL`
- CLI arg: `--logging-level` (if implemented)

---

### 3.5 Config Resolution Example

```yaml
# config.yaml
bitrate: 128k
loudnorm: false
```

```bash
export AUDIOMASON_LOUDNORM=true
```

```bash
python run_wizard.py --bitrate 320k
```

**Resolution:**
- `bitrate`: CLI wins -> `320k`
- `loudnorm`: ENV wins -> `true`
- `verbosity`: Default -> `1` (not set anywhere)

---

## 4. PROCESSING CONTEXT INTERFACE

### 4.1 ProcessingContext Class

```python
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

class State(Enum):
    """Processing state."""
    INIT = "init"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"

@dataclass
class ProcessingContext:
    """Shared context for processing pipeline."""
    
    # REQUIRED FIELDS
    id: str                       # Unique identifier (source name)
    source: Path                  # Source file/directory path
    state: State                  # Current processing state
    
    # OPTIONAL FIELDS (set by plugins)
    stage_dir: Path = None        # Staging directory
    output_dir: Path = None       # Output directory
    output_path: Path = None      # Final output path
    
    # Metadata
    author: str = None
    title: str = None
    year: int = None
    publisher: str = None
    isbn: str = None
    description: str = None
    
    # Files
    converted_files: list[Path] = None
    exported_files: list[Path] = None
    cover_path: Path = None
    cover_url: str = None
    
    # Processing info
    errors: list[str] = None
    warnings: list[str] = None
    timings: dict[str, float] = None
```

---

### 4.2 Context Lifecycle

**1. Initialization (by wizard)**
```python
context = ProcessingContext(
    id="source_name",
    source=Path("/inbox/source"),
    state=State.INIT
)
```

**2. Preflight (by wizard)**
```python
context.author = answers['author']
context.title = answers['title']
```

**3. Processing (by plugins)**
```python
# file_io_sync.import_to_stage()
context.stage_dir = Path("/tmp/stage/source")

# audio_processor_sync.process_files()
context.converted_files = [Path("file1.mp3"), Path("file2.mp3")]

# cover_handler_sync.process()
context.cover_path = Path("/tmp/stage/cover.jpg")

# metadata_sync.process()
context.year = 2020
context.publisher = "Publisher Name"

# file_io_sync.export_to_output()
context.output_path = Path("/output/Author - Title")
context.exported_files = [Path("file1.mp3"), Path("file2.mp3")]
```

**4. Completion**
```python
context.state = State.DONE
```

---

### 4.3 Context Access Patterns

**Reading from context:**
```python
def my_method(self, context: ProcessingContext):
    # Safe access (may be None)
    author = context.author
    
    # Check existence
    if hasattr(context, 'converted_files') and context.converted_files:
        for file in context.converted_files:
            # process file
            pass
    
    # Use getattr with default
    year = getattr(context, 'year', 2020)
```

**Writing to context:**
```python
def my_method(self, context: ProcessingContext):
    # Set attributes
    context.author = "New Author"
    context.custom_field = "custom value"
    
    # Append to lists
    if not hasattr(context, 'warnings'):
        context.warnings = []
    context.warnings.append("Warning message")
    
    # Return modified context
    return context
```

**Contract:**
- Plugins MAY read any context attribute
- Plugins MAY set any context attribute
- Plugins SHOULD NOT delete context attributes
- Plugins MUST return context (modified or new)

---

### 4.4 Standard Context Fields

**Always Present:**
- `id: str` - Source identifier
- `source: Path` - Source path
- `state: State` - Current state

**Set by file_io_sync:**
- `stage_dir: Path` - Staging directory (after import)
- `output_path: Path` - Output directory (after export)
- `exported_files: list[Path]` - Exported files

**Set by wizard (from preflight):**
- `author: str` - Book author
- `title: str` - Book title

**Set by audio_processor_sync:**
- `converted_files: list[Path]` - Converted MP3 files

**Set by cover_handler_sync:**
- `cover_path: Path` - Local cover file path
- `cover_url: str` - Cover download URL (if fetched)

**Set by metadata_sync:**
- `year: int` - Publication year
- `publisher: str` - Publisher name
- `isbn: str` - ISBN number
- `description: str` - Book description

---

## 5. ERROR HANDLING INTERFACE

### 5.1 Exception Hierarchy

```python
class AudioMasonError(Exception):
    """Base exception for all AudioMason errors."""
    pass

class ConfigError(AudioMasonError):
    """Configuration error."""
    pass

class FileError(AudioMasonError):
    """File operation error."""
    pass

class AudioProcessingError(AudioMasonError):
    """Audio processing error."""
    pass

class TaggingError(AudioMasonError):
    """ID3 tagging error."""
    pass

class CoverError(AudioMasonError):
    """Cover handling error."""
    pass

class MetadataError(AudioMasonError):
    """Metadata fetching error."""
    pass

class WizardError(AudioMasonError):
    """Wizard execution error."""
    pass
```

---

### 5.2 Error Handling Contract

**Plugin Methods:**
```python
def my_method(self, context: ProcessingContext):
    """Process something.
    
    Raises:
        SpecificError: When specific condition fails
        AudioMasonError: For general errors
    """
    if error_condition:
        raise SpecificError("Descriptive error message")
    
    return context
```

**Error Message Format:**
- Start with what failed: `"Failed to convert audio"`
- Include details: `"Failed to convert audio: file not found"`
- Include path/name if relevant: `"Failed to convert book.m4a: invalid format"`

**Wizard Behavior:**
- Catch all exceptions during step execution
- Log error with `_log_error()`
- Set `context.state = State.ERROR`
- Add to `context.errors` list
- Continue with next source (if batch processing)
- Exit with code 1 if any errors

---

## 6. PLUGIN DISCOVERY INTERFACE

### 6.1 Plugin Loading

**Discovery:**
```
plugins/
+-- plugin_name_1/
|   +-- plugin.yaml
|   +-- plugin.py
+-- plugin_name_2/
|   +-- plugin.yaml
|   +-- plugin.py
```

**Loading Process:**
1. Scan `plugins/` directory
2. For each subdirectory, look for `plugin.yaml`
3. Parse YAML, validate required fields
4. Extract `entrypoint` (e.g. `plugin:ClassName`)
5. Import module: `from plugins.plugin_name.plugin import ClassName`
6. Instantiate: `instance = ClassName(config)`
7. Store in plugin registry

**Contract:**
- Plugin directory name MUST match `name` in plugin.yaml
- `plugin.py` MUST exist
- `entrypoint` class MUST exist in specified file
- Class constructor MUST accept `config: dict | None`

---

### 6.2 Plugin Registration

**Hardcoded Plugin Map (current implementation):**
```python
plugin_map = {
    'file_io_sync': ('plugins.file_io_sync.plugin', 'FileIOSync'),
    'audio_processor_sync': ('plugins.audio_processor_sync.plugin', 'AudioProcessorSync'),
    'id3_tagger_sync': ('plugins.id3_tagger_sync.plugin', 'ID3TaggerSync'),
    'cover_handler_sync': ('plugins.cover_handler_sync.plugin', 'CoverHandlerSync'),
    'metadata_sync': ('plugins.metadata_sync.plugin', 'MetadataSync'),
}
```

**To Add New Plugin:**
1. Create plugin directory and files
2. Add entry to `plugin_map` in `basic_wizard_sync/plugin.py`
3. Plugin is now available in workflows

**Future:** Plugin map should be auto-discovered from `plugin.yaml` files

---

## 7. WORKFLOW EXECUTION INTERFACE

### 7.1 Execution Flow

```
1. Load workflow YAML
2. Parse and validate structure
3. Detect sources in inbox
4. Show source selection menu
5. For each selected source:
   a. Execute preflight steps (in order)
   b. Collect answers
   c. Create ProcessingContext
   d. Execute processing steps (in order)
      - Check enabled flag
      - Evaluate condition
      - Call plugin method
      - Update context
   e. Handle errors
   f. Mark complete/error
6. Summary
```

---

### 7.2 Step Execution Contract

**Preflight Step:**
```python
def execute_preflight_step(step: WorkflowStep, source_name: str) -> Any:
    """Execute preflight step.
    
    Args:
        step: Step definition from YAML
        source_name: Current source name (for hints)
    
    Returns:
        User's answer (str, bool, or None)
    
    Side effects:
        - Prompts user (if enabled and verbosity allows)
        - Stores answer in wizard.answers dict
    """
```

**Processing Step:**
```python
def execute_processing_step(step: WorkflowStep, context: ProcessingContext) -> ProcessingContext:
    """Execute processing step.
    
    Args:
        step: Step definition from YAML
        context: Current processing context
    
    Returns:
        Updated processing context
    
    Raises:
        WizardError: If step execution fails
    
    Side effects:
        - Loads plugin (if not loaded)
        - Calls plugin method
        - Logs step execution
    """
```

---

## 8. VALIDATION RULES

### 8.1 Workflow YAML Validation

**Required:**
- `workflow.name` must exist
- At least one `preflight_steps` or `processing_steps`
- Each step must have `id`
- Preflight steps must have `type`
- Processing steps must have `plugin` and `method`

**Unique:**
- Step IDs must be unique within workflow
- Step IDs should be valid Python identifiers (lowercase, underscores)

**References:**
- `plugin` must reference existing plugin
- `method` must exist in plugin class
- `condition` references must be valid (`answers.*`, `config.*`)

**Types:**
- `enabled` must be boolean
- `required` must be boolean
- `skip_if_set` must be boolean
- `type` must be one of: `yes_no`, `input`, `menu`

---

### 8.2 Config Validation

**Paths:**
- Must be expandable (~, .., $VAR)
- Directory paths should exist or be creatable
- File paths should be valid

**Choices:**
- Must match allowed values
- Example: `clean_inbox` must be `yes`, `no`, or `ask`

**Verbosity:**
- Must be integer 0-3
- CLI flags override: `--quiet` -> 0, `--verbose` -> 2, `--debug` -> 3

---

## 9. EXTENSION POINTS

### 9.1 Adding New Step Types

Currently hardcoded in `basic_wizard_sync/plugin.py`:

```python
if step.type == 'yes_no':
    # implementation
elif step.type == 'input':
    # implementation
elif step.type == 'menu':
    # implementation
```

**To add new type:**
1. Add `elif` branch in `_execute_preflight_step()`
2. Implement logic
3. Update documentation

**Future:** Pluggable step type system

---

### 9.2 Adding New Condition Operators

Currently hardcoded in `workflow_reader.py`:

```python
if ' == ' in condition:
    # equals
elif ' != ' in condition:
    # not equals
```

**To add new operator:**
1. Add `elif` branch in `evaluate_condition()`
2. Implement logic
3. Update documentation

---

### 9.3 Adding New Plugins

**Steps:**
1. Create `plugins/my_plugin/` directory
2. Create `plugin.yaml` with metadata
3. Create `plugin.py` with class
4. Add to `plugin_map` in `basic_wizard_sync/plugin.py`
5. Use in workflow YAML

**Future:** Auto-discovery from `plugin.yaml` files

---

## 10. COMPLETE EXAMPLE

### 10.1 Custom Plugin

**plugins/custom_plugin/plugin.yaml:**
```yaml
name: custom_plugin
version: 1.0.0
description: My custom plugin
author: Me
entrypoint: plugin:CustomPlugin
interfaces:
  - IProcessor
config:
  custom_option: default_value
```

**plugins/custom_plugin/plugin.py:**
```python
from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError

class CustomError(AudioMasonError):
    """Custom plugin error."""
    pass

class CustomPlugin:
    """My custom plugin."""
    
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.verbosity = self.config.get('verbosity', 1)
        self.custom_option = self.config.get('custom_option', 'default')
    
    def _log_info(self, msg: str) -> None:
        if self.verbosity >= 1:
            print(f"[custom_plugin] {msg}")
    
    def my_method(self, context: ProcessingContext) -> ProcessingContext:
        """Do custom processing."""
        self._log_info("Doing custom processing")
        
        # Access context
        author = context.author
        
        # Modify context
        context.custom_field = "custom value"
        
        # Return context
        return context
    
    def process(self, context: ProcessingContext) -> ProcessingContext:
        """IProcessor interface."""
        return self.my_method(context)
```

---

### 10.2 Custom Workflow

**workflow_sync/custom.yaml:**
```yaml
workflow:
  name: "Custom Workflow"
  description: "Uses custom plugin"
  
  preflight_steps:
    - id: choose_source
      type: menu
      enabled: true
      prompt: "Choose source"
      default: "1"
    
    - id: author
      type: input
      enabled: true
      prompt: "Author"
      required: true
      hint_from: source_name
      hint_pattern: "^([^-]+)"
    
    - id: custom_question
      type: yes_no
      enabled: true
      prompt: "Enable custom feature"
      default: yes
  
  processing_steps:
    - id: import
      plugin: file_io_sync
      method: import_to_stage
      enabled: true
      description: "Import"
    
    - id: custom_step
      plugin: custom_plugin
      method: my_method
      enabled: true
      description: "Custom processing"
      condition: "answers.custom_question == true"
    
    - id: export
      plugin: file_io_sync
      method: export_to_output
      enabled: true
      description: "Export"

verbosity:
  normal:
    - errors
    - prompts
    - workflow_steps
```

---

### 10.3 Usage

```bash
# Run custom workflow
python run_wizard.py --workflow workflow_sync/custom.yaml --debug
```

---

## CHANGELOG

**v1.0.0** - 2026-01-31
- Initial specification
- All interfaces documented
- Examples provided
