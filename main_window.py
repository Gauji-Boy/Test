from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar, QDockWidget, QApplication, QWidget, QVBoxLayout, QMenuBar, QMenu, QFileDialog, QLabel, QToolBar, QInputDialog, QMessageBox, QLineEdit, QPushButton, QToolButton, QComboBox, QPlainTextEdit, QTabBar
from PySide6.QtGui import QAction, QIcon, QTextCharFormat, QColor, QTextCursor, QActionGroup, QFont
from PySide6.QtCore import Qt, QProcess, Signal, Slot, QPoint, QModelIndex, QThreadPool, QStandardPaths, QObject
from welcome_page import WelcomePage
from file_explorer import FileExplorer
from code_editor import CodeEditor
from interactive_terminal import InteractiveTerminal # Import the new interactive terminal
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
        self.load_session() # Re-added: MainWindow handles its own session.

    def _show_welcome_page(self):
        # Check if an initial "Untitled" tab exists and should be closed.
        if self.tab_widget.count() == 1:
            editor_widget = self.tab_widget.widget(0)
            # Check if it's a CodeEditor instance before accessing tab_data_map specific to editors
            if isinstance(editor_widget, CodeEditor): 
                tab_data = self.tab_data_map.get(editor_widget, {})
                if tab_data.get("path") is None and not tab_data.get("is_dirty", False):
                    print("LOG: Closing initial untitled/clean tab before showing welcome page.")
                    self.close_tab(0) 
            # If it's not a CodeEditor, it might be an already open Welcome Page, close it too if it's the only tab.
            elif isinstance(editor_widget, WelcomePage):
                 print("LOG: Closing existing Welcome Page before showing a new one.")
                 self.close_tab(0)


        welcome_page_widget = WelcomePage(self) 

        # Add WelcomePage as a new tab
        index = self.tab_widget.addTab(welcome_page_widget, "Welcome")
        self.tab_widget.setCurrentIndex(index)

        # Make the Welcome Page tab non-closable
        tab_bar = self.tab_widget.tabBar()
        tab_bar.setTabButton(index, QTabBar.RightSide, None) 

        # Connect signals from WelcomePage to MainWindow methods
        welcome_page_widget.new_file_requested.connect(self.create_new_file)
        welcome_page_widget.open_file_requested.connect(self.open_file)
        welcome_page_widget.open_folder_requested.connect(self.open_folder)
        
        print("LOG: Welcome page shown.")

    # initialize_project method removed

    def _get_session_file_path(self):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        app_specific_config_dir = os.path.join(config_dir, "AetherEditor")
        os.makedirs(app_specific_config_dir, exist_ok=True)
        return os.path.join(app_specific_config_dir, "session.json")

    def save_session(self):
        session_file = self._get_session_file_path()
        root_path = ""
        if self.file_explorer.model(): # Ensure model exists
            root_path = self.file_explorer.model().rootPath()
        
        open_files = []
        for i in range(self.tab_widget.count()):
            editor_widget = self.tab_widget.widget(i)
            if isinstance(editor_widget, CodeEditor): 
                # Do not save the Welcome Page tab if it's identified by a specific title
                if self.tab_widget.tabText(i) == "Welcome": # Assuming "Welcome" is the title of the welcome tab
                    continue
                tab_data = self.tab_data_map.get(editor_widget)
                if tab_data and tab_data.get("path") and os.path.exists(tab_data.get("path")):
                    open_files.append(tab_data.get("path"))

        active_file_index = self.tab_widget.currentIndex()
        # TODO: Adjust active_file_index if Welcome page was before it and is not saved.
        # This is a simplification for now. A more robust way would be to map saved indices.

        session_data = {
            "root_path": root_path,
            "open_files": open_files,
            "active_file_index": active_file_index 
        }

        try:
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=4) 
            print(f"LOG: Session saved to {session_file}")
        except IOError as e:
            print(f"LOG: save_session - Error writing session file {session_file}: {e}")
        except Exception as e:
            print(f"LOG: save_session - Unexpected error saving session: {e}")
            
    def load_session(self):
        session_file = self._get_session_file_path()
        if not os.path.exists(session_file):
            print("LOG: load_session - No session file found, showing welcome page.")
            self._show_welcome_page() # Show welcome page if no session
            return

        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"LOG: load_session - Error reading or parsing session file {session_file}: {e}")
            self._show_welcome_page() # Show welcome page on error
            return

        root_path = session_data.get("root_path")
        open_files_paths = session_data.get("open_files", [])
        active_file_index = session_data.get("active_file_index", 0)

        if root_path and os.path.isdir(root_path):
            self.file_explorer.set_root_path(root_path)
            self.terminal_widget.start_shell(root_path) # Also start terminal in this dir

        # Close the initial "Untitled" tab from setup_ui if there are files to open or a valid root_path
        if (open_files_paths or (root_path and os.path.isdir(root_path))) and self.tab_widget.count() == 1:
            initial_editor_widget = self.tab_widget.widget(0)
            if isinstance(initial_editor_widget, CodeEditor): # Check it's an editor
                initial_tab_data = self.tab_data_map.get(initial_editor_widget, {})
                if initial_tab_data.get("path") is None and not initial_tab_data.get("is_dirty", False):
                    # Also check if it's the welcome page, though welcome page shouldn't be an editor
                    if self.tab_widget.tabText(0) != "Welcome":
                         self.close_tab(0)
            elif self.tab_widget.tabText(0) == "Welcome": # If it's the welcome page itself
                self.close_tab(0)


        for file_path in open_files_paths:
            if os.path.exists(file_path):
                self.open_new_tab(file_path)
            else:
                print(f"LOG: load_session - File path from session does not exist: {file_path}")
        
        if not open_files_paths and not (root_path and os.path.isdir(root_path)):
            # No valid files or root path from session, show welcome page
            self._show_welcome_page()
        elif self.tab_widget.count() == 0 : # If all files failed to load or open_files was empty but root_path was set
             self._show_welcome_page() # Show welcome if no tabs ended up opening


        # Adjust active_file_index if the welcome page was potentially closed
        # This needs careful handling if the welcome page was among the tabs before this logic.
        # For simplicity, we rely on the fact that open_new_tab sets the current index.
        # The 'active_file_index' from session might be less reliable if "Welcome" tab was involved.
        # A safer approach: if tabs were opened, the last one is active. Otherwise, if count > 0, 0 is active.
        if self.tab_widget.count() > 0 :
            final_active_index = active_file_index
            # Validate active_file_index against current number of tabs
            # (excluding welcome page which isn't saved in open_files)
            if not (0 <= final_active_index < self.tab_widget.count()):
                final_active_index = self.tab_widget.count() -1 # Fallback to last opened tab
            if final_active_index >=0 :
                 self.tab_widget.setCurrentIndex(final_active_index)

        print(f"LOG: Session loaded from {session_file}")


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
        self.terminal_dock = QDockWidget("Output", self)
        self.terminal_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        
        # Create a QTabWidget for the bottom dock
        self.bottom_tab_widget = QTabWidget()
        self.terminal_dock.setWidget(self.bottom_tab_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal_dock)


        # Tab 2: Interactive Terminal
        self.terminal_widget = InteractiveTerminal(self)
        self.bottom_tab_widget.addTab(self.terminal_widget, "Terminal")
        
        # Connect the interactive terminal's command_entered signal
        # self.terminal_widget.line_entered.connect(self._on_terminal_input) # Removed: New terminal handles input

        # Initial empty tab is no longer opened here. load_session() will handle it.
        # self.open_new_tab() 
        
        # Start shell in home directory on startup
        self.terminal_widget.start_shell(QStandardPaths.writableLocation(QStandardPaths.HomeLocation))


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

        # Play Button (QAction)
        self.run_debug_action_button = QAction(QIcon.fromTheme("media-playback-start"), "Run Code", self) # Tooltip updated
        self.run_debug_action_button.setToolTip("Run Code (F5)")
        self.run_debug_action_button.setShortcut("F5")
        self.run_debug_action_button.triggered.connect(self._handle_run_request) # Connect to new handler
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

        # New Test Runner Button for diagnostic purposes
        self.test_runner_button = QPushButton("Test Runner", self)
        self.test_runner_button.clicked.connect(self._run_diagnostic_test)
        toolbar.addWidget(self.test_runner_button)

        # Add a permanent widget to the status bar for role/control status
        self.control_status_label = QLabel("Not in session")
        self.status_bar.addPermanentWidget(self.control_status_label)
        
        # Initial update of the run/debug button

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
        "Python": ["python", "-u", "{file}"],
        "C++": ["g++", "{file}", "-o", "{output_file}", "&&", "{output_file}"],
        "JavaScript": ["node", "{file}"]
    }

    def _update_status_bar_and_language_selector_on_tab_change(self, index):
        editor = self.tab_widget.widget(index)
        if isinstance(editor, CodeEditor):
            # Update status bar labels
            self.language_label.setText(f"Language: {editor.current_language}")
            self._update_cursor_position_label(editor.textCursor().blockNumber() + 1, editor.textCursor().columnNumber() + 1)
            
            # Auto-select language in QComboBox
            # Get tab data from self.tab_data_map
            tab_data = self.tab_data_map.get(editor, {}) # Provide default if editor not in map yet
            file_path = tab_data.get("path") # No 'if tab_data else None' needed due to default

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

        current_index = self.tab_widget.indexOf(current_editor) # Keep for tab title update
        if current_index == -1:
            return # Should not happen

        # Get tab_data from the map
        tab_data = self.tab_data_map.get(current_editor)
        
        if not isinstance(tab_data, dict):
            # Fallback if tab_data is not found or not a dict (should be rare after open_new_tab changes)
            tab_data = {"path": getattr(current_editor, 'file_path', None), "is_dirty": False}
            self.tab_data_map[current_editor] = tab_data # Ensure it's in the map
            # print(f"WARNING: on_text_editor_changed - tab_data was None or not a dict, re-initialized.")

        # Only mark as dirty if the change is not from network update
        if not self.is_updating_from_network:
            if not tab_data.get("is_dirty", False):
                tab_data["is_dirty"] = True # Update the dict in the map by reference
                # No self.tab_widget.setTabData call needed here.
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

    # New _handle_run_request method
    @Slot()
    def _handle_run_request(self):
        editor = self._get_current_code_editor()
        if not editor:
            self.statusBar().showMessage("No active editor to run.", 3000)
            return

        if not self.save_current_file(): # save_current_file calls _save_file
            self.statusBar().showMessage("Save operation cancelled or failed. Run aborted.", 3000)
            return

        file_path = editor.file_path
        if not file_path:
            QMessageBox.warning(self, "Execution Error", "File path not available after save attempt. Cannot execute.")
            self.statusBar().showMessage("File path error. Run aborted.", 3000)
            return

        _, extension = os.path.splitext(file_path)
        language_name = self.EXTENSION_TO_LANGUAGE.get(extension.lower())
        if not language_name:
            QMessageBox.warning(self, "Execution Error", f"No language is configured for file type '{extension}'.")
            return

        command_template = self.RUNNER_CONFIG.get(language_name) # This is now a list
        if not command_template:
            QMessageBox.warning(self, "Execution Error", f"No 'run' command is configured for the language '{language_name}'.")
            return

        # Clear both output panels
        self.terminal_widget.clear_all()
        self.statusBar().showMessage(f"Executing '{os.path.basename(file_path)}'...")
        
        output_file_no_ext = os.path.splitext(file_path)[0]

        executable = command_template[0]
        arguments = [part.replace("{file}", file_path).replace("{output_file}", output_file_no_ext) for part in command_template[1:]]

        working_directory = os.path.dirname(file_path)

        # Construct the command string
        # Ensure file_path and output_file_no_ext are quoted if they contain spaces
        quoted_file_path = f'"{file_path}"'
        quoted_output_file_no_ext = f'"{output_file_no_ext}"'

        # Replace placeholders in the command template parts
        command_parts = [
            part.replace("{file}", quoted_file_path)
                .replace("{output_file}", quoted_output_file_no_ext)
            for part in command_template
        ]
        
        # Join parts into a single command string
        # For C++, the command might be "g++ {file} -o {output_file} && {output_file}"
        # We need to handle this by potentially splitting if "&&" is present,
        # or just joining if it's a simple command like "python -u {file}".
        # For now, let's assume simple joining for commands that don't need chaining in this way
        # or that the shell itself will handle the '&&' if present in the list.
        final_command_str = " ".join(command_parts)

        # If working_directory is different from where the shell is currently, cd into it first
        # This is a simplified approach. A more robust solution might involve checking current shell dir.
        # For now, we assume the shell started by start_shell is in a known state or CWD is managed by user.
        # current_shell_dir = self.terminal_widget.get_current_working_directory() # Assuming such a method exists
        # if working_directory != current_shell_dir:
        #    final_command_str = f"cd \"{working_directory}\" && {final_command_str}"
        # else:
        #    final_command_str = f"cd \"{working_directory}\" && {final_command_str}"
        # For simplicity, always prepend cd for now, as run_code_command will execute it in the current shell context.
        
        # Prepend cd to the command to ensure it runs in the correct directory
        final_command_str = f"cd \"{working_directory}\" && {final_command_str}"

        print(f"DEBUG: Sending command to terminal: {final_command_str}")
        self.terminal_widget.run_code_command(final_command_str)

        self.bottom_tab_widget.setCurrentWidget(self.terminal_widget) # Switch to interactive terminal
        self.terminal_dock.show()
        self.terminal_dock.raise_()

    @Slot()
    def _run_diagnostic_test(self):
        print("--- DEBUG: Starting diagnostic test ---")
        
        self.terminal_widget.clear_all()
        # self.terminal_widget.append_output("--- Starting Diagnostic Test ---\n") # append_output removed

        command = "python --version"
        print(f"DEBUG: Hardcoded command for diagnostic: {command}")
        # self.terminal_widget.append_output(f"> {command}\n") # append_output removed

        self.terminal_widget.run_code_command(command)
        self.bottom_tab_widget.setCurrentWidget(self.terminal_widget) # Switch to interactive terminal

    # Removed _on_terminal_input as InteractiveTerminal now handles its input.
    # Removed _on_process_output, _on_process_error_output, _on_process_finished, _on_process_error
    # as QProcess is no longer managed by MainWindow directly for terminal operations.

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
        # self.tab_data_map[editor] = tab_data # Store tab state - MOVED, ALREADY PRESENT
        self.tab_widget.setCurrentIndex(index)
        self.tab_widget.setTabToolTip(index, file_path if file_path else "Untitled") # Set tooltip to full path
        self.tab_data_map[editor] = tab_data # Store tab_data in the map

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
        self._close_welcome_page_if_open()
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec():
            selected_directory = dialog.selectedFiles()[0]
            self.file_explorer.set_root_path(selected_directory)
            self.status_bar.showMessage(f"Opened folder: {selected_directory}")
            # Start shell in the newly opened folder
            self.terminal_widget.start_shell(selected_directory)


    def close_tab(self, index=None): # Made index optional as per later definition
        if index is None:
            index_to_close = self.tab_widget.currentIndex()
        else:
            index_to_close = index
        
        if index_to_close == -1:
            return

        widget = self.tab_widget.widget(index_to_close)
        if widget is not None:
            # Disconnect signals first
            if isinstance(widget, CodeEditor):
                try:
                    widget.textChanged.disconnect(self.on_text_editor_changed)
                    widget.control_reclaim_requested.disconnect(self.on_host_reclaim_control)
                    # Attempt to disconnect other signals if they were connected
                    widget.cursor_position_changed_signal.disconnect(self._update_cursor_position_label)
                    widget.language_changed_signal.disconnect(self._update_language_label)
                except RuntimeError: # Signal already disconnected
                    pass 
            
            # Remove from tab_data_map
            if widget in self.tab_data_map:
                del self.tab_data_map[widget]
            
            widget.deleteLater()
        
        self.tab_widget.removeTab(index_to_close)

    # Removed create_new_file_action_triggered, open_file_action_triggered, open_folder_action_triggered
    # as their logic is now incorporated into the main action methods.

    def _close_welcome_page_if_open(self):
        for i in range(self.tab_widget.count()):
            widget_at_i = self.tab_widget.widget(i) # Get the widget
            # Check tab title and optionally widget type for robustness
            if self.tab_widget.tabText(i) == "Welcome" and isinstance(widget_at_i, WelcomePage):
                self.close_tab(i)
                print("LOG: Welcome page closed by _close_welcome_page_if_open.")
                return # Assuming only one welcome page can be open

    def create_new_file(self):
        self._close_welcome_page_if_open()
        # 1. Context-Aware Path Detection
        # If file explorer is empty (no root path), default to a known writable location
        target_directory_default = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        
        current_explorer_root = self.file_explorer.model().rootPath() if self.file_explorer.model() and self.file_explorer.model().rootPath() else None

        target_directory = None
        selected_index = self.file_explorer.selectionModel().currentIndex()

        if selected_index.isValid():
            selected_path = self.file_explorer.model().filePath(selected_index) # Use model()
            if os.path.isdir(selected_path):
                target_directory = selected_path
            else: 
                target_directory = os.path.dirname(selected_path)
        elif current_explorer_root: # Nothing selected, but explorer has a root
             target_directory = current_explorer_root
        else: # Nothing selected and no root in explorer
            target_directory = target_directory_default


        if not target_directory: # Should always have a target_directory by now due to default
             QMessageBox.critical(self, "Error", "Could not determine target directory for new file. Using Documents.")
             target_directory = target_directory_default # Fallback just in case

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

    # This version of close_tab is removed as the one above is more complete
    # and already incorporates the self.tab_data_map logic.

    def open_file(self):
        self._close_welcome_page_if_open()
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
        # 1. Get Current State
        editor = self.tab_widget.widget(index)
        if not isinstance(editor, CodeEditor):
            print("DEBUG: _save_file - editor is not CodeEditor instance")
            return False

        # Retrieve tab_data using self.tab_data_map.get(editor)
        tab_data = self.tab_data_map.get(editor)
        if tab_data is None:
            # Fallback: Initialize tab_data if it's missing. This is a recovery mechanism.
            current_path_from_editor = getattr(editor, 'file_path', None)
            tab_data = {"path": current_path_from_editor, "is_dirty": True} # Assume dirty
            self.tab_data_map[editor] = tab_data # Add to map
            # print(f"WARNING: _save_file - tab_data was None for editor, initialized to: {tab_data}")

        current_path = tab_data.get("path")
        # editor_file_path = getattr(editor, 'file_path', None) # For fallback logic if needed

        # Fallback logic for current_path if tab_data had None, but editor knew its path (and not save_as)
        if current_path is None and editor.file_path is not None and not save_as:
             current_path = editor.file_path
             tab_data["path"] = current_path # Synchronize tab_data into our map's dictionary

        # 2. Handle "Untitled" Files / "Save As"
        if current_path is None or save_as:
            suggested_dir = os.path.dirname(current_path) if current_path and os.path.dirname(current_path) else QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            if save_as or current_path is None: 
                suggested_filename_base = "Untitled.py"
            else: 
                suggested_filename_base = os.path.basename(current_path)
            
            full_suggested_path = os.path.join(suggested_dir, suggested_filename_base)

            new_path, _ = QFileDialog.getSaveFileName(
                self, "Save File As", full_suggested_path,
                "All Files (*);;Python Files (*.py);;C++ Files (*.cpp *.cxx *.h *.hpp);;Text Files (*.txt)"
            )

            if not new_path:
                self.statusBar().showMessage("Save operation cancelled.", 3000)
                return False
            
            current_path = new_path
            tab_data["path"] = current_path # This updates the dictionary in self.tab_data_map
            editor.file_path = current_path # Keep editor's own file_path in sync
            # No self.tab_widget.setTabData needed as self.tab_data_map[editor] = tab_data is done if it was None,
            # or tab_data is a reference to the dict in the map.
            editor._update_language_and_highlighting()
            if hasattr(self, 'file_explorer') and self.file_explorer:
                self.file_explorer.refresh_tree()

        if not current_path:
             QMessageBox.critical(self, "Save Error", "No file path determined for saving.")
             self.statusBar().showMessage("Save error: No file path.", 5000)
             return False

        # 3. Provide Clear User Feedback (Start of Operation)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage(f"Formatting and saving '{os.path.basename(current_path)}'...")

        # 4. Perform Synchronous Formatting (for Python files)
        original_text = editor.toPlainText()
        formatted_text = original_text

        if current_path.lower().endswith(".py"):
            try:
                formatted_text = black.format_str(original_text, mode=black.FileMode())
            except black.parsing.LibCSTError as e:
                QMessageBox.critical(self, "Formatting Error", f"Syntax error in Python code. Cannot format and save:\n{e}")
                QApplication.restoreOverrideCursor()
                self.statusBar().showMessage("Formatting error. File not saved.", 5000)
                return False
            except Exception as e:
                QMessageBox.critical(self, "Formatting Error", f"Failed to format Python code with Black. File not saved:\n{e}")
                QApplication.restoreOverrideCursor()
                self.statusBar().showMessage("Formatting error. File not saved.", 5000)
                return False
        
        # 5. Perform Synchronous Write to Disk
        try:
            dir_name = os.path.dirname(current_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(current_path, 'w', encoding='utf-8') as f:
                f.write(formatted_text)
        except (IOError, PermissionError) as e:
            QMessageBox.critical(self, "File Save Error", f"Could not write to disk: '{current_path}'.\nError: {e}")
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage("File write error. File not saved.", 5000)
            return False
        except Exception as e:
            QMessageBox.critical(self, "File Save Error", f"An unexpected error occurred while writing to '{current_path}'.\nError: {e}")
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage("Unexpected write error. File not saved.", 5000)
            return False

        # 6. Finalize State on Success
        self.is_updating_from_network = True
        current_cursor_pos = editor.textCursor().position()
        editor.setPlainText(formatted_text)
        new_cursor = editor.textCursor()
        new_cursor.setPosition(min(current_cursor_pos, len(formatted_text)))
        editor.setTextCursor(new_cursor)
        self.is_updating_from_network = False
        
        tab_data["is_dirty"] = False # This updates the dictionary in self.tab_data_map
        # tab_data["path"] = current_path # Path is already updated in tab_data
        # self.tab_data_map[editor] = tab_data # This ensures the map has the latest state.
                                            # If tab_data is a reference to the dict in the map,
                                            # this explicit assignment might be redundant but safe.
        
        new_tab_title = os.path.basename(current_path)
        self.tab_widget.setTabText(index, new_tab_title)
        self.tab_widget.setTabToolTip(index, current_path) # Set full path as tooltip
        
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"File '{new_tab_title}' saved successfully.", 3000)
        
        return True

    def format_current_code(self):
        current_editor = self._get_current_code_editor()
        if not current_editor:
            self.status_bar.showMessage("No active editor to format.")
            return

        current_index = self.tab_widget.indexOf(current_editor)
        if current_index == -1:
            return

        code_text = current_editor.toPlainText()
        # Get tab_data from the map
        tab_data = self.tab_data_map.get(current_editor)
        file_path = tab_data.get("path") if tab_data else None

        # Only attempt to format if it's a Python file
        if file_path and file_path.lower().endswith(".py"):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.statusBar().showMessage("Formatting code...")
            try:
                formatted_text = black.format_str(code_text, mode=black.FileMode())
                current_editor.setPlainText(formatted_text) # This will trigger on_text_editor_changed
                self.status_bar.showMessage("Code formatted.")
                
                # Mark as dirty in self.tab_data_map if formatting changed the text
                # on_text_editor_changed will handle the asterisk if it's a new change
                if tab_data: # Ensure tab_data was found
                    if original_text != formatted_text and not tab_data.get("is_dirty", False):
                        tab_data["is_dirty"] = True
                        # Update tab title with asterisk if not already there
                        # This part is tricky as on_text_editor_changed also does this.
                        # To avoid double-asterisk or complex logic, let on_text_editor_changed handle it.
                        # We just ensure the dirty flag is set in our map.
                        # current_tab_text = self.tab_widget.tabText(current_index)
                        # if not current_tab_text.endswith("*"):
                        #    self.tab_widget.setTabText(current_index, current_tab_text + "*")
                
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


    def closeEvent(self, event):
        # Session saving is no longer handled by MainWindow directly.
        # AppController might handle it, or it's removed from the current scope.
        unsaved_changes_exist = False
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.widget(i)
            if isinstance(editor, CodeEditor):
                tab_data = self.tab_data_map.get(editor)
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
                    editor = self.tab_widget.widget(i) # Get editor for the tab
                    if isinstance(editor, CodeEditor):
                        tab_data = self.tab_data_map.get(editor) # Get its data from the map
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
        self.save_session() # Re-added
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
        model = self.file_explorer.model
        # file_index = model.index(index.row(), 0, index.parent()) # This seems to be Qt specific for tree models
        # old_path = model.filePath(file_index)
        old_path = model.filePath(index) # Simpler, index should be the direct item index
        
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
            editor, tab_idx = self._find_editor_for_path(old_path) # Renamed tab_index to tab_idx
            if editor:
                tab_data_for_editor = self.tab_data_map.get(editor) # Get from map
                if tab_data_for_editor: # Check if found in map
                    tab_data_for_editor["path"] = new_path
                    # tab_data_for_editor["is_dirty"] could be set if needed, e.g. if rename dirties.
                # Update editor's internal file_path as well
                editor.file_path = new_path
                self.tab_widget.setTabText(tab_idx, os.path.basename(new_path))
                self.tab_widget.setTabToolTip(tab_idx, new_path) # Update tooltip as well
            
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


