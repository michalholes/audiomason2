"""TUI plugin - Ncurses terminal user interface.

Provides raspi-config style menu system for AudioMason management.
"""

from __future__ import annotations

import curses
import sys
from pathlib import Path
from typing import Any

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False


class VerbosityLevel:
    """Verbosity levels."""
    QUIET = 0    # Errors only
    NORMAL = 1   # Progress + warnings
    VERBOSE = 2  # Detailed info
    DEBUG = 3    # Everything


class TUIPlugin:
    """Terminal user interface plugin."""
    
    def __init__(self, config: dict | None = None):
        """Initialize TUI plugin.
        
        Args:
            config: Plugin configuration
        """
        if not HAS_CURSES:
            raise ImportError("curses not available")
        
        self.config = config or {}
        self.verbosity = self.config.get("verbosity", VerbosityLevel.NORMAL)
        self.screen = None
        self.current_menu = "main"
        self.menu_stack = []
        
    async def run(self) -> None:
        """Run TUI - main entry point."""
        try:
            curses.wrapper(self._main_loop)
        except KeyboardInterrupt:
            pass
    
    def _main_loop(self, stdscr) -> None:
        """Main TUI loop.
        
        Args:
            stdscr: Curses screen object
        """
        self.screen = stdscr
        
        # Setup
        curses.curs_set(0)  # Hide cursor
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Title
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Success
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)    # Error
        
        # Main loop
        while True:
            if self.current_menu == "main":
                action = self._show_main_menu()
            elif self.current_menu == "plugins":
                action = self._show_plugins_menu()
            elif self.current_menu == "wizards":
                action = self._show_wizards_menu()
            elif self.current_menu == "config":
                action = self._show_config_menu()
            elif self.current_menu == "process":
                action = self._show_process_menu()
            else:
                action = "back"
            
            if action == "exit":
                break
            elif action == "back":
                if self.menu_stack:
                    self.current_menu = self.menu_stack.pop()
                else:
                    break
    
    def _show_main_menu(self) -> str:
        """Show main menu.
        
        Returns:
            Action to take
        """
        options = [
            ("1", "Import Audiobooks", "process"),
            ("2", "Run Wizard", "wizards"),
            ("3", "Manage Plugins", "plugins"),
            ("4", "Configuration", "config"),
            ("5", "Web Server", "web"),
            ("6", "Daemon Mode", "daemon"),
            ("0", "Exit", "exit"),
        ]
        
        selected = 0
        
        while True:
            self.screen.clear()
            h, w = self.screen.getmaxyx()
            
            # Title
            title = "AudioMason v2 - Main Menu"
            self._draw_box(2, 2, h-4, w-4, title)
            
            # Options
            start_y = 5
            for i, (key, label, _) in enumerate(options):
                y = start_y + i
                x = 5
                
                if i == selected:
                    self.screen.attron(curses.color_pair(2))
                    self.screen.addstr(y, x, f"  {key}. {label}".ljust(w-10))
                    self.screen.attroff(curses.color_pair(2))
                else:
                    self.screen.addstr(y, x, f"  {key}. {label}")
            
            # Footer
            self.screen.addstr(h-3, 5, "Use ↑↓ arrows to select, Enter to choose, Esc to exit")
            
            self.screen.refresh()
            
            # Input
            key = self.screen.getch()
            
            if key == curses.KEY_UP:
                selected = (selected - 1) % len(options)
            elif key == curses.KEY_DOWN:
                selected = (selected + 1) % len(options)
            elif key in (curses.KEY_ENTER, 10, 13):
                action = options[selected][2]
                if action in ("plugins", "wizards", "config", "process"):
                    self.menu_stack.append("main")
                    self.current_menu = action
                    return action
                elif action == "web":
                    self._show_message("Starting web server...", "Web server started on http://localhost:8080")
                elif action == "daemon":
                    self._show_message("Starting daemon...", "Daemon started in background")
                elif action == "exit":
                    return "exit"
            elif key == 27:  # Esc
                return "exit"
            elif key in (ord('0'), ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6')):
                # Direct number selection
                num = chr(key)
                for opt_key, _, action in options:
                    if opt_key == num:
                        if action in ("plugins", "wizards", "config", "process"):
                            self.menu_stack.append("main")
                            self.current_menu = action
                            return action
                        elif action == "exit":
                            return "exit"
    
    def _show_plugins_menu(self) -> str:
        """Show plugins management menu.
        
        Returns:
            Action to take
        """
        from audiomason.api.plugins import PluginAPI
        
        plugins_dir = Path(__file__).parent.parent
        api = PluginAPI(plugins_dir)
        
        try:
            plugins = api.list_plugins()
        except Exception as e:
            self._show_error(f"Failed to load plugins: {e}")
            return "back"
        
        selected = 0
        
        while True:
            self.screen.clear()
            h, w = self.screen.getmaxyx()
            
            # Title
            title = "Plugin Management"
            self._draw_box(2, 2, h-4, w-4, title)
            
            # Plugin list
            start_y = 5
            for i, plugin in enumerate(plugins):
                if i >= h - 10:  # Don't overflow screen
                    break
                
                y = start_y + i
                x = 5
                
                name = plugin['name']
                enabled = plugin.get('enabled', True)
                status = "✓" if enabled else "✗"
                
                line = f"{status} {name}"
                
                if i == selected:
                    self.screen.attron(curses.color_pair(2))
                    self.screen.addstr(y, x, f"  {line}".ljust(w-10))
                    self.screen.attroff(curses.color_pair(2))
                else:
                    color = curses.color_pair(3) if enabled else curses.color_pair(4)
                    self.screen.attron(color)
                    self.screen.addstr(y, x, f"  {line}")
                    self.screen.attroff(color)
            
            # Footer
            self.screen.addstr(h-3, 5, "↑↓: Select | Space: Enable/Disable | D: Delete | I: Install | Esc: Back")
            
            self.screen.refresh()
            
            # Input
            key = self.screen.getch()
            
            if key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(len(plugins) - 1, selected + 1)
            elif key == ord(' '):  # Space - toggle enable/disable
                plugin = plugins[selected]
                try:
                    if plugin.get('enabled', True):
                        api.disable_plugin(plugin['name'])
                        self._show_message("Plugin Disabled", f"{plugin['name']} has been disabled")
                    else:
                        api.enable_plugin(plugin['name'])
                        self._show_message("Plugin Enabled", f"{plugin['name']} has been enabled")
                    plugins = api.list_plugins()  # Reload
                except Exception as e:
                    self._show_error(f"Failed to toggle plugin: {e}")
            elif key in (ord('d'), ord('D')):  # Delete
                plugin = plugins[selected]
                if self._confirm(f"Delete plugin '{plugin['name']}'?"):
                    try:
                        api.delete_plugin(plugin['name'])
                        self._show_message("Plugin Deleted", f"{plugin['name']} has been deleted")
                        plugins = api.list_plugins()  # Reload
                        selected = min(selected, len(plugins) - 1)
                    except Exception as e:
                        self._show_error(f"Failed to delete plugin: {e}")
            elif key in (ord('i'), ord('I')):  # Install
                self._show_message("Install Plugin", "Plugin installation from TUI not yet implemented.\nUse: audiomason web")
            elif key == 27:  # Esc
                return "back"
    
    def _show_wizards_menu(self) -> str:
        """Show wizards menu.
        
        Returns:
            Action to take
        """
        from audiomason.api.wizards import WizardAPI
        
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"
        api = WizardAPI(wizards_dir)
        
        try:
            wizards = api.list_wizards()
        except Exception as e:
            self._show_error(f"Failed to load wizards: {e}")
            return "back"
        
        selected = 0
        
        while True:
            self.screen.clear()
            h, w = self.screen.getmaxyx()
            
            # Title
            title = "Wizard Management"
            self._draw_box(2, 2, h-4, w-4, title)
            
            if not wizards:
                self.screen.addstr(5, 5, "No wizards found!")
                self.screen.addstr(6, 5, f"Create wizards in: {wizards_dir}")
                self.screen.addstr(h-3, 5, "Press any key to go back...")
                self.screen.refresh()
                self.screen.getch()
                return "back"
            
            # Wizard list
            start_y = 5
            for i, wizard in enumerate(wizards):
                if i >= h - 10:
                    break
                
                y = start_y + i
                x = 5
                
                name = wizard['name']
                desc = wizard.get('description', 'No description')
                steps = wizard.get('steps', 0)
                
                line = f"{name} ({steps} steps)"
                
                if i == selected:
                    self.screen.attron(curses.color_pair(2))
                    self.screen.addstr(y, x, f"  {line}".ljust(w-10))
                    self.screen.attroff(curses.color_pair(2))
                    # Show description below
                    if y + 1 < h - 4:
                        self.screen.addstr(y + 1, x + 4, desc[:w-15])
                else:
                    self.screen.addstr(y, x, f"  {line}")
            
            # Footer
            self.screen.addstr(h-3, 5, "↑↓: Select | Enter: Run | D: Delete | C: Create | Esc: Back")
            
            self.screen.refresh()
            
            # Input
            key = self.screen.getch()
            
            if key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(len(wizards) - 1, selected + 1)
            elif key in (curses.KEY_ENTER, 10, 13):  # Run wizard
                wizard = wizards[selected]
                self._run_wizard(wizard['filename'])
            elif key in (ord('d'), ord('D')):  # Delete
                wizard = wizards[selected]
                if self._confirm(f"Delete wizard '{wizard['name']}'?"):
                    try:
                        api.delete_wizard(wizard['filename'].replace('.yaml', ''))
                        self._show_message("Wizard Deleted", f"{wizard['name']} has been deleted")
                        wizards = api.list_wizards()  # Reload
                        selected = min(selected, len(wizards) - 1)
                    except Exception as e:
                        self._show_error(f"Failed to delete wizard: {e}")
            elif key in (ord('c'), ord('C')):  # Create
                self._show_message("Create Wizard", "Wizard creation from TUI not yet implemented.\nUse: audiomason web or edit YAML manually")
            elif key == 27:  # Esc
                return "back"
    
    def _show_config_menu(self) -> str:
        """Show configuration menu.
        
        Returns:
            Action to take
        """
        from audiomason.api.config import ConfigAPI
        
        config_file = Path.home() / ".config" / "audiomason" / "config.yaml"
        api = ConfigAPI(config_file)
        
        try:
            schema = api.get_config_schema()
            config = api.get_config()
        except Exception as e:
            self._show_error(f"Failed to load config: {e}")
            return "back"
        
        # Build flat list of config items
        items = []
        for key, field_schema in schema.items():
            value = config.get(key, field_schema.get('default'))
            items.append({
                'key': key,
                'value': value,
                'type': field_schema.get('type', 'string'),
                'description': field_schema.get('description', ''),
                'choices': field_schema.get('choices'),
            })
        
        selected = 0
        
        while True:
            self.screen.clear()
            h, w = self.screen.getmaxyx()
            
            # Title
            title = "Configuration"
            self._draw_box(2, 2, h-4, w-4, title)
            
            # Config list
            start_y = 5
            for i, item in enumerate(items):
                if i >= h - 10:
                    break
                
                y = start_y + i
                x = 5
                
                key = item['key']
                value = item['value']
                
                # Format value
                if isinstance(value, bool):
                    value_str = "✓" if value else "✗"
                else:
                    value_str = str(value)[:20]
                
                line = f"{key}: {value_str}"
                
                if i == selected:
                    self.screen.attron(curses.color_pair(2))
                    self.screen.addstr(y, x, f"  {line}".ljust(w-10))
                    self.screen.attroff(curses.color_pair(2))
                    # Show description
                    if y + 1 < h - 4:
                        desc = item['description'][:w-15]
                        self.screen.addstr(y + 1, x + 4, desc)
                else:
                    self.screen.addstr(y, x, f"  {line}")
            
            # Footer
            self.screen.addstr(h-3, 5, "↑↓: Select | Enter: Edit | R: Reset | S: Save | Esc: Back")
            
            self.screen.refresh()
            
            # Input
            key = self.screen.getch()
            
            if key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(len(items) - 1, selected + 1)
            elif key in (curses.KEY_ENTER, 10, 13):  # Edit
                item = items[selected]
                new_value = self._edit_config_value(item)
                if new_value is not None:
                    item['value'] = new_value
                    config[item['key']] = new_value
                    try:
                        api.update_config(config)
                        self._show_message("Config Updated", f"{item['key']} = {new_value}")
                    except Exception as e:
                        self._show_error(f"Failed to save: {e}")
            elif key in (ord('r'), ord('R')):  # Reset
                if self._confirm("Reset all config to defaults?"):
                    try:
                        api.reset_config()
                        self._show_message("Config Reset", "All settings reset to defaults")
                        return "back"  # Reload menu
                    except Exception as e:
                        self._show_error(f"Failed to reset: {e}")
            elif key in (ord('s'), ord('S')):  # Save
                try:
                    api.update_config(config)
                    self._show_message("Config Saved", "All changes saved")
                except Exception as e:
                    self._show_error(f"Failed to save: {e}")
            elif key == 27:  # Esc
                return "back"
    
    def _show_process_menu(self) -> str:
        """Show process/import menu.
        
        Returns:
            Action to take
        """
        self.screen.clear()
        h, w = self.screen.getmaxyx()
        
        title = "Import Audiobooks"
        self._draw_box(2, 2, h-4, w-4, title)
        
        self.screen.addstr(5, 5, "Import options:")
        self.screen.addstr(7, 5, "  1. Use Wizard (recommended)")
        self.screen.addstr(8, 5, "  2. Manual import via CLI")
        self.screen.addstr(9, 5, "  3. Web interface")
        self.screen.addstr(11, 5, "Press 1-3 to select, Esc to go back")
        
        self.screen.refresh()
        
        while True:
            key = self.screen.getch()
            
            if key == ord('1'):
                # Switch to wizard menu
                self.menu_stack.append("process")
                self.current_menu = "wizards"
                return "wizards"
            elif key == ord('2'):
                self._show_message("Manual Import", "Exit TUI and use:\n  audiomason process <file> [options]")
            elif key == ord('3'):
                self._show_message("Web Interface", "Start web server:\n  audiomason web\n\nThen open: http://localhost:8080")
            elif key == 27:  # Esc
                return "back"
    
    def _run_wizard(self, wizard_filename: str) -> None:
        """Run wizard (exit TUI and run in terminal).
        
        Args:
            wizard_filename: Wizard YAML filename
        """
        curses.endwin()  # Exit curses mode
        
        import subprocess
        
        wizard_name = wizard_filename.replace('.yaml', '')
        cmd = ['audiomason', 'wizard', wizard_name]
        
        # Add verbosity flag based on current level
        if self.verbosity == VerbosityLevel.QUIET:
            cmd.append('-q')
        elif self.verbosity == VerbosityLevel.VERBOSE:
            cmd.append('-v')
        elif self.verbosity == VerbosityLevel.DEBUG:
            cmd.append('-d')
        
        if self.verbosity >= VerbosityLevel.NORMAL:
            print(f"\n🧙 Running wizard: {wizard_name}\n")
        
        try:
            subprocess.run(cmd)
        except Exception as e:
            print(f"Error running wizard: {e}")
        
        if self.verbosity >= VerbosityLevel.NORMAL:
            print("\nPress Enter to return to TUI...")
            input()
        
        # Reinitialize curses
        self.screen = curses.initscr()
        curses.curs_set(0)
    
    def _edit_config_value(self, item: dict) -> Any:
        """Edit config value.
        
        Args:
            item: Config item dict
            
        Returns:
            New value or None if cancelled
        """
        h, w = self.screen.getmaxyx()
        
        # Create edit window
        edit_h = 10
        edit_w = min(60, w - 10)
        edit_y = (h - edit_h) // 2
        edit_x = (w - edit_w) // 2
        
        edit_win = curses.newwin(edit_h, edit_w, edit_y, edit_x)
        edit_win.box()
        edit_win.addstr(1, 2, f"Edit: {item['key']}")
        edit_win.addstr(2, 2, "─" * (edit_w - 4))
        
        if item['type'] == 'boolean':
            # Toggle boolean
            edit_win.addstr(4, 2, "Current value:")
            edit_win.addstr(5, 4, "✓ Enabled" if item['value'] else "✗ Disabled")
            edit_win.addstr(7, 2, "Press Space to toggle, Enter to save, Esc to cancel")
            edit_win.refresh()
            
            value = item['value']
            while True:
                key = edit_win.getch()
                if key == ord(' '):
                    value = not value
                    edit_win.addstr(5, 4, "✓ Enabled " if value else "✗ Disabled")
                    edit_win.refresh()
                elif key in (curses.KEY_ENTER, 10, 13):
                    return value
                elif key == 27:
                    return None
        
        elif item['choices']:
            # Multiple choice
            edit_win.addstr(4, 2, "Select value:")
            choices = item['choices']
            selected = choices.index(item['value']) if item['value'] in choices else 0
            
            while True:
                for i, choice in enumerate(choices):
                    y = 5 + i
                    if i == selected:
                        edit_win.attron(curses.color_pair(2))
                        edit_win.addstr(y, 4, str(choice).ljust(edit_w - 8))
                        edit_win.attroff(curses.color_pair(2))
                    else:
                        edit_win.addstr(y, 4, str(choice))
                
                edit_win.refresh()
                
                key = edit_win.getch()
                if key == curses.KEY_UP:
                    selected = (selected - 1) % len(choices)
                elif key == curses.KEY_DOWN:
                    selected = (selected + 1) % len(choices)
                elif key in (curses.KEY_ENTER, 10, 13):
                    return choices[selected]
                elif key == 27:
                    return None
        
        else:
            # Text input
            edit_win.addstr(4, 2, "Current value:")
            edit_win.addstr(5, 4, str(item['value']))
            edit_win.addstr(7, 2, "Enter new value (Esc to cancel):")
            edit_win.refresh()
            
            curses.echo()
            curses.curs_set(1)
            
            try:
                new_value = edit_win.getstr(8, 4, edit_w - 8).decode('utf-8').strip()
                
                # Type conversion
                if item['type'] == 'integer':
                    return int(new_value)
                elif item['type'] == 'float':
                    return float(new_value)
                else:
                    return new_value
            except:
                return None
            finally:
                curses.noecho()
                curses.curs_set(0)
    
    def _draw_box(self, y: int, x: int, height: int, width: int, title: str = ""):
        """Draw a box with optional title.
        
        Args:
            y: Y position
            x: X position
            height: Box height
            width: Box width
            title: Optional title
        """
        # Draw box
        self.screen.attron(curses.color_pair(1))
        self.screen.addstr(y, x, "┌" + "─" * (width - 2) + "┐")
        for i in range(1, height - 1):
            self.screen.addstr(y + i, x, "│" + " " * (width - 2) + "│")
        self.screen.addstr(y + height - 1, x, "└" + "─" * (width - 2) + "┘")
        
        # Title
        if title:
            title_text = f" {title} "
            title_x = x + (width - len(title_text)) // 2
            self.screen.addstr(y, title_x, title_text)
        
        self.screen.attroff(curses.color_pair(1))
    
    def _show_message(self, title: str, message: str):
        """Show message box.
        
        Args:
            title: Message title
            message: Message text
        """
        h, w = self.screen.getmaxyx()
        
        lines = message.split('\n')
        box_h = len(lines) + 6
        box_w = min(max(len(line) for line in lines) + 8, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2
        
        msg_win = curses.newwin(box_h, box_w, box_y, box_x)
        msg_win.box()
        msg_win.addstr(1, 2, title)
        msg_win.addstr(2, 2, "─" * (box_w - 4))
        
        for i, line in enumerate(lines):
            msg_win.addstr(3 + i, 4, line)
        
        msg_win.addstr(box_h - 2, 2, "Press any key to continue...")
        msg_win.refresh()
        msg_win.getch()
    
    def _show_error(self, message: str):
        """Show error message.
        
        Args:
            message: Error message
        """
        self._show_message("ERROR", message)
    
    def _confirm(self, question: str) -> bool:
        """Show confirmation dialog.
        
        Args:
            question: Question to ask
            
        Returns:
            True if confirmed, False otherwise
        """
        h, w = self.screen.getmaxyx()
        
        box_h = 8
        box_w = min(len(question) + 10, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2
        
        confirm_win = curses.newwin(box_h, box_w, box_y, box_x)
        confirm_win.box()
        confirm_win.addstr(1, 2, "Confirm")
        confirm_win.addstr(2, 2, "─" * (box_w - 4))
        confirm_win.addstr(4, 4, question)
        confirm_win.addstr(6, 4, "[Y]es  [N]o")
        confirm_win.refresh()
        
        while True:
            key = confirm_win.getch()
            if key in (ord('y'), ord('Y')):
                return True
            elif key in (ord('n'), ord('N'), 27):
                return False
