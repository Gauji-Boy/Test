from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar, QDockWidget, QApplication, QWidget, QVBoxLayout, QMenuBar, QMenu, QFileDialog, QLabel, QToolBar, QInputDialog, QMessageBox, QLineEdit, QPushButton, QToolButton, QComboBox, QPlainTextEdit
from PySide6.QtGui import QAction, QIcon, QTextCharFormat, QColor, QTextCursor, QActionGroup, QFont
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QModelIndex, QThreadPool, QStandardPaths, QObject
from file_explorer import FileExplorer
from code_editor import CodeEditor
from interactive_terminal import InteractiveTerminal # Import the new interactive terminal
from network_manager import NetworkManager # Import NetworkManager
from connection_dialog import ConnectionDialog # Import ConnectionDialog
from ai_controller import AIController # Import AIController
import tempfile
import os
import sys
import shutil # For rmtree
import json # Import json for structured messages
import black # Import black for synchronous formatting

class MainWindow(QMainWindow):
    def __init__(self, initial_path=None):
        super().__init__()
        self.setWindowTitle("Aether Editor")
        self.setGeometry(100, 100, 1200, 800)

        self.threadpool = QThreadPool() # Initialize QThreadPool for background tasks
        print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")

        self.threadpool = QThreadPool() # Initialize QThreadPool for background tasks
        print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")

        self.is_updating_from_network = False # Flag to prevent echo loop

        self.network_manager = NetworkManager(self) # Initialize NetworkManager

        # State variables for collaborative editing
        self.is_host = False
        self.has_control = False # True if this instance has the editing token
        self.tab_data_map = {} # Map to store tab-specific data (e.g., file paths)
        self.recent_projects = [] # Initialize recent projects list

        self.current_run_mode = "Run" # Initial run mode
        self.setup_status_bar() # Initialize status bar labels first
        self.setup_toolbar() # Re-enable toolbar for the new button
        self.setup_ui()
        self.setup_menu()
        self.setup_network_connections() # Setup network signals and slots
        self.update_ui_for_control_state() # Initial UI update

        # Initialize active editor undo stack reference
        self._active_editor_undo_stack = None
        
        # Disable undo/redo actions initially (will be enabled by tab change if editor is valid)
        if hasattr(self, 'undo_action'): # Check if setup_menu has been called
            self.undo_action.setEnabled(False)
        if hasattr(self, 'redo_action'):
            self.redo_action.setEnabled(False)

        # Load session data at startup
        session_data = self.load_session()
        self.recent_projects = session_data.get("recent_projects", [])

        if initial_path:
            self.initialize_project(initial_path)
        elif session_data["root_path"]:
            self.initialize_project(session_data["root_path"], add_to_recents=False)
            for file_path in session_data["open_files"]:
                if os.path.exists(file_path):
                    self.open_new_tab(file_path)
            if 0 <= session_data["active_file_index"] < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(session_data["active_file_index"])
            elif self.tab_widget.count() > 0:
                self.tab_widget.setCurrentIndex(0)
        else:
            # Initial empty tab if no path is provided and no session to load
            # Check if this is part of a "join session" flow, which might not need an initial tab here
            # For now, let's assume open_new_tab() is okay, or initialize_project(None) handles it.
            # self.open_new_tab() # This will now correctly set initial tab data
            # If started with no initial_path and no session, it could be a join attempt or fresh start.
            # The welcome screen or direct "join session" action will handle this.
            # If neither, then perhaps an empty tab is desired.
            # For now, let's defer tab opening to specific actions like new file or join session.
            pass


    def initialize_project(self, path: str, add_to_recents: bool = True):
        """Initializes the project by setting the file explorer root and opening the terminal."""
        if path is None:
            # This is a client-only startup.
            # Open a single, empty "Untitled" tab.
            self.open_new_tab() # Use open_new_tab which handles None path
            # Hide the file explorer as there is no project context.
            if hasattr(self, 'file_explorer_dock'): # Check if file_explorer_dock exists
                self.file_explorer_dock.setVisible(False)
            return # Stop further processing

        import os
        if os.path.isdir(path):
            self.file_explorer.set_root_path(path)
            # Ensure file explorer is visible if it was hidden
            if hasattr(self, 'file_explorer_dock') and not self.file_explorer_dock.isVisible():
                self.file_explorer_dock.setVisible(True)
            # Ensure file explorer is visible
            if hasattr(self, 'file_explorer_dock') and not self.file_explorer_dock.isVisible():
                self.file_explorer_dock.setVisible(True)
            self.terminal_widget.start_shell(path)
            if add_to_recents:
                self.add_recent_project(path) # Add to recent projects
        elif os.path.isfile(path):
            parent_dir = os.path.dirname(path)
            if parent_dir:
                self.file_explorer.set_root_path(parent_dir)
                # Ensure file explorer is visible
                if hasattr(self, 'file_explorer_dock') and not self.file_explorer_dock.isVisible():
                    self.file_explorer_dock.setVisible(True)
                self.terminal_widget.start_shell(parent_dir)
                if add_to_recents:
                    self.add_recent_project(parent_dir) # Add parent directory to recent projects
            else:
                # If it's a file in the current working directory with no parent_dir
                current_dir = os.getcwd()
                self.file_explorer.set_root_path(current_dir)
                # Ensure file explorer is visible
                if hasattr(self, 'file_explorer_dock') and not self.file_explorer_dock.isVisible():
                    self.file_explorer_dock.setVisible(True)
                self.terminal_widget.start_shell(current_dir)
                if add_to_recents:
                    self.add_recent_project(current_dir) # Add current directory to recent projects
            self.open_new_tab(path) # Use open_new_tab which handles file opening
        else:
            print(f"Warning: Provided path is neither a file nor a directory: {path}")
            # Fallback to default behavior if path is invalid
            default_path = os.path.expanduser("~")
            self.file_explorer.set_root_path(default_path)
            # Ensure file explorer is visible
            if hasattr(self, 'file_explorer_dock') and not self.file_explorer_dock.isVisible():
                self.file_explorer_dock.setVisible(True)
            self.terminal_widget.start_shell(default_path)
            if add_to_recents:
                self.add_recent_project(default_path) # Add default path to recent projects
        
    def setup_ui(self):
        # Central Editor View (QTabWidget)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tab_widget)
        self.tab_widget.currentChanged.connect(self._update_status_bar_and_language_selector_on_tab_change)
        self.tab_widget.currentChanged.connect(self._update_undo_redo_actions) # Connect to update undo/redo actions

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
        self.terminal_dock = QDockWidget("Terminal", self) # Renamed dock title
        self.terminal_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        
        # Add the new InteractiveTerminal widget directly to the dock
        self.terminal_widget = InteractiveTerminal(self)
        self.terminal_dock.setWidget(self.terminal_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal_dock)

    def _open_file_in_new_tab(self, file_path):
        """Helper method to open a file in a new tab."""
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", f"The file '{file_path}' does not exist.")
            return

        # Check if the file is already open
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.widget(i)
            tab_data = self.tab_data_map.get(editor)
            if tab_data and tab_data.get("path") == file_path:
                self.tab_widget.setCurrentIndex(i)
                return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            editor = CodeEditor(self)
            editor.setPlainText(content)
            editor.textChanged.connect(self.on_text_editor_changed)
            editor.cursorPositionChanged.connect(lambda: self._update_cursor_position_label(
                editor.textCursor().blockNumber() + 1,
                editor.textCursor().columnNumber() + 1
            ))

            # Determine language based on file extension
            file_extension = os.path.splitext(file_path)[1].lower()
            language = self.EXTENSION_TO_LANGUAGE.get(file_extension, "Plain Text")
            editor.set_language(language)

            tab_name = os.path.basename(file_path)
            new_tab_index = self.tab_widget.addTab(editor, tab_name)
            self.tab_widget.setCurrentIndex(new_tab_index)

            # Store tab-specific data
            self.tab_data_map[editor] = {"path": file_path, "is_dirty": False}
            
            self.update_editor_read_only_state() # Apply read-only state if in session
            self.status_bar.showMessage(f"Opened {file_path}", 2000)
            self._update_undo_redo_actions() # Update undo/redo actions after opening a file

        except Exception as e:
            QMessageBox.critical(self, "Error Opening File", f"Could not open file {file_path}: {e}")

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


        # Recent Projects Submenu
        self.recent_projects_menu = file_menu.addMenu("Recent Projects")
        self._update_recent_menu() # Populate it initially

        # Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")

        # Undo/Redo Actions
        self.undo_action = QAction("&Undo", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self._undo_current_editor)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("&Redo", self)
        self.redo_action.setShortcut("Ctrl+Y")
        self.redo_action.triggered.connect(self._redo_current_editor)
        edit_menu.addAction(self.redo_action)
        
        edit_menu.addSeparator() # Separator for clarity

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

    def _update_recent_menu(self):
        self.recent_projects_menu.clear()
        if not self.recent_projects:
            placeholder_action = QAction("No Recent Projects", self)
            placeholder_action.setEnabled(False)
            self.recent_projects_menu.addAction(placeholder_action)
        else:
            for project_path in self.recent_projects:
                action = QAction(project_path, self)
                action.triggered.connect(lambda checked, path=project_path: self.initialize_project(path))
                self.recent_projects_menu.addAction(action)
            self.recent_projects_menu.addSeparator()
            clear_action = QAction("Clear Recent Projects", self)
            clear_action.triggered.connect(self._clear_recent_projects)
            self.recent_projects_menu.addAction(clear_action)


    def _handle_remove_recent_project(self, path_to_remove):
        if path_to_remove in self.recent_projects:
            self.recent_projects.remove(path_to_remove)
            self._update_recent_menu()
            if hasattr(self, 'welcome_page') and self.welcome_page:
                self.welcome_page.update_list(self.recent_projects)
            self.save_session() # Save the updated session

    def _handle_rename_recent_project(self, old_path):
        new_path, ok = QInputDialog.getText(self, "Rename Recent Project",
                                            f"Enter new path for '{old_path}':",
                                            QLineEdit.Normal, old_path)
        if ok and new_path:
            if new_path != old_path:
                try:
                    # Attempt to rename the actual folder/file if it exists
                    if os.path.exists(old_path):
                        os.rename(old_path, new_path)
                        QMessageBox.information(self, "Rename Successful", f"Renamed '{old_path}' to '{new_path}'.")
                    else:
                        QMessageBox.warning(self, "Path Not Found", f"Original path '{old_path}' does not exist. Updating list only.")

                    # Update in recent projects list
                    if old_path in self.recent_projects:
                        index = self.recent_projects.index(old_path)
                        self.recent_projects[index] = new_path
                        self._update_recent_menu()
                        self.save_session() # Save the updated session
                except OSError as e:
                    QMessageBox.critical(self, "Rename Error", f"Could not rename: {e}")
            else:
                QMessageBox.information(self, "No Change", "New path is the same as the old path. No action taken.")

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

        # New Test Runner Button for diagnostic purposes
        self.test_runner_button = QPushButton("Test Runner", self)
        self.test_runner_button.clicked.connect(self._run_diagnostic_test)
        toolbar.addWidget(self.test_runner_button)

        # AI Assistant Button
        self.ai_assistant_button = QPushButton("AI Assistant", self)
        # Optionally, set an icon if available:
        # self.ai_assistant_button.setIcon(QIcon.fromTheme("accessories-text-editor"))
        self.ai_assistant_button.clicked.connect(self.open_new_ai_assistant)
        toolbar.addWidget(self.ai_assistant_button)

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
        # Disconnect from previous editor's undo stack signals if any
        # Disconnect from previous editor's document signals if any
        if hasattr(self, '_active_editor_document') and self._active_editor_document:
            try:
                self._active_editor_document.undoAvailable.disconnect(self.undo_action.setEnabled)
            except RuntimeError: # Signal was not connected or object deleted
                pass
            try:
                self._active_editor_document.redoAvailable.disconnect(self.redo_action.setEnabled)
            except RuntimeError: # Signal was not connected or object deleted
                pass
            self._active_editor_document = None # Clear the reference

        editor = self.tab_widget.widget(index)
        if isinstance(editor, CodeEditor):
            self._active_editor_document = editor.document()

            self._active_editor_document.undoAvailable.connect(self.undo_action.setEnabled)
            self._active_editor_document.redoAvailable.connect(self.redo_action.setEnabled)
            
            # Immediately update state
            self.undo_action.setEnabled(self._active_editor_document.isUndoAvailable())
            self.redo_action.setEnabled(self._active_editor_document.isRedoAvailable())
            self.redo_action.setEnabled(editor.document().isRedoAvailable())

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
            # Not a CodeEditor tab, or no editor
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)
            self._active_editor_undo_stack = None # Ensure it's cleared

            self.language_label.setText("Language: N/A")
            self.cursor_pos_label.setText("Ln 1, Col 1")
            default_idx = self.language_selector.findText("Plain Text")
            if default_idx != -1:
                self.language_selector.setCurrentIndex(default_idx)
            elif self.language_selector.count() > 0:
                self.language_selector.setCurrentIndex(0)

    @Slot()
    def join_session_from_welcome_page(self):
        """Public slot to initiate joining a session from the welcome page."""
        self.connect_to_host_session()
        # After attempting to connect, initialize_project(None) will set up the client-only UI
        self.initialize_project(None)

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
        
        # Enable/disable undo/redo actions based on editor's state
        self._update_undo_redo_actions()

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
                self._update_undo_redo_actions() # Update after network change
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

        self.statusBar().showMessage(f"Executing '{os.path.basename(file_path)}'...")
        
        output_file_no_ext = os.path.splitext(file_path)[0]
        
        # Construct the final command string
        final_command_str = " ".join(command_template).replace("{file}", f'"{file_path}"').replace("{output_file}", f'"{output_file_no_ext}"')
        
        # Pass the command to the interactive terminal using the new method
        self.terminal_widget.run_code_command(final_command_str)
        
        self.terminal_dock.show()
        self.terminal_dock.raise_()

    @Slot()
    def _run_diagnostic_test(self):
        print("--- DEBUG: Starting diagnostic test ---")
        
        # The simplest possible command. This checks if python is in the PATH.
        executable = "python"
        arguments = ["--version"] # A command that prints to stdout and exits.
        
        print(f"DEBUG: Hardcoded command: {executable} {' '.join(arguments)}")
        
        # Pass the command to the interactive terminal
        self.terminal_widget.run_code_command(f"{executable} {' '.join(arguments)}")
        
        self.terminal_dock.show()
        self.terminal_dock.raise_()

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
        self._update_undo_redo_actions() # Update undo/redo actions for new tab

    def open_folder(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec():
            selected_directory = dialog.selectedFiles()[0]
            self.file_explorer.set_root_path(selected_directory)
            self.setWindowTitle(f"Aether Editor - {os.path.basename(selected_directory)}")
            self.terminal_widget.start_shell(selected_directory) # Start shell in new directory
            self.add_recent_project(selected_directory) # Add to recent projects
            self.save_session() # Save session after opening folder

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

    # This version of close_tab is removed as the one above is more complete
    # and already incorporates the self.tab_data_map logic.

    def open_file(self):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        if file_dialog.exec():
            selected_file = file_dialog.selectedFiles()[0]
            self.initialize_project(selected_file) # Initialize project with the selected file
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
            original_text = current_editor.toPlainText() # Store original text before formatting
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


    def save_session(self):
        session_data = {}
        try:
            root_path = self.file_explorer.model.rootPath() # Get root path from QFileSystemModel
            open_files = []
            for i in range(self.tab_widget.count()):
                editor = self.tab_widget.widget(i)
                if isinstance(editor, CodeEditor):
                    tab_data = self.tab_data_map.get(editor) # Get tab data from map
                    if tab_data and tab_data.get("path") and os.path.exists(tab_data.get("path")):
                        open_files.append(tab_data.get("path"))
            
            active_file_index = self.tab_widget.currentIndex()
            
            session_data = {
                "root_path": root_path,
                "open_files": open_files,
                "active_file_index": active_file_index,
                "recent_projects": self.recent_projects # Save recent projects
            }
            
            config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
            session_dir = os.path.join(config_dir, ".aether_editor")
            os.makedirs(session_dir, exist_ok=True)
            session_file = os.path.join(session_dir, "session.json")
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=4)
            print(f"LOG: Session saved to {session_file}. Content: {session_data}")
        except Exception as e:
            print(f"LOG: save_session - Error saving session: {e}")

    def load_session(self):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        session_dir = os.path.join(config_dir, ".aether_editor")
        session_file = os.path.join(session_dir, "session.json")
        
        session_data = {"root_path": None, "open_files": [], "active_file_index": 0, "recent_projects": []} # Default empty session

        if os.path.exists(session_file):
            try:
                with open(session_file, 'r') as f:
                    loaded_data = json.load(f)
                    session_data["root_path"] = loaded_data.get("root_path")
                    session_data["open_files"] = loaded_data.get("open_files", [])
                    session_data["active_file_index"] = loaded_data.get("active_file_index", 0)
                    session_data["recent_projects"] = loaded_data.get("recent_projects", [])
                print(f"LOG: Session loaded from {session_file}. Content: {session_data}")
            except Exception as e:
                print(f"LOG: load_session - Error loading session: {e}")
        return session_data

    def add_recent_project(self, path: str):
        if path not in self.recent_projects:
            self.recent_projects.insert(0, path) # Add to the beginning
            self.recent_projects = self.recent_projects[:10] # Keep only the last 10
            self._update_recent_menu()
            self.save_session() # Persist changes
        else:
            # If the path is already in recent_projects, move it to the front
            self.recent_projects.remove(path)
            self.recent_projects.insert(0, path)
            self._update_recent_menu()
            self.save_session() # Save updated recent projects

    def _show_welcome_page(self):
        from welcome_screen import WelcomeScreen # Import here to avoid circular dependency
        # Close existing welcome tab if open
        for i in range(self.tab_widget.count()):
            if isinstance(self.tab_widget.widget(i), WelcomeScreen):
                self.tab_widget.removeTab(i)
                break

        self.welcome_page = WelcomeScreen(recent_projects=self.recent_projects)
        self.welcome_page.path_selected.connect(self.initialize_project)
        self.welcome_page.recent_projects_changed.connect(self._update_recent_projects_from_welcome)
        self.welcome_page.clear_recents_requested.connect(self._perform_clear_recent_projects_logic)
        self.welcome_page.rename_recent_requested.connect(self._rename_recent_project)
        self.welcome_page.remove_recent_requested.connect(self._remove_recent_project)

        index = self.tab_widget.addTab(self.welcome_page, "Welcome")
        self.tab_widget.setCurrentIndex(index)
        self.tab_widget.setTabEnabled(index, False) # Make welcome tab non-closable
        self.tab_widget.setTabButton(index, QTabWidget.RightSide, None) # Remove close button

    @Slot(list)
    def _update_recent_projects_from_welcome(self, updated_list):
        self.recent_projects = updated_list
        self._update_recent_menu()
        self.save_session()

    @Slot()
    def _clear_recent_projects(self):
        # Step 1: Display the confirmation dialog
        reply = QMessageBox.question(self,
                                     "Confirm Clear",
                                     "Are you sure you want to clear all recent projects?",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)

        # Step 2: Act based on the user's response
        if reply == QMessageBox.Yes:
            # This is where the existing clearing logic goes:
            self.recent_projects.clear()
            self._update_recent_menu()
            if hasattr(self, 'welcome_page') and self.welcome_page:
                self.welcome_page.update_list(self.recent_projects)
            self.statusBar().showMessage("Recent projects list cleared.", 3000)
            self.save_session() # Save the updated session
        else:
            # If user clicks "No" or closes the dialog, do nothing.
            self.statusBar().showMessage("Clear operation cancelled.", 3000)

    @Slot(str)
    def _rename_recent_project(self, old_path: str):
        new_path = QFileDialog.getExistingDirectory(self, "Select New Folder for Project")
        if new_path and new_path != old_path:
            if old_path in self.recent_projects:
                self.recent_projects.remove(old_path)
            if new_path not in self.recent_projects:
                self.recent_projects.insert(0, new_path) # Add to the beginning
                self.recent_projects = self.recent_projects[:10] # Keep only the last 10
                self._update_recent_menu()
                self.save_session()
                if hasattr(self, 'welcome_page') and self.welcome_page:
                    self.welcome_page.update_list(self.recent_projects)

    @Slot(str)
    def _remove_recent_project(self, path_to_remove: str):
        if QMessageBox.question(self, "Remove Recent Project",
                                f"Are you sure you want to remove '{os.path.basename(path_to_remove)}' from the list?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            if path_to_remove in self.recent_projects:
                self.recent_projects.remove(path_to_remove)
                self._update_recent_menu()
                self.save_session()
                if hasattr(self, 'welcome_page') and self.welcome_page:
                    self.welcome_page.update_list(self.recent_projects)

    def closeEvent(self, event):
        self.save_session() # Save session on close
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

    def open_new_ai_assistant(self):
        # Store the controller instance as a member of MainWindow
        # to keep it alive as long as the AI window is open.
        # If the AI window is modal, this might not be strictly necessary,
        # but it's safer if the window can be non-modal.
        # For simplicity, let's create a new one each time,
        # assuming the AI window/controller handles its own lifecycle once shown.
        # If issues arise with premature GC, we can revisit storing it as self.ai_controller.
        ai_controller = AIController(main_window=self)
        ai_controller.show_window()
        # To prevent the AIController instance from being garbage collected immediately
        # if show_window() is non-blocking and the AI window is not modal,
        # we might need to store it. A simple way for now if the window is a dialog:
        self._current_ai_controller = ai_controller

    def _undo_current_editor(self):
        current_editor = self._get_current_code_editor()
        if current_editor and current_editor.document().isUndoAvailable():
            current_editor.undo()
            # self._update_undo_redo_actions() # REMOVED - signal from QUndoStack handles this

    def _redo_current_editor(self):
        current_editor = self._get_current_code_editor()
        if current_editor and current_editor.document().isRedoAvailable():
            current_editor.redo()
            # self._update_undo_redo_actions() # REMOVED - signal from QUndoStack handles this

    def _update_undo_redo_actions(self):
        # This method is kept for manual refresh if needed by other parts of the UI,
        # e.g., after a programmatic change that might not reliably trigger document signals,
        # or when a tab is opened/closed.
        # The primary update mechanism for undo/redo actions during typing/editing
        # is now the direct connection to QUndoStack signals in 
        # _update_status_bar_and_language_selector_on_tab_change.
        current_editor = self._get_current_code_editor()
        if current_editor:
            # Ensure undo_action and redo_action exist before trying to setEnabled
            if hasattr(self, 'undo_action'):
                self.undo_action.setEnabled(current_editor.document().isUndoAvailable())
            if hasattr(self, 'redo_action'):
                self.redo_action.setEnabled(current_editor.document().isRedoAvailable())
        else:
            if hasattr(self, 'undo_action'):
                self.undo_action.setEnabled(False)
            if hasattr(self, 'redo_action'):
                self.redo_action.setEnabled(False)