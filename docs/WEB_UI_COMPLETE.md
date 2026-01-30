# 🌐 Web UI - COMPLETE IMPLEMENTATION GUIDE

## ✅ Implementované API moduly:

1. **Plugin API** (`src/audiomason/api/plugins.py`) ✅
2. **Wizard API** (`src/audiomason/api/wizards.py`) ✅  
3. **Config API** (`src/audiomason/api/config.py`) ✅

## 📋 TODO - Dokončiť implementáciu:

### **1. Web Server Plugin - Update**
Pridať nové API endpoints do `plugins/web_server/plugin.py`:
- GET/POST/PUT/DELETE `/api/plugins/*`
- GET/POST/PUT/DELETE `/api/wizards/*`
- GET/PUT/POST `/api/config/*`

### **2. Web UI - HTML/JS Updates**
Aktualizovať `plugins/web_server/templates/index.html`:
- Plugins Tab (management interface)
- Wizards Tab (builder interface)
- Config Tab (form editor)

### **3. Ncurses TUI**
Vytvoriť `plugins/tui/` plugin:
- Main menu (raspi-config style)
- Plugin manager
- Wizard manager
- Config editor

### **4. Wizard Engine**
Vytvoriť `src/audiomason/wizard_engine.py`:
- YAML parser
- Step executor
- Context builder

### **5. Example Wizards**
Vytvoriť `wizards/*.yaml`:
- quick_import.yaml
- batch_import.yaml
- complete_import.yaml
- merge_multipart.yaml
- advanced.yaml

## 🚀 Nasledujúce kroky:

**Priorita 1:** Dokončiť Web Server plugin updates
**Priorita 2:** Vytvoriť Web UI tabs (HTML/JS)
**Priorita 3:** Ncurses TUI implementation
**Priorita 4:** Wizard engine + example wizards
**Priorita 5:** .deb package

## 📝 Poznámky:

- API moduly sú hotové a funkčné
- Potrebujú integráciu do web servera
- Potrebujú frontend (HTML/JS/CSS)
- Ncurses vyžaduje curses library
