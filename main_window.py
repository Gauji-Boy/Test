from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar, QDockWidget, QApplication, QWidget, QVBoxLayout, QMenuBar, QMenu, QFileDialog, QLabel, QToolBar, QInputDialog, QMessageBox, QLineEdit, QPushButton, QToolButton, QComboBox
from PySide6.QtGui import QAction, QIcon, QTextCharFormat, QColor, QTextCursor, QActionGroup
from PySide6.QtCore import Qt, QProcess, Signal, Slot, QPoint, QModelIndex, QThreadPool, QStandardPaths, QObject
from file_explorer import FileExplorer
from code_editor import CodeEditor
from interactive_terminal import InteractiveTerminal # Use the new interactive terminal
from network_manager import NetworkManager # Import NetworkManager
from connection_dialog import ConnectionDialog # Import ConnectionDialog
from ai_assistant_window import AIAssistantWindow # Import the AI Assistant Window
from ai_tools import AITools # Import AITools
import tempfile
import os
import sys
import shutil # For rmtree
import json # Import json for structured messages
import black # Import black for synchronous formatting

class MainWindow(QMainWindow):
    # Signals for AI Tools to get results back from MainWindow
    ai_get_current_code_result = Signal(str)
    ai_read_file_result = Signal(str, str) # file_path, content/error_message
    ai_write_file_result = Signal(str, bool, str) # file_path, success, message
    ai_list_directory_result = Signal(str, str) # path, json_string_of_contents/error_message

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aether Editor")
        self.setGeometry(100, 100, 1200, 800)

        self.threadpool = QThreadPool() # Initialize QThreadPool for background tasks
        print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")

        self.threadpool = QThreadPool() # Initialize QThreadPool for background tasks
        print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")


        self.current_process = None # To hold the QProcess instance
        self.is_updating_from_network = False # Flag to prevent echo loop

        self.network_manager = NetworkManager(self) # Initialize NetworkManager
        self.ai_tools = AITools(self) # Initialize AITools

        # Connect AITools signals to MainWindow slots for execution
        self.ai_tools.get_current_code_signal.connect(self._ai_handle_get_current_code_request)
        self.ai_tools.read_file_signal.connect(self._ai_handle_read_file_request)
        self.ai_tools.write_file_signal.connect(self._ai_handle_write_file_request)
        self.ai_tools.list_directory_signal.connect(self._ai_handle_list_directory_request)

        # State variables for collaborative editing
        self.is_host = False
        self.has_control = False # True if this instance has the editing token
        self.tab_data_map = {} # Map to store tab-specific data (e.g., file paths)

        self.current_run_mode = "Run" # Initial run mode
        self.setup_status_bar() # Initialize status bar labels first
        self.setup_toolbar() # Re-enable toolbar for the new button
        self.setup_ui()
        self.setup_menu()
        self.setup_network_connections() # Setup network signals and slots
        self.update_ui_for_control_state() # Initial UI update
        self.load_session() # Load session on startup

    def setup_ui(self):
        # Central Editor View (QTabWidget)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tab_widget)
        self.tab_widget.currentChanged.connect(self._update_status_bar_and_language_selector_on_tab_change)

        # File Explorer Panel (Left Sidebar)
        self.file_explorer_dock = QDockWidget("File Explorer", self)
        self.file_explorer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.file_explorer = FileExplorer()
        self.file_explorer_dock.setWidget(self.file_explorer)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.file_explorer_dock)
        self.file_explorer.file_opened.connect(self.open_new_tab)
        self.file_explorer.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_explorer.customContextMenuRequested.connect(self.on_file_tree_context_menu)

        # Integrated Terminal Panel (Bottom Dock)
        self.terminal_dock = QDockWidget("Integrated Terminal", self)
        self.terminal_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.terminal_widget = InteractiveTerminal() # Use InteractiveTerminal
        self.terminal_dock.setWidget(self.terminal_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal_dock)

        # Initial empty tab
        self.open_new_tab() # This will now correctly set initial tab data

    def setup_menu(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")
        new_file_action = QAction("&New File", self)
        new_file_action.setShortcut("Ctrl+N")
        new_file_action.triggered.connect(self.create_new_file)
        file_menu.addAction(new_file_action)

        save_file_action = QAction("&Save", self)
        save_file_action.setShortcut("Ctrl+S")
        save_file_action.triggered.connect(self.save_current_file)
        file_menu.addAction(save_file_action)

        save_file_as_action = QAction("Save &As...", self)
        save_file_as_action.setShortcut("Ctrl+Shift+S")
        save_file_as_action.triggered.connect(self.save_current_file_as)
        file_menu.addAction(save_file_as_action)

        open_file_action = QAction("&Open File...", self)
        open_file_action.setShortcut("Ctrl+Shift+O")
        open_file_action.triggered.connect(self.open_file)
        file_menu.addAction(open_file_action)

        open_folder_action = QAction("&Open Folder...", self)
        open_folder_action.setShortcut("Ctrl+O")
        open_folder_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_folder_action)

        exit_action = QAction("&Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")
        format_code_action = QAction("&Format Code", self)
        format_code_action.setShortcut("Ctrl+Shift+I")
        format_code_action.triggered.connect(self.format_current_code)
        edit_menu.addAction(format_code_action)

        # View Menu (Placeholder for now)
        view_menu = menu_bar.addMenu("&View")

        # Run Menu
        run_menu = menu_bar.addMenu("&Run")

        # Run Button in Run Menu (No language selector here anymore)

        # Session Menu
        session_menu = menu_bar.addMenu("&Session")
        self.start_host_action = QAction("Start &Hosting Session", self)
        self.start_host_action.setShortcut("Ctrl+H")
        self.start_host_action.triggered.connect(self.start_hosting_session)
        session_menu.addAction(self.start_host_action)

        self.connect_host_action = QAction("&Connect to Host...", self)
        self.connect_host_action.setShortcut("Ctrl+J")
        self.connect_host_action.triggered.connect(self.connect_to_host_session)
        session_menu.addAction(self.connect_host_action)

        self.stop_session_action = QAction("&Stop Current Session", self)
        self.stop_session_action.setShortcut("Ctrl+T")
        self.stop_session_action.triggered.connect(self.stop_current_session)
        session_menu.addAction(self.stop_session_action)

    def setup_toolbar(self):
        toolbar = self.addToolBar("Main Toolbar")
        
        # Run/Debug Dropdown Button
        # Mode Selector (QComboBox)
        self.language_selector = QComboBox(self)
        self.language_selector.addItem("Plain Text") # Default
        self.language_selector.addItem("Python")
        self.language_selector.addItem("JavaScript")
        self.language_selector.addItem("HTML")
        self.language_selector.addItem("CSS")
        self.language_selector.addItem("JSON")
        self.language_selector.setFixedWidth(100) # Adjust width as needed
        toolbar.addWidget(self.language_selector)

        # Add Run/Debug Mode Selector
        self.run_mode_selector = QComboBox(self)
        self.run_mode_selector.addItem("Run")
        self.run_mode_selector.addItem("Debug")
        self.run_mode_selector.setFixedWidth(80) # Adjust width as needed
        toolbar.addWidget(self.run_mode_selector)

        # Play Button (QAction)
        self.run_debug_action_button = QAction(QIcon.fromTheme("media-playback-start"), "Run", self)
        self.run_debug_action_button.setToolTip("Execute Code (F5)")
        self.run_debug_action_button.setShortcut("F5")
        self.run_debug_action_button.triggered.connect(self.handle_execution)
        toolbar.addAction(self.run_debug_action_button)

        # Add other buttons to the toolbar
        self.request_control_button = QPushButton("Request Control", self)
        self.request_control_button.clicked.connect(self.request_control)
        toolbar.addWidget(self.request_control_button)
        self.request_control_button.setEnabled(False) # Initially disabled

        # AI Assistant Button
        self.ai_assistant_button = QPushButton("AI Assistant", self)
        self.ai_assistant_button.setIcon(QIcon.fromTheme("accessories-text-editor")) # Placeholder icon
        self.ai_assistant_button.clicked.connect(self.open_ai_assistant)
        toolbar.addWidget(self.ai_assistant_button)

        # Add a permanent widget to the status bar for role/control status
        self.control_status_label = QLabel("Not in session")
        self.status_bar.addPermanentWidget(self.control_status_label)
        
        # Initial update of the run/debug button
        self.update_run_debug_button_ui()

    def setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Status bar labels
        self.cursor_pos_label = QLabel("Ln 1, Col 1")
        self.language_label = QLabel("Language: Plain Text")
        self.git_branch_label = QLabel("Git: N/A") # Placeholder for Git integration

        self.status_bar.addPermanentWidget(self.cursor_pos_label)
        self.status_bar.addPermanentWidget(self.language_label)
        self.status_bar.addPermanentWidget(self.git_branch_label)

    def setup_network_connections(self):
        self.network_manager.data_received.connect(self.on_network_data_received)
        self.network_manager.status_changed.connect(self.status_bar.showMessage)
        self.network_manager.peer_connected.connect(self.on_peer_connected)
        self.network_manager.peer_disconnected.connect(self.on_peer_disconnected)
        
        # New signals for control management
        self.network_manager.control_request_received.connect(self.on_control_request_received)
        self.network_manager.control_granted.connect(self.on_control_granted)
        self.network_manager.control_revoked.connect(self.on_control_revoked)
        
        # New signals for control management
        self.network_manager.control_request_received.connect(self.on_control_request_received)
        self.network_manager.control_granted.connect(self.on_control_granted)
        self.network_manager.control_declined.connect(self.on_control_declined) # Connect new signal
        self.network_manager.control_revoked.connect(self.on_control_revoked)

    EXTENSION_TO_LANGUAGE = {
        ".py": "Python",
        ".js": "JavaScript",
        ".cpp": "C++",
        ".cxx": "C++",
        ".c": "C",
        ".java": "Java",
        ".html": "HTML",
        ".txt": "Plain Text"
    }

    RUNNER_CONFIG = {
        "Python": {
            "run": ["python", "-u", "{file}"],
            "debug": ["python", "-m", "pdb", "{file}"]
        },
        "C++": {
            "run": ["g++", "{file}", "-o", "{output_file}", "&&", "{output_file}"],
            "debug": ["gdb", "{output_file}"]
        },
        "JavaScript": {
            "run": ["node", "{file}"],
            "debug": ["node", "--inspect-brk", "{file}"]
        }
    }

    def _update_status_bar_and_language_selector_on_tab_change(self, index):
        editor = self.tab_widget.widget(index)
        if isinstance(editor, CodeEditor):
            # Update status bar labels
            self.language_label.setText(f"Language: {editor.current_language}")
            self._update_cursor_position_label(editor.textCursor().blockNumber() + 1, editor.textCursor().columnNumber() + 1)
            
            # Auto-select language in QComboBox
            # Get tab data to determine if it's an untitled file
            tab_data = self.tab_data_map.get(editor, {})
            file_path = tab_data.get("path") if tab_data else None

            if file_path:
                file_extension = os.path.splitext(file_path)[1].lower()
                detected_language = self.EXTENSION_TO_LANGUAGE.get(file_extension, "Plain Text")
                idx = self.language_selector.findText(detected_language)
                if idx != -1:
                    self.language_selector.setCurrentIndex(idx)
                else:
                    default_idx = self.language_selector.findText("Plain Text")
                    if default_idx != -1:
                        self.language_selector.setCurrentIndex(default_idx)
                    elif self.language_selector.count() > 0:
                        self.language_selector.setCurrentIndex(0)
            else:
                default_idx = self.language_selector.findText("Plain Text")
                if default_idx != -1:
                    self.language_selector.setCurrentIndex(default_idx)
                elif self.language_selector.count() > 0:
                    self.language_selector.setCurrentIndex(0)
        else:
            self.language_label.setText("Language: N/A")
            self.cursor_pos_label.setText("Ln 1, Col 1")
            default_idx = self.language_selector.findText("Plain Text")
            if default_idx != -1:
                self.language_selector.setCurrentIndex(default_idx)
            elif self.language_selector.count() > 0:
                self.language_selector.setCurrentIndex(0)

    @Slot()
    def on_text_editor_changed(self):
        current_editor = self._get_current_code_editor()
        if not current_editor:
            return

        current_index = self.tab_widget.indexOf(current_editor)
        if current_index == -1:
            return # Should not happen

        tab_data = self.tab_widget.tabData(current_index)
        # Ensure tab_data is a dictionary and has the expected keys
        if not isinstance(tab_data, dict):
            tab_data = {"path": None, "is_dirty": False}

        # Only mark as dirty if the change is not from network update
        if not self.is_updating_from_network:
            if not tab_data.get("is_dirty", False):
                tab_data["is_dirty"] = True
                self.tab_widget.setTabData(current_index, tab_data)
                # Add asterisk to tab title
                current_tab_text = self.tab_widget.tabText(current_index)
                if not current_tab_text.endswith("*"):
                    self.tab_widget.setTabText(current_index, current_tab_text + "*")
            
            # If in a collaborative session and we have control, send text updates
            if self.network_manager.is_connected() and self.has_control and not current_editor.isReadOnly():
                text = current_editor.toPlainText()
                self.network_manager.send_data('TEXT_UPDATE', text)

    @Slot(str)
    def on_network_data_received(self, data):
        print(f"8. Editor update slot called. Received data parameter: {data[:50]}...")
        current_editor = self._get_current_code_editor() # Use helper
        if current_editor:
            try:
                # The data parameter is already the content string, not the full JSON message.
                # No need to json.loads() here.
                content = data
                print(f"LOG: MainWindow.on_network_data_received - Parsed message in MainWindow: (content directly used)")
                self.is_updating_from_network = True
                current_cursor_pos = current_editor.textCursor().position()
                print(f"LOG: MainWindow.on_network_data_received - Setting text: {content[:50]}...")
                current_editor.setPlainText(content)
                cursor = current_editor.textCursor()
                cursor.setPosition(current_cursor_pos)
                current_editor.setTextCursor(cursor)
                self.is_updating_from_network = False
            except Exception as e:
                print(f"LOG: MainWindow.on_network_data_received - Error processing received data: {e}")
        print("LOG: MainWindow.on_network_data_received - Exit")

    @Slot()
    def on_peer_connected(self):
        self.status_bar.showMessage("Peer connected!")
        QMessageBox.information(self, "Connection Status", "Peer connected successfully!")
        self.start_host_action.setEnabled(False)
        self.connect_host_action.setEnabled(False)
        self.stop_session_action.setEnabled(True)
        self.update_ui_for_control_state() # Update UI after connection
        print(f"LOG: on_peer_connected - is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_peer_disconnected(self):
        self.status_bar.showMessage("Peer disconnected.")
        QMessageBox.warning(self, "Connection Status", "Peer disconnected.")
        self.start_host_action.setEnabled(True)
        self.connect_host_action.setEnabled(True)
        self.stop_session_action.setEnabled(False)
        self.is_host = False
        self.has_control = False
        self.update_ui_for_control_state() # Reset UI after disconnection
        print(f"LOG: on_peer_disconnected - is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def start_hosting_session(self):
        ip, port = ConnectionDialog.get_details(self)
        if ip and port:
            if self.network_manager.start_hosting(port):
                self.status_bar.showMessage(f"Hosting on port {port}...")
                self.start_host_action.setEnabled(False)
                self.connect_host_action.setEnabled(False)
                self.stop_session_action.setEnabled(True)
                self.is_host = True
                self.has_control = True # Host starts with control
                self.update_ui_for_control_state()
                print(f"LOG: start_hosting_session - is_host={self.is_host}, has_control={self.has_control}")
            else:
                QMessageBox.critical(self, "Error", "Failed to start hosting session.")

    @Slot()
    def connect_to_host_session(self):
        ip, port = ConnectionDialog.get_details(self)
        if ip and port:
            self.network_manager.connect_to_host(ip, port)
            self.status_bar.showMessage(f"Connecting to {ip}:{port}...")
            self.start_host_action.setEnabled(False)
            self.connect_host_action.setEnabled(False)
            self.stop_session_action.setEnabled(True)
            self.is_host = False
            self.has_control = False # Client starts without control
            self.update_ui_for_control_state()
            print(f"LOG: connect_to_host_session - is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def stop_current_session(self):
        self.network_manager.stop_session()
        self.status_bar.showMessage("Session stopped.")
        self.start_host_action.setEnabled(True)
        self.connect_host_action.setEnabled(True)
        self.stop_session_action.setEnabled(False)
        self.is_host = False
        self.has_control = False
        self.update_ui_for_control_state() # Reset UI after session stop
        print(f"LOG: stop_current_session - is_host={self.is_host}, has_control={self.has_control}")

    @Slot(int, int)
    def _update_cursor_position_label(self, line, column):
        self.cursor_pos_label.setText(f"Ln {line}, Col {column}")

    @Slot(str)
    def _update_language_label(self, language):
        self.language_label.setText(f"Language: {language}")

    def _get_current_code_editor(self):
        """Helper to get the current CodeEditor widget, or None if not a CodeEditor."""
        current_widget = self.tab_widget.currentWidget()
        if isinstance(current_widget, CodeEditor):
            return current_widget
        return None

    def update_editor_read_only_state(self):
        current_editor = self._get_current_code_editor()
        if current_editor:
            if self.network_manager.is_connected():
                # Editor is read-only if we don't have control in a session
                current_editor.setReadOnly(not self.has_control)
            else:
                # If not in a session, editor is always writable
                current_editor.setReadOnly(False)

    def update_ui_for_control_state(self):
        # Update status bar message
        if self.network_manager.is_connected():
            if self.is_host:
                if self.has_control:
                    self.control_status_label.setText("You have editing control.")
                else:
                    self.control_status_label.setText("Viewer has control. Press any key to reclaim.")
            else: # Client
                if self.has_control:
                    self.control_status_label.setText("You have editing control.")
                else:
                    self.control_status_label.setText("Viewing only. Click 'Request Control' to edit.")
        else:
            self.control_status_label.setText("Not in session")

        # Update "Request Control" button state
        if self.network_manager.is_connected() and not self.is_host:
            self.request_control_button.setEnabled(not self.has_control)
        else:
            self.request_control_button.setEnabled(False) # Only client can request control

        # Update editor read-only state
        self.update_editor_read_only_state()
        print(f"LOG: update_ui_for_control_state - is_host={self.is_host}, has_control={self.has_control}, editor_read_only={self._get_current_code_editor().isReadOnly() if self._get_current_code_editor() else 'N/A'}")

    @Slot()
    def request_control(self):
        if not self.is_host and not self.has_control and self.network_manager.is_connected():
            self.network_manager.send_data('REQ_CONTROL')
            self.status_bar.showMessage("Requesting control...")
            self.request_control_button.setEnabled(False) # Disable button after request
            print(f"LOG: request_control - is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_control_request_received(self):
        if self.is_host and self.has_control: # Host has control and client requests it
            reply = QMessageBox.question(self, "Control Request",
                                         "The client has requested editing control. Grant control?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.network_manager.send_data('GRANT_CONTROL')
                self.has_control = False
                self.update_ui_for_control_state()
                self.status_bar.showMessage("Control granted to client.")
            else:
                self.network_manager.send_data('DECLINE_CONTROL')
                self.status_bar.showMessage("Control request declined.")

    @Slot()
    def on_control_granted(self):
        if not self.is_host: # Only client receives this
            self.has_control = True
            self.update_ui_for_control_state()
            self.status_bar.showMessage("You have been granted editing control.")
            print(f"LOG: on_control_granted - is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_control_declined(self):
        if not self.is_host: # Only client receives this
            self.status_bar.showMessage("Host declined the request.", 3000) # Show for 3 seconds
            self.request_control_button.setEnabled(True) # Re-enable button

    @Slot()
    def on_control_revoked(self):
        if not self.is_host: # Only client receives this
            self.has_control = False
            self.update_ui_for_control_state()
            self.status_bar.showMessage("Editing control has been revoked.")
            print(f"LOG: on_control_revoked - is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_host_reclaim_control(self):
        if self.is_host and not self.has_control: # Host reclaims control
            self.has_control = True
            self.update_ui_for_control_state()
            self.network_manager.send_data('REVOKE_CONTROL')
            self.status_bar.showMessage("You have reclaimed editing control.")
            print(f"LOG: on_host_reclaim_control - is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def _ai_handle_get_current_code_request(self):
        """Handles requests from AITools to get the current code in the active editor."""
        current_editor = self._get_current_code_editor()
        if current_editor:
            code = current_editor.toPlainText()
            self.ai_get_current_code_result.emit(code)
            print("LOG: _ai_handle_get_current_code_request - Emitted current code.")
        else:
            self.ai_get_current_code_result.emit("") # Emit empty string if no editor
            print("LOG: _ai_handle_get_current_code_request - No active editor, emitted empty string.")

    def open_new_tab(self, file_path=None):
        editor = CodeEditor(self)
        tab_title = "Untitled"
        tab_data = {"path": None, "is_dirty": False} # Initialize tab state

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                editor.setPlainText(content)
                tab_title = os.path.basename(file_path) # Get filename
                editor.file_path = file_path # Store file path in editor widget
                tab_data["path"] = file_path # Set path for existing file
            except FileNotFoundError:
                QMessageBox.critical(self, "Error", f"File not found: '{file_path}'")
                editor.deleteLater() # Clean up the editor if file not found
                return
            except PermissionError:
                QMessageBox.critical(self, "Error", f"Permission denied to open: '{file_path}'")
                editor.deleteLater()
                return
            except UnicodeDecodeError:
                QMessageBox.critical(self, "Error", f"Could not open '{file_path}'. It might be a binary file or use an unsupported encoding.")
                editor.deleteLater()
                return
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An unexpected error occurred while opening '{file_path}': {e}")
                editor.deleteLater()
                return
        else:
            editor.file_path = None # For new untitled files

        index = self.tab_widget.addTab(editor, tab_title)
        self.tab_data_map[editor] = tab_data # Store tab state
        self.tab_widget.setCurrentIndex(index)
        self.tab_widget.setTabToolTip(index, file_path if file_path else "Untitled") # Set tooltip to full path

        # Connect signals from the new editor to update status bar
        editor.cursor_position_changed_signal.connect(self._update_cursor_position_label)
        editor.language_changed_signal.connect(self._update_language_label)
        editor.textChanged.connect(self.on_text_editor_changed) # Connect for network sync
        editor.control_reclaim_requested.connect(self.on_host_reclaim_control) # Connect new signal
        self._update_status_bar_and_language_selector_on_tab_change(index) # Update status bar immediately for new tab
        self.update_editor_read_only_state() # Apply initial read-only state

    @Slot(str)
    def _ai_handle_read_file_request(self, file_path):
        """Handles requests from AITools to read a file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.ai_read_file_result.emit(file_path, content)
            print(f"LOG: _ai_handle_read_file_request - Read file: {file_path}")
        except FileNotFoundError:
            self.ai_read_file_result.emit(file_path, f"Error: File not found at {file_path}")
            print(f"LOG: _ai_handle_read_file_request - File not found: {file_path}")
        except Exception as e:
            self.ai_read_file_result.emit(file_path, f"Error reading file {file_path}: {e}")
            print(f"LOG: _ai_handle_read_file_request - Error reading file {file_path}: {e}")

    @Slot(str, str)
    def _ai_handle_write_file_request(self, file_path, content):
        """Handles requests from AITools to write content to a file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.ai_write_file_result.emit(file_path, True, "File written successfully.")
            print(f"LOG: _ai_handle_write_file_request - Wrote to file: {file_path}")
        except Exception as e:
            self.ai_write_file_result.emit(file_path, False, f"Error writing to file {file_path}: {e}")
            print(f"LOG: _ai_handle_write_file_request - Error writing to file {file_path}: {e}")

    @Slot(str)
    def _ai_handle_list_directory_request(self, path):
        """Handles requests from AITools to list directory contents."""
        try:
            contents = []
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    contents.append({"name": item, "type": "directory"})
                else:
                    contents.append({"name": item, "type": "file"})
            self.ai_list_directory_result.emit(path, json.dumps(contents))
            print(f"LOG: _ai_handle_list_directory_request - Listed directory: {path}")
        except FileNotFoundError:
            self.ai_list_directory_result.emit(path, f"Error: Directory not found at {path}")
            print(f"LOG: _ai_handle_list_directory_request - Directory not found: {path}")
        except Exception as e:
            self.ai_list_directory_result.emit(path, f"Error listing directory {path}: {e}")
            print(f"LOG: _ai_handle_list_directory_request - Error listing directory {path}: {e}")

    def open_folder(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec():
            selected_directory = dialog.selectedFiles()[0]
            self.file_explorer.set_root_path(selected_directory)
            self.status_bar.showMessage(f"Opened folder: {selected_directory}")

    def close_tab(self, index):
        widget = self.tab_widget.widget(index)
        if widget is not None:
            widget.deleteLater()
        self.tab_widget.removeTab(index)

    def create_new_file(self):
        # 1. Context-Aware Path Detection
        selected_index = self.file_explorer.selectionModel().currentIndex()
        target_directory = None

        if selected_index.isValid():
            selected_path = self.file_explorer.model.filePath(selected_index)
            if os.path.isdir(selected_path):
                target_directory = selected_path
            else: # A file is selected
                target_directory = os.path.dirname(selected_path)
        else: # Nothing is selected, default to root path
            target_directory = self.file_explorer.model.rootPath()

        if not target_directory:
            QMessageBox.critical(self, "Error", "Could not determine target directory for new file.")
            return

        # 2. User Input for Filename
        file_name, ok = QInputDialog.getText(self, "New File", "Enter new file name:", QLineEdit.Normal, "")

        if not ok or not file_name:
            return # User cancelled or entered empty name

        full_path = os.path.join(target_directory, file_name)

        # 3. File Creation and Error Handling
        if os.path.exists(full_path):
            QMessageBox.warning(self, "File Exists", "A file or folder with this name already exists.")
            return

        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                pass # Create an empty file
            
            # 4. Post-Creation Workflow
            self.open_new_tab(full_path) # Open the new file in the editor
            self.status_bar.showMessage(f"Created new file: {full_path}", 3000)

        except OSError as e:
            QMessageBox.critical(self, "Error Creating File", f"Failed to create file '{file_name}': {e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")

    def close_tab(self, index=None):
        if index is None:
            index = self.tab_widget.currentIndex()
        if index != -1:
            current_editor = self.tab_widget.widget(index)
            if isinstance(current_editor, CodeEditor):
                current_editor.textChanged.disconnect(self.on_text_editor_changed)
                current_editor.control_reclaim_requested.disconnect(self.on_host_reclaim_control)
            current_editor.deleteLater()
            self.tab_widget.removeTab(index)

    def open_file(self):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        if file_dialog.exec():
            selected_file = file_dialog.selectedFiles()[0]
            self.open_new_tab(selected_file)

    def save_current_file(self):
        current_index = self.tab_widget.currentIndex()
        if current_index == -1:
            self.status_bar.showMessage("No active editor to save.")
            return False
        return self._save_file(current_index)

    def save_current_file_as(self):
        current_index = self.tab_widget.currentIndex()
        if current_index == -1:
            self.status_bar.showMessage("No active editor to save.")
            return False
        return self._save_file(current_index, save_as=True)

    def _save_file(self, index: int, save_as: bool = False) -> bool:
        print(f"LOG: _save_file - Entry for index {index}, save_as={save_as}")
        """
        Rewritten to be a robust, synchronous save operation.
        Returns True on success, False on failure or user cancellation.
        """
        editor = self.tab_widget.widget(index)
        if not isinstance(editor, CodeEditor):
            print(f"LOG: _save_file - Current widget is not a CodeEditor. Returning False.")
            return False

        tab_data = self.tab_widget.tabData(index)
        if tab_data is None:
            tab_data = {"path": None, "is_dirty": False}
            print(f"LOG: _save_file - tab_data was None, initialized to {tab_data}")

        file_path = tab_data.get("path")
        original_text = editor.toPlainText()
        formatted_text = original_text # Initialize with original text
        print(f"LOG: _save_file - Initial file_path: {file_path}")
        print(f"LOG: _save_file - Original text length: {len(original_text)}")

        # 1. Handle "Untitled" Files and "Save As"
        if file_path is None or save_as:
            suggested_filename = "Untitled.py" if file_path is None else os.path.basename(file_path)
            print(f"LOG: _save_file - Handling 'Save As' or untitled file. Suggested filename: {suggested_filename}")
            new_file_path, _ = QFileDialog.getSaveFileName(self, "Save File As", suggested_filename, "All Files (*);;Python Files (*.py)")
            if not new_file_path:
                self.status_bar.showMessage("Save operation cancelled.")
                print(f"LOG: _save_file - User cancelled Save As dialog. Returning False.")
                return False # User cancelled
            file_path = new_file_path
            # Update path in tab data immediately for subsequent steps
            tab_data["path"] = file_path
            self.tab_widget.setTabData(index, tab_data) # Ensure tab_data is updated
            editor.file_path = file_path # Update the editor's internal file_path
            print(f"LOG: _save_file - New file path selected: {file_path}")
            # Re-run highlighting and language detection for the new file type
            editor._update_language_and_highlighting()
            # Refresh file explorer to show new file
            self.file_explorer.refresh_tree()


        # If after "Save As" dialog, file_path is still None (e.g., user cancelled and it was an untitled file)
        if not file_path:
            QMessageBox.warning(self, "Save Error", "No file path specified for saving.")
            print(f"LOG: _save_file - No file path after dialog. Returning False.")
            return False

        # 2. Provide UI Feedback (Start)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage(f"Formatting and saving '{os.path.basename(file_path)}'...")
        print(f"LOG: _save_file - Starting save process for: {file_path}")

        try:
            # 3. Synchronous Formatting
            # Only attempt to format if it's a Python file, otherwise just use original text
            if file_path.lower().endswith(".py"):
                print(f"LOG: _save_file - Attempting to format Python file with Black.")
                try:
                    formatted_text = black.format_str(original_text, mode=black.FileMode())
                    print(f"LOG: _save_file - Black formatting successful. Formatted text length: {len(formatted_text)}")
                except black.parsing.LibCSTError as e:
                    QMessageBox.critical(self, "Formatting Error", f"Syntax error in code. Cannot format:\n{e}")
                    print(f"LOG: _save_file - Black formatting failed (LibCSTError): {e}. Returning False.")
                    return False
                except Exception as e:
                    QMessageBox.critical(self, "Formatting Error", f"Failed to format code with Black:\n{e}")
                    print(f"LOG: _save_file - Black formatting failed (General Error): {e}. Returning False.")
                    return False
            else:
                print(f"LOG: _save_file - Not a Python file, skipping Black formatting.")
            
            # 4. Synchronous Write to Disk
            print(f"LOG: _save_file - Creating directories if they don't exist for: {os.path.dirname(file_path)}")
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            print(f"LOG: _save_file - Opening file for writing: {file_path}")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(formatted_text)
            print(f"LOG: _save_file - File write successful.")

            # 5. Finalize UI State (On Success)
            self.is_updating_from_network = True # Prevent on_text_editor_changed from marking as dirty
            editor.setPlainText(formatted_text) # Update editor with formatted text
            self.is_updating_from_network = False # Reset flag
            tab_data["is_dirty"] = False
            self.tab_widget.setTabData(index, tab_data)
            
            # Update tab title (remove asterisk and set filename)
            new_tab_title = os.path.basename(file_path)
            self.tab_widget.setTabText(index, new_tab_title)
            self.tab_widget.setTabToolTip(index, file_path) # Update tooltip

            # 6. Provide UI Feedback (End)
            self.statusBar().showMessage(f"File saved successfully.", 3000)
            return True

        except PermissionError:
            QMessageBox.critical(self, "File Save Error", f"Permission denied: Could not write to '{file_path}'.")
            return False
        except IOError as e:
            QMessageBox.critical(self, "File Save Error", f"An I/O error occurred while saving '{file_path}':\n{e}")
            return False
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during save: {e}")
            return False
        finally:
            QApplication.restoreOverrideCursor() # Always restore cursor

    def format_current_code(self):
        current_editor = self._get_current_code_editor()
        if not current_editor:
            self.status_bar.showMessage("No active editor to format.")
            return

        current_index = self.tab_widget.indexOf(current_editor)
        if current_index == -1:
            return

        code_text = current_editor.toPlainText()
        file_path = self.tab_widget.tabData(current_index).get("path")

        # Only attempt to format if it's a Python file
        if file_path and file_path.lower().endswith(".py"):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.statusBar().showMessage("Formatting code...")
            try:
                formatted_text = black.format_str(code_text, mode=black.FileMode())
                current_editor.setPlainText(formatted_text)
                self.status_bar.showMessage("Code formatted.")
                
                # Mark as dirty if it wasn't already, as formatting is a change
                tab_data = self.tab_widget.tabData(current_index)
                if tab_data is None:
                    tab_data = {"path": None, "is_dirty": False}
                if not tab_data.get("is_dirty", False):
                    tab_data["is_dirty"] = True
                    self.tab_widget.setTabData(current_index, tab_data)
                    self.tab_widget.setTabText(current_index, self.tab_widget.tabText(current_index) + "*")

            except black.parsing.LibCSTError as e:
                self.status_bar.showMessage("Formatting failed: Syntax error.")
                QMessageBox.critical(self, "Formatting Error", f"Syntax error in code. Cannot format:\n{e}")
            except Exception as e:
                self.status_bar.showMessage("Formatting failed.")
                QMessageBox.critical(self, "Formatting Error", f"Failed to format code with Black:\n{e}")
            finally:
                QApplication.restoreOverrideCursor()
        else:
            self.status_bar.showMessage("Formatting is only supported for Python files (.py).")

    def run_code(self, mode="run"):
        current_editor = self._get_current_code_editor()
        if not current_editor:
            self.status_bar.showMessage("No active code editor to run.")
            return

        file_path = current_editor.file_path
        if not file_path:
            QMessageBox.warning(self, "Execution Error", "Please save the file before running or debugging.")
            self.status_bar.showMessage("Please save the file before running or debugging.")
            return

        file_extension = os.path.splitext(file_path)[1].lower()
        language_mode = self.language_selector.currentText() # Get selected language from QComboBox

        # Determine the command based on the selected language mode
        command_config = self.RUNNER_CONFIG.get(language_mode)
        
        if not command_config:
            # Fallback to extension-based lookup if language mode doesn't have a direct config
            # This handles cases where a language might not be explicitly in RUNNER_CONFIG but its extension is
            for lang, config in self.RUNNER_CONFIG.items():
                if file_extension in config.get("extensions", []):
                    command_config = config
                    break

        if not command_config:
            error_message = f"No runner is configured for '{file_extension}' files with the selected language '{language_mode}'. Please select a different language or save the file with the correct extension (e.g., '.py' for Python)."
            QMessageBox.warning(self, "Execution Error", error_message)
            self.status_bar.showMessage(error_message)
            return

        # Use the command from the determined config
        command = command_config.get("run_command") if mode == "run" else command_config.get("debug_command")
        if not command:
            error_message = f"No {mode} command configured for '{language_mode}'."
            QMessageBox.warning(self, "Execution Error", error_message)
            self.status_bar.showMessage(error_message)
            return

        # Replace placeholder with actual file path
        final_command = command.replace("{file_path}", f'"{file_path}"')

        self.terminal_widget.clear_output()
        self.status_bar.showMessage(f"Running: {final_command}")
        self.terminal_widget.execute_command(final_command, os.path.dirname(file_path))

    def run_code(self, mode="run"):
        current_editor = self._get_current_code_editor()
        if not current_editor:
            self.status_bar.showMessage("No active code editor to run.")
            return

        file_path = current_editor.file_path
        if not file_path:
            self.status_bar.showMessage(f"Please save the file before {mode}ging.")
            return

        file_extension = os.path.splitext(file_path)[1].lower() # Get file extension
        selected_mode = mode.lower() # 'run' or 'debug'
        selected_language = self.language_selector.currentText() # Get selected language for display in messages

        language_config = self.RUNNER_CONFIG.get(file_extension)
        if not language_config:
            QMessageBox.warning(self, "Execution Error",
                                f"No configuration found for file type: '{file_extension}'.")
            self.status_bar.showMessage(f"No runner configured for '{file_extension}'.")
            return

        command_template = language_config.get(selected_mode)
        if not command_template:
            QMessageBox.warning(self, "Execution Error",
                                f"No '{selected_mode}' command configured for language: '{selected_language}'.")
            self.status_bar.showMessage(f"No '{selected_mode}' command configured for '{selected_language}'.")
            return

        # Prepare the command
        substituted_command_parts = []
        class_name = os.path.splitext(os.path.basename(file_path))[0]
        output_file = os.path.splitext(file_path)[0]

        for part in command_template:
            if part == "{file}":
                substituted_command_parts.append(f'"{file_path}"') # Quote file path for spaces
            elif part == "{class_name}":
                substituted_command_parts.append(class_name)
            elif part == "{output_file}":
                substituted_command_parts.append(output_file)
            else:
                substituted_command_parts.append(part)

        # Handle "&&" for chained commands
        final_commands_sequence = []
        current_command_set = []
        for part in substituted_command_parts:
            if part == "&&":
                if current_command_set:
                    final_commands_sequence.append(current_command_set)
                current_command_set = []
            else:
                current_command_set.append(part)
        
        if current_command_set:
            final_commands_sequence.append(current_command_set)

        # Execute the command sequence
        self.terminal_widget.clear_output()
        self.status_bar.showMessage(f"{mode.capitalize()}ing {os.path.basename(file_path)} ({selected_language})...")
        
        # QProcess setup for output
        self.terminal_widget.run_command_sequence(final_commands_sequence, os.path.dirname(file_path), current_editor.current_language)

    @Slot()
    def handle_execution(self):
        selected_mode = self.language_selector.currentText().lower()
        if selected_mode == "run":
            self.run_code(mode="run")
        elif selected_mode == "debug":
            self.run_code(mode="debug") # Call run_code with debug mode

    def debug_code(self):
        """Legacy method preserved for compatibility - use run_code(mode='debug') instead"""
        pass

    def save_session(self):
        session_data = {}
        try:
            root_path = self.file_explorer.model().rootPath()
            open_files = []
            for i in range(self.tab_widget.count()):
                tab_data = self.tab_widget.tabData(i) # Get tab data
                if tab_data and "path" in tab_data and tab_data["path"]:
                    file_path = tab_data["path"]
                    # Only save actual files, ignore "Untitled" tabs that haven't been saved
                    if os.path.exists(file_path):
                        open_files.append(file_path)
            
            active_file_index = self.tab_widget.currentIndex()
            
            session_data = {
                "root_path": root_path,
                "open_files": open_files,
                "active_file_index": active_file_index
            }
            
            config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
            session_dir = os.path.join(config_dir, ".aether_editor")
            os.makedirs(session_dir, exist_ok=True)
            session_file = os.path.join(session_dir, "session.json")
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=4)
            print(f"LOG: Session saved to {session_file}")
        except Exception as e:
            print(f"LOG: save_session - Error saving session: {e}")

    def load_session(self):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        session_dir = os.path.join(config_dir, ".aether_editor")
        session_file = os.path.join(session_dir, "session.json")
        
        if os.path.exists(session_file):
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                
                root_path = session_data.get("root_path")
                open_files = session_data.get("open_files", [])
                active_file_index = session_data.get("active_file_index", 0)
                
                # Restore Folder
                if root_path and os.path.isdir(root_path):
                    self.file_explorer.set_root_path(root_path)
                
                # Close the initial empty tab if it's the only one
                # Check if the initial tab is "Untitled" and not dirty
                if self.tab_widget.count() == 1:
                    tab_data = self.tab_widget.tabData(0)
                    if tab_data and tab_data.get("path") is None and not tab_data.get("is_dirty", False):
                        self.close_tab(0)
                
                # Restore Files
                for file_path in open_files:
                    if os.path.exists(file_path):
                        self.open_new_tab(file_path)
                
                # Restore Active Tab
                if 0 <= active_file_index < self.tab_widget.count():
                    self.tab_widget.setCurrentIndex(active_file_index)
                elif self.tab_widget.count() > 0:
                    self.tab_widget.setCurrentIndex(0) # Fallback to first tab
                
                print(f"LOG: Session loaded from {session_file}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"LOG: load_session - Error loading session file: {e}")
                # Fallback to default state if file is corrupted or unreadable
                if self.tab_widget.count() == 0:
                    self.open_new_tab() # Ensure at least one tab is open
        else:
            print("LOG: load_session - No session file found, starting with default state.")
            if self.tab_widget.count() == 0:
                self.open_new_tab() # Ensure at least one tab is open

    def closeEvent(self, event):
        unsaved_changes_exist = False
        for i in range(self.tab_widget.count()):
            tab_data = self.tab_widget.tabData(i)
            if tab_data and tab_data.get("is_dirty", False):
                unsaved_changes_exist = True
                break

        if unsaved_changes_exist:
            reply = QMessageBox.question(self, "Unsaved Changes",
                                         "You have unsaved changes. Do you want to save them before closing?",
                                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                         QMessageBox.Save) # Default button

            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.Save:
                # Store current index to restore it later
                original_current_index = self.tab_widget.currentIndex()
                
                for i in range(self.tab_widget.count()):
                    tab_data = self.tab_widget.tabData(i)
                    if tab_data and tab_data.get("is_dirty", False):
                        # Temporarily set the current index to the tab to be saved
                        # This ensures _save_file operates on the correct tab
                        self.tab_widget.setCurrentIndex(i)
                        if not self._save_file(i): # If save is cancelled
                            event.ignore()
                            return # Stop processing and prevent close
                
                # Restore original current index if it's still valid
                if 0 <= original_current_index < self.tab_widget.count():
                    self.tab_widget.setCurrentIndex(original_current_index)
        
        # Only save the session and accept the close event if all saves were successful or discarded
        self.save_session()
        event.accept()

    @Slot(QPoint)
    def on_file_tree_context_menu(self, position):
        index = self.file_explorer.indexAt(position)
        if not index.isValid():
            return # No item clicked

        file_path = self.file_explorer.model.filePath(index)
        
        menu = QMenu(self)
        
        rename_action = QAction("Rename", self)
        rename_action.triggered.connect(lambda: self._rename_file_folder(index))
        menu.addAction(rename_action)

        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self._delete_file_folder(index))
        menu.addAction(delete_action)

        menu.exec(self.file_explorer.mapToGlobal(position))

    def _find_editor_for_path(self, file_path):
        """Helper to find an open CodeEditor tab for a given file path."""
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.widget(i)
            if isinstance(editor, CodeEditor) and editor.file_path == file_path:
                return editor, i
        return None, -1

    def _rename_file_folder(self, index):
        model = self.file_explorer.model()
        file_index = model.index(index.row(), 0, index.parent())
        old_path = model.filePath(file_index)
        
        if not old_path:
            self.status_bar.showMessage("Could not get path for selected item.")
            return

        is_dir = os.path.isdir(old_path)
        item_type = "folder" if is_dir else "file"
        
        new_name, ok = QInputDialog.getText(self, f"Rename {item_type}", f"Enter new name for {os.path.basename(old_path)}:",
                                            QLineEdit.Normal, os.path.basename(old_path))
        if ok and new_name:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            
            # If it's an open editor, update its tab data and tab title
            editor, tab_index = self._find_editor_for_path(old_path)
            if editor:
                tab_data = self.tab_widget.tabData(tab_index)
                if isinstance(tab_data, dict):
                    tab_data["path"] = new_path
                    self.tab_widget.setTabData(tab_index, tab_data)
                self.tab_widget.setTabText(tab_index, os.path.basename(new_path))
            
            try:
                os.rename(old_path, new_path)
                self.status_bar.showMessage(f"Renamed {item_type} to {new_name}")
                self.file_explorer.refresh_view() # Refresh the file explorer
            except Exception as e:
                self.status_bar.showMessage(f"Error renaming {item_type}: {e}")

    def _delete_file_folder(self, index):
        path_to_delete = self.file_explorer.model.filePath(index)
        name_to_delete = os.path.basename(path_to_delete)

        reply = QMessageBox.question(self, "Delete", f"Are you sure you want to delete '{name_to_delete}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                # Close any open tabs related to the deleted file/folder
                tabs_to_close = []
                for i in range(self.tab_widget.count()):
                    editor = self.tab_widget.widget(i)
                    if isinstance(editor, CodeEditor) and editor.file_path:
                        if os.path.isfile(path_to_delete) and editor.file_path == path_to_delete:
                            tabs_to_close.append(i)
                        elif os.path.isdir(path_to_delete) and editor.file_path.startswith(path_to_delete):
                            tabs_to_close.append(i)
                
                # Close tabs in reverse order to avoid index issues
                for i in sorted(tabs_to_close, reverse=True):
                    self.close_tab(i)

                if os.path.isdir(path_to_delete):
                    shutil.rmtree(path_to_delete)
                else:
                    os.remove(path_to_delete)
                self.status_bar.showMessage(f"Deleted '{name_to_delete}'")
            except (OSError, PermissionError) as e:
                QMessageBox.critical(self, "Delete Error", f"Permission denied or file in use: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Delete Error", f"An unexpected error occurred while deleting '{name_to_delete}': {e}")

    @Slot()
    def open_ai_assistant(self):
        """
        Opens the AI Assistant window.
        """
        self.ai_assistant_window = AIAssistantWindow(self) # Pass self (MainWindow instance)
        self.ai_assistant_window.show()

    @Slot(str)
    def apply_ai_code_edit(self, new_code):
        """
        Slot to receive code edits from the AI assistant and apply them to the current editor.
        """
        current_editor = self._get_current_code_editor()
        if current_editor:
            # Set the flag to prevent network echo
            current_editor._is_programmatic_change = True
            current_editor.setPlainText(new_code)
            current_editor._is_programmatic_change = False
            self.status_bar.showMessage("AI Assistant applied code changes.")
        else:
            self.status_bar.showMessage("AI Assistant tried to edit, but no active editor found.")

    @Slot()
    def handle_execution(self):
        """Unified handler for the Play button, dispatches based on selected mode."""
        selected_mode = self.language_selector.currentText().lower()
        self.run_code(mode=selected_mode)

    def debug_code(self):
        """Handles starting a debug session using pdb in the integrated terminal."""
        current_editor = self._get_current_code_editor()
        if not current_editor:
            self.status_bar.showMessage("No active code editor to debug.")
            return

        if not current_editor.file_path:
            self.status_bar.showMessage("Please save the file before debugging.")
            return

        file_path = current_editor.file_path
        
        # Switch to the integrated terminal tab
        self.tab_widget.setCurrentWidget(self.terminal_dock)
        self.terminal_widget.clear_output()
        self.status_bar.showMessage(f"Starting debug session for: {os.path.basename(file_path)}")
        
        # Command to run pdb
        debug_command = self.RUNNER_CONFIG[os.path.splitext(file_path)[1]].get("debug")
        if not debug_command:
            QMessageBox.information(self, "Debugging", "Debugging not configured for this file type.")
            self.status_bar.showMessage("Debugging not configured for this file type.")
            return

        # Substitute {file} placeholder
        final_debug_command = [part.replace("{file}", file_path) for part in debug_command]
        
        # Run the debug command in the terminal widget
        self.terminal_widget.start_interactive_process(final_debug_command, os.path.dirname(file_path))
    def set_run_mode(self, mode):
        """Sets the current run mode and updates the UI."""
        self.current_run_mode = mode
        self.update_run_debug_button_ui()
        self.status_bar.showMessage(f"Mode set to: {mode}")

    def update_run_debug_button_ui(self):
        """Updates the main Run/Debug button's icon and tooltip based on current mode."""
        if self.current_run_mode == "Run":
            self.run_debug_action_button.setIcon(QIcon.fromTheme("media-playback-start"))
            self.run_debug_action_button.setText("Run")
            self.run_debug_action_button.setToolTip("Run Code (F5)")
        elif self.current_run_mode == "Debug":
            self.run_debug_action_button.setIcon(QIcon.fromTheme("debug-alt"))
            self.run_debug_action_button.setText("Debug")
            self.run_debug_action_button.setToolTip("Debug Code")

    def debug_code(self):
        """Handles starting a debug session using pdb in the integrated terminal."""
        current_editor = self._get_current_code_editor()
        if not current_editor:
            self.status_bar.showMessage("No active code editor to debug.")
            return

        if not current_editor.file_path:
            self.status_bar.showMessage("Please save the file before debugging.")
            return

        file_path = current_editor.file_path
        
        # Switch to the integrated terminal tab
        self.tab_widget.setCurrentWidget(self.terminal_dock)
        self.terminal_widget.clear_output()
        self.status_bar.showMessage(f"Starting debug session for: {os.path.basename(file_path)}")
        
        # Command to run pdb
        debug_command = ["python", "-m", "pdb", file_path]
        
        # Run the debug command in the terminal widget
        # The terminal_widget needs a method to run a single command interactively
        self.terminal_widget.start_interactive_process(debug_command, os.path.dirname(file_path))
