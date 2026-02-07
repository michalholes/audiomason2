# [ROCKET] AudioMason v2 - Quick Start Guide

## OK MVP is READY!

AudioMason v2 MVP is now complete with:
- OK Audio conversion (M4A/Opus -> MP3)
- OK Chapter detection and splitting
- OK Command-line interface
- OK Complete pipeline system

---

## [PKG] Installation on Raspberry Pi

### 1. Transfer Project

```bash
# From your Mac, transfer to Raspberry Pi:
scp -r audiomason-v2-implementation pi@raspberrypi.local:~/
```

### 2. Install Dependencies

```bash
ssh pi@raspberrypi.local

# Install FFmpeg (required!)
sudo apt-get update
sudo apt-get install -y ffmpeg

# Verify FFmpeg is installed
ffmpeg -version
```

### 3. Make audiomason Executable

```bash
cd ~/audiomason-v2-implementation
chmod +x audiomason
```

---

## [GOAL] Usage

### Basic Usage

```bash
# Process a single M4A file
./audiomason process book.m4a

# You will be prompted for:
# - Author name
# - Book title

# Output will be in: ~/Audiobooks/output/Author - Title/
```

### With Options

```bash
# Provide metadata via command line
./audiomason process book.m4a --author "George Orwell" --title "1984"

# High quality conversion
./audiomason process book.m4a --bitrate 320k

# Enable loudness normalization
./audiomason process book.m4a --loudnorm

# Split M4A by chapters
./audiomason process book.m4a --split-chapters

# Combine options
./audiomason process book.m4a \
  --author "George Orwell" \
  --title "1984" \
  --bitrate 320k \
  --loudnorm \
  --split-chapters
```

### Convert Multiple Files

```bash
# Process all M4A files in a directory
for file in /path/to/books/*.m4a; do
  ./audiomason process "$file"
done
```

---

## [STATS] Example Session

```
$ ./audiomason process my_book.m4a

[AUDIO] AudioMason v2 - Processing: my_book.m4a

? Author: George Orwell
[DOC] Title: 1984

   Author: George Orwell
   Title: 1984

[PLUG] Loading plugins...
   OK audio_processor
   OK file_io

? Executing pipeline...

OK Processing complete!

? Output: /home/pi/Audiobooks/output/George Orwell - 1984

[WARN]?  Warnings:
   - Imported to: /tmp/audiomason/stage/book_abc12345
   - M4A file: 15 chapter(s) detected
   - Split into 15 files
   - Exported 15 file(s) to: /home/pi/Audiobooks/output/George Orwell - 1984
```

---

## ? Configuration

### Change Output Directory

Edit `~/.config/audiomason/config.yaml`:

```yaml
# Output directory for processed books
output_dir: /media/usb/Audiobooks

# Audio quality
bitrate: 192k
loudnorm: true

# Chapter splitting
split_chapters: true
```

### Environment Variables

```bash
# Override config with environment variables
export AUDIOMASON_OUTPUT_DIR=/media/usb/Audiobooks
export AUDIOMASON_BITRATE=320k
export AUDIOMASON_LOUDNORM=true

./audiomason process book.m4a
```

---

## [TEST] Testing

### Test 1: Help

```bash
./audiomason
# Should show usage information
```

### Test 2: Version

```bash
./audiomason version
# Should show: AudioMason v2.0.0-alpha
```

### Test 3: MVP Test Suite

```bash
python3 tests/test_mvp.py
# Should output: OK ALL TESTS PASSED
```

### Test 4: Real File

```bash
# Try with a real M4A file
./audiomason process test.m4a --author "Test Author" --title "Test Book"

# Check output directory
ls ~/Audiobooks/output/Test\ Author\ -\ Test\ Book/
```

---

## ? Output Structure

```
~/Audiobooks/output/
+-- George Orwell - 1984/
    +-- 01.mp3    # Chapter 1
    +-- 02.mp3    # Chapter 2
    +-- 03.mp3    # Chapter 3
    +-- ...

# Or if not splitting chapters:
~/Audiobooks/output/
+-- George Orwell - 1984/
    +-- 1984.mp3  # Single file
```

---

## ? Troubleshooting

### "FFmpeg not found"

```bash
# Install FFmpeg
sudo apt-get install ffmpeg

# Verify installation
ffmpeg -version
```

### "Permission denied: ./audiomason"

```bash
# Make executable
chmod +x audiomason
```

### "No module named 'audiomason'"

```bash
# Make sure you're in the correct directory
cd ~/audiomason-v2-implementation

# And running with ./
./audiomason process book.m4a
```

### Files not being converted

- Check that input file exists
- Check that FFmpeg is installed
- Try running with verbose output (add `print()` statements in plugins if needed)

---

## [GOAL] What Works

### OK Fully Implemented

- M4A -> MP3 conversion
- Opus -> MP3 conversion
- Chapter detection (M4A)
- Chapter splitting
- Loudness normalization
- Custom bitrate
- Manual metadata input
- CLI interface
- Pipeline execution
- File organization

### ? Not Yet Implemented

- Metadata fetching (Google Books, OpenLibrary)
- Cover extraction/download
- ID3 tag writing
- Preflight detection (auto-guess author/title)
- Batch processing with smart grouping
- Progress bars (Rich library)
- Verbosity modes (quiet/normal/verbose/debug)
- Daemon mode
- Web UI

---

## [DOC] Common Workflows

### Workflow 1: Simple Conversion

```bash
./audiomason process book.m4a
# Enter author and title when prompted
```

### Workflow 2: Batch with Same Settings

```bash
for file in *.m4a; do
  ./audiomason process "$file" --bitrate 320k --loudnorm
done
```

### Workflow 3: High Quality Split

```bash
./audiomason process audiobook.m4a \
  --author "Author Name" \
  --title "Book Title" \
  --bitrate 320k \
  --loudnorm \
  --split-chapters
```

---

## [ROCKET] Next Steps

After testing MVP, you can:

1. **Add metadata fetching** - Integrate Google Books API
2. **Add cover handling** - Extract/download/embed covers
3. **Add preflight detection** - Auto-guess author/title from filename
4. **Add progress indicators** - Rich library progress bars
5. **Add verbosity modes** - quiet/normal/verbose/debug
6. **Improve error handling** - Better error messages
7. **Add batch processing** - Smart question grouping

---

## ? Tips

- **Start simple**: Test with one book first
- **Check FFmpeg**: Make sure it's installed and working
- **Use full paths**: When in doubt, use absolute paths
- **Check output**: Verify files are created in output directory
- **Read errors**: Error messages have suggestions for fixes

---

## ? Support

If MVP works:
- OK Core is solid
- OK Plugins are working
- OK Pipeline is executing
- OK You can start processing real books!

If something fails:
1. Check FFmpeg is installed
2. Check file exists and is readable
3. Check permissions on output directory
4. Run MVP test suite: `python3 tests/test_mvp.py`

---

**Status:** MVP Complete OK | Ready for Real Testing [ROCKET]
