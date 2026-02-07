# [WEB] Web UI - COMPLETE IMPLEMENTATION GUIDE

## OK Implementovane API moduly:

1. **Plugin API** (`src/audiomason/api/plugins.py`) OK
2. **Wizard API** (`src/audiomason/api/wizards.py`) OK  
3. **Config API** (`src/audiomason/api/config.py`) OK

## [LIST] TODO - Dokoncit implementaciu:

### **1. Web Server Plugin - Update**
Pridat nove API endpoints do `plugins/web_server/plugin.py`:
- GET/POST/PUT/DELETE `/api/plugins/*`
- GET/POST/PUT/DELETE `/api/wizards/*`
- GET/PUT/POST `/api/config/*`

### **2. Web UI - HTML/JS Updates**
Aktualizovat `plugins/web_server/templates/index.html`:
- Plugins Tab (management interface)
- Wizards Tab (builder interface)
- Config Tab (form editor)

### **3. Ncurses TUI**
Vytvorit `plugins/tui/` plugin:
- Main menu (raspi-config style)
- Plugin manager
- Wizard manager
- Config editor

### **4. Wizard Engine**
Vytvorit `src/audiomason/wizard_engine.py`:
- YAML parser
- Step executor
- Context builder

### **5. Example Wizards**
Vytvorit `wizards/*.yaml`:
- quick_import.yaml
- batch_import.yaml
- complete_import.yaml
- merge_multipart.yaml
- advanced.yaml

## [ROCKET] Nasledujuce kroky:

**Priorita 1:** Dokoncit Web Server plugin updates
**Priorita 2:** Vytvorit Web UI tabs (HTML/JS)
**Priorita 3:** Ncurses TUI implementation
**Priorita 4:** Wizard engine + example wizards
**Priorita 5:** .deb package

## [NOTE] Poznamky:

- API moduly su hotove a funkcne
- Potrebuju integraciu do web servera
- Potrebuju frontend (HTML/JS/CSS)
- Ncurses vyzaduje curses library
