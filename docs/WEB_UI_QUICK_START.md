# 🚀 AudioMason v2 - Web UI Quick Start

**Quick reference for using the new Web UI features**

---

## 🌐 Starting the Web Server

```bash
# Navigate to project directory
cd /path/to/audiomason2-git

# Start web server
python -m plugins.web_server.plugin

# Or use the main executable
./audiomason --web-server
```

**Default URL:** `http://localhost:8080`

---

## 📋 Available Tabs

| Icon | Tab | Description |
|------|-----|-------------|
| 📊 | Dashboard | System status and recent activity |
| 🎵 | Process Books | Upload and process audiobooks |
| 📋 | Queue | View active and completed jobs |
| 🧩 | **Plugins** | **Manage plugins (NEW!)** |
| 🧙 | **Wizards** | **Manage wizards (NEW!)** |
| ⚙️ | Config | System configuration (ENHANCED!) |
| 💾 | Checkpoints | Resume interrupted processing |

---

## 🧩 Plugin Management

### View Plugins
1. Click **🧩 Plugins** tab
2. See all installed plugins with:
   - Name and version
   - Description
   - Author
   - Enable/disable status
   - Interfaces implemented

### Install Plugin

#### From ZIP:
1. Click **📦 Install Plugin**
2. Select **Upload ZIP**
3. Choose `.zip` file
4. Click **Install**

#### From URL:
1. Click **📦 Install Plugin**
2. Select **From URL**
3. Enter plugin URL (e.g., `https://example.com/plugin.zip`)
4. Click **Install**

### Enable/Disable Plugin
- Use the toggle switch next to plugin name
- Green = enabled, Gray = disabled

### Configure Plugin
1. Click **⚙️ Configure** button (if available)
2. Edit settings in modal
3. Click **Save**

### Delete Plugin
1. Click **🗑️ Delete** button
2. Confirm deletion
3. Plugin will be removed

---

## 🧙 Wizard Management

### View Wizards
1. Click **🧙 Wizards** tab
2. See all wizards with:
   - Name
   - Description
   - Number of steps
   - Filename

### Create Wizard
1. Click **✨ Create Wizard**
2. Enter wizard name
3. Add description
4. Write YAML definition:
   ```yaml
   wizard:
     name: My Wizard
     description: What this wizard does
     steps:
       - id: step1
         type: input
         prompt: Enter value
         required: true
   ```
5. Click **Create**

### Run Wizard
- Click **▶️ Run** button
- (Note: Wizard engine not yet implemented)

### Edit Wizard
- Click **✏️ Edit** button
- (Note: Visual editor not yet implemented)

### Delete Wizard
1. Click **🗑️ Delete** button
2. Confirm deletion

---

## ⚙️ Configuration Management

### View Configuration
1. Click **⚙️ Config** tab
2. See all settings organized by category:
   - **Output Directory** - Where processed files go
   - **Default Bitrate** - Audio quality (96k - 320k)
   - **Loudness Normalization** - Enable/disable
   - **Split Chapters** - Enable/disable
   - **Web Server** - Host and port settings
   - **Daemon Mode** - Watch folders and interval

### Edit Settings

#### Text Fields:
- Click in field
- Type new value
- Changes not saved until you click **💾 Save**

#### Dropdowns:
- Click dropdown
- Select option
- Changes not saved until you click **💾 Save**

#### Checkboxes:
- Click checkbox to toggle
- Changes not saved until you click **💾 Save**

#### Numbers:
- Click in field
- Enter number
- Use arrows to increment/decrement
- Changes not saved until you click **💾 Save**

### Save Changes
1. Make your edits
2. Click **💾 Save** button
3. Wait for success message

### Reset to Defaults
1. Click **⚠️ Reset to Defaults**
2. Confirm action
3. All settings restored to defaults

### Refresh Configuration
- Click **🔄 Refresh** to reload current values

---

## 🎨 UI Features

### Alerts
- **Green** - Success (e.g., "Plugin installed")
- **Blue** - Info (e.g., "Loading...")
- **Red** - Error (e.g., "Failed to save")
- Auto-hide after 5 seconds

### Modals
- Click outside modal to close
- Or click **Cancel** button

### Toggle Switches
- Animated smooth transition
- Green when enabled
- Gray when disabled

### Status Indicator
- **Top-right corner**
- Green = Connected to server
- Red = Disconnected
- Auto-reconnect every 5 seconds

---

## 🔌 API Endpoints

### For Plugin Developers

```bash
# List plugins
GET /api/plugins

# Get plugin details
GET /api/plugins/{name}

# Enable plugin
PUT /api/plugins/{name}/enable

# Disable plugin
PUT /api/plugins/{name}/disable

# Delete plugin
DELETE /api/plugins/{name}

# Get plugin config
GET /api/plugins/{name}/config

# Update plugin config
PUT /api/plugins/{name}/config
{
  "setting1": "value1",
  "setting2": "value2"
}

# Install plugin
POST /api/plugins/install
Content-Type: multipart/form-data
- file: plugin.zip
OR
- url: https://example.com/plugin.zip
```

### For Wizard Developers

```bash
# List wizards
GET /api/wizards

# Get wizard
GET /api/wizards/{name}

# Create wizard
POST /api/wizards
{
  "wizard": {
    "name": "My Wizard",
    "description": "...",
    "steps": [...]
  }
}

# Update wizard
PUT /api/wizards/{name}
{
  "wizard": {...}
}

# Delete wizard
DELETE /api/wizards/{name}
```

### For Config Management

```bash
# Get config schema
GET /api/config/schema

# Get current config
GET /api/config

# Update config
PUT /api/config
{
  "output_dir": "/new/path",
  "bitrate": "192k",
  "web_server": {
    "host": "0.0.0.0",
    "port": 8080
  }
}

# Reset to defaults
POST /api/config/reset
```

---

## 🛠️ Troubleshooting

### Plugin Won't Install
- Check ZIP structure (must contain `plugin.yaml`)
- Verify plugin name in manifest
- Check for duplicate plugin names

### Wizard Not Creating
- Validate YAML syntax
- Ensure wizard name is unique
- Check required fields (name, steps)

### Config Not Saving
- Check for validation errors
- Ensure numeric fields have valid numbers
- Verify paths exist

### Page Not Loading
1. Check server is running
2. Verify port 8080 is not in use
3. Check browser console for errors
4. Try refreshing page

---

## 💡 Tips & Tricks

### Plugin Development
1. Create plugin in separate directory
2. Test locally first
3. Package as ZIP with `plugin.yaml` at root
4. Install via URL for easy updates

### Wizard Development
1. Start with simple 1-step wizard
2. Test each step individually
3. Use YAML validator before submitting
4. Document all step parameters

### Configuration
1. Save before changing tabs
2. Use Reset to Defaults if confused
3. Check tooltips for field descriptions
4. Test changes before committing

### Performance
1. Disable unused plugins
2. Adjust web server port if needed
3. Monitor active jobs in Dashboard
4. Use checkpoints for long processes

---

## 📞 Support

### Documentation
- Full docs: `/docs/` directory
- API docs: `http://localhost:8080/docs` (FastAPI auto-generated)

### Reporting Issues
1. Check existing issues
2. Include:
   - Browser version
   - OS version
   - Console errors
   - Steps to reproduce

### Contributing
- Follow existing code style
- Test thoroughly
- Document new features
- Submit pull request

---

**Last Updated:** 2026-01-30  
**Version:** 2.0.0-alpha
