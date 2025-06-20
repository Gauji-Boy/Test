from PySide6.QtWidgets import (QMainWindow, QTabWidget, QStatusBar, QDockWidget, QApplication, QWidget,
                               QVBoxLayout, QMenuBar, QMenu, QFileDialog, QLabel, QToolBar,
                               QInputDialog, QMessageBox, QLineEdit, QPushButton, QToolButton,
                               QComboBox, QPlainTextEdit, QStyle, QTreeWidget, QTreeWidgetItem,
                               QListWidget, QListWidgetItem)
from PySide6.QtGui import (QAction, QIcon, QTextCharFormat, QColor, QTextCursor, QActionGroup,
                           QFont, QCloseEvent, QPaintEvent, QMouseEvent, QTextDocument) # Added QCloseEvent, QTextDocument
from PySide6.QtCore import (Qt, Signal, Slot, QPoint, QModelIndex, QThreadPool, QStandardPaths,
                            QObject, QProcess, QTextStream, QSize) # Added QSize
from file_explorer import FileExplorer
from code_editor import CodeEditor # Assuming CodeEditor has _InternalCodeEditor
from debug_manager import DebugManager
from interactive_terminal import InteractiveTerminal
from command_output_viewer import CommandOutputViewer
from network_manager import NetworkManager, NetworkMessageType
from connection_dialog import ConnectionDialog
from ai_controller import AIController
from file_manager import FileManager
from session_manager import SessionManager
from process_manager import ProcessManager

from editor_file_coordinator import EditorFileCoordinator
from user_session_coordinator import UserSessionCoordinator
from collaboration_service import CollaborationService
from execution_coordinator import ExecutionCoordinator
from config_manager import ConfigManager
from config import (DEFAULT_EXTENSION_TO_LANGUAGE_MAP, DEFAULT_MAIN_WINDOW_TITLE,
                    DEFAULT_MAIN_WINDOW_GEOMETRY, DEFAULT_LANGUAGE_SELECTOR_ITEMS) # Added

from typing import Optional, Any, Dict, List, Set # Added Dict, List, Set, Any
import logging
import tempfile
import os
# import sys # Not used
import shutil
import json
import black

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    # Coordinator instances (injected)
    editor_file_coordinator: EditorFileCoordinator
    user_session_coordinator: UserSessionCoordinator
    collaboration_service: CollaborationService
    execution_coordinator: ExecutionCoordinator

    # UI Elements
    tab_widget: QTabWidget
    status_bar: QStatusBar
    file_explorer: FileExplorer
    terminal_widget: InteractiveTerminal
    command_output_viewer: CommandOutputViewer
    control_status_label: QLabel
    recent_projects_menu: QMenu
    language_selector: QComboBox
    run_action_button: QAction
    debug_action_button: QAction
    request_control_button: QPushButton
    ai_assistant_button: QPushButton
    cursor_pos_label: QLabel
    language_label: QLabel
    git_branch_label: QLabel
    debugger_toolbar: QToolBar
    continue_action: QAction
    step_over_action: QAction
    step_into_action: QAction
    step_out_action: QAction
    stop_action: QAction
    left_tab_widget: QTabWidget
    left_dock_widget: QDockWidget
    terminal_dock: QDockWidget
    bottom_dock_tab_widget: QTabWidget
    variables_panel: QTreeWidget
    call_stack_panel: QListWidget
    breakpoints_panel: QListWidget
    debugger_main_widget: QWidget
    undo_action: QAction
    redo_action: QAction
    welcome_page: Optional[QWidget] # WelcomeScreen type, but QWidget for generality

    # Internal State
    threadpool: QThreadPool
    network_manager: NetworkManager
    file_manager: FileManager
    session_manager: SessionManager
    process_manager: ProcessManager
    debug_manager: DebugManager
    editor_to_path: Dict[QWidget, str]
    path_to_editor: Dict[str, CodeEditor]
    extension_to_language_map_config: Dict[str, str]
    active_breakpoints: Dict[str, Set[int]]
    current_run_mode: str

    _active_editor_document: Optional[QTextDocument]
    pending_initial_path: Optional[str]
    _current_ai_controller: Optional[AIController] # To keep AIController alive


    def __init__(self,
                 editor_file_coordinator: EditorFileCoordinator,
                 user_session_coordinator: UserSessionCoordinator,
                 collaboration_service: CollaborationService,
                 execution_coordinator: ExecutionCoordinator,
                 initial_path: Optional[str] = None) -> None:
        super().__init__()

        config_mgr = ConfigManager() # Moved up to be available for title/geometry

        # Load and set window title
        title = config_mgr.load_setting('main_window_title', DEFAULT_MAIN_WINDOW_TITLE)
        self.setWindowTitle(title)

        # Load and set window geometry
        geom = config_mgr.load_setting('main_window_geometry', DEFAULT_MAIN_WINDOW_GEOMETRY)
        if isinstance(geom, list) and len(geom) == 4 and all(isinstance(x, int) for x in geom):
            self.setGeometry(*geom)
        else:
            logger.warning(f"Loaded main_window_geometry '{geom}' is invalid. Using default.")
            self.setGeometry(*DEFAULT_MAIN_WINDOW_GEOMETRY)

        self.editor_file_coordinator = editor_file_coordinator
        self.user_session_coordinator = user_session_coordinator
        self.collaboration_service = collaboration_service
        self.execution_coordinator = execution_coordinator

        self.threadpool = QThreadPool()
        logger.info(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")

        self.network_manager = NetworkManager(self)
        self.file_manager = FileManager(self)
        self.session_manager = SessionManager(self)
        self.process_manager = ProcessManager(self)
        self.debug_manager = DebugManager(self)
        self.editor_to_path = {}
        self.path_to_editor = {}

        # config_mgr = ConfigManager() # Moved up
        self.extension_to_language_map_config = config_mgr.load_setting('extension_to_language_map', DEFAULT_EXTENSION_TO_LANGUAGE_MAP)
        if self.extension_to_language_map_config is DEFAULT_EXTENSION_TO_LANGUAGE_MAP:
            logger.info("Using default EXTENSION_TO_LANGUAGE_MAP as it was not found in settings.")
        else:
            logger.info("Loaded EXTENSION_TO_LANGUAGE_MAP from settings.")

        self.active_breakpoints = {}
        self.current_run_mode = "Run"

        self.setup_status_bar()
        self.setup_toolbar()
        self.command_output_viewer = CommandOutputViewer(self)

        self.debug_manager.session_started.connect(self.execution_coordinator._on_debug_session_started)
        self.debug_manager.session_stopped.connect(self.execution_coordinator._on_debug_session_stopped)
        self.debug_manager.paused.connect(self.execution_coordinator._on_debugger_paused)
        self.debug_manager.resumed.connect(self.execution_coordinator._on_debugger_resumed)
        self.setup_debugger_toolbar()

        self.setup_ui()
        self.setup_menu()
        self.setup_network_connections()

        self.file_manager.file_opened.connect(self.editor_file_coordinator._handle_file_opened)
        self.file_manager.file_open_error.connect(self.editor_file_coordinator._handle_file_open_error)
        self.file_manager.dirty_status_changed.connect(self._handle_dirty_status_changed)
        self.file_manager.file_saved.connect(self.editor_file_coordinator._handle_file_saved)
        self.file_manager.file_save_error.connect(self.editor_file_coordinator._handle_file_save_error)

        self.session_manager.session_loaded.connect(self.user_session_coordinator._handle_session_loaded)
        self.session_manager.session_saved.connect(self.user_session_coordinator._handle_session_saved_confirmation)
        self.session_manager.session_error.connect(self.user_session_coordinator._handle_session_error)

        self.process_manager.output_received.connect(self.execution_coordinator._handle_process_output)
        self.process_manager.process_started.connect(self.execution_coordinator._handle_process_started)
        self.process_manager.process_finished.connect(self.execution_coordinator._handle_process_finished)
        self.process_manager.process_error.connect(self.execution_coordinator._handle_process_error)

        self.update_ui_for_control_state()
        self._active_editor_document = None
        
        if hasattr(self, 'undo_action'):
            self.undo_action.setEnabled(False)
        if hasattr(self, 'redo_action'):
            self.redo_action.setEnabled(False)

        self.pending_initial_path = initial_path
        self.session_manager.load_session()
        self.welcome_page = None
        self._current_ai_controller = None


    def setup_debugger_toolbar(self) -> None:
        self.debugger_toolbar = QToolBar("Debugger Toolbar", self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.debugger_toolbar)

        self.continue_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Continue (F5)", self)
        self.continue_action.setShortcut("F5")
        self.continue_action.triggered.connect(lambda: self.debug_manager.continue_execution())
        self.continue_action.setEnabled(False)
        self.debugger_toolbar.addAction(self.continue_action)

        self.step_over_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward), "Step Over (F10)", self)
        self.step_over_action.setShortcut("F10")
        self.step_over_action.triggered.connect(lambda: self.debug_manager.step_over())
        self.step_over_action.setEnabled(False)
        self.debugger_toolbar.addAction(self.step_over_action)

        self.step_into_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward), "Step Into (F11)", self)
        self.step_into_action.setShortcut("F11")
        self.step_into_action.triggered.connect(lambda: self.debug_manager.step_into())
        self.step_into_action.setEnabled(False)
        self.debugger_toolbar.addAction(self.step_into_action)

        self.step_out_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward), "Step Out (Shift+F11)", self)
        self.step_out_action.setShortcut("Shift+F11")
        self.step_out_action.triggered.connect(lambda: self.debug_manager.step_out())
        self.step_out_action.setEnabled(False)
        self.debugger_toolbar.addAction(self.step_out_action)

        self.stop_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop), "Stop (Shift+F5)", self)
        self.stop_action.setShortcut("Shift+F5")
        self.stop_action.triggered.connect(self.debug_manager.stop_session)
        self.stop_action.setEnabled(False)
        self.debugger_toolbar.addAction(self.stop_action)

        self.debugger_toolbar.setVisible(False)

    def initialize_project(self, path: str, add_to_recents: bool = True) -> None:
        if path is None:
            self.editor_file_coordinator.open_new_tab()
            if hasattr(self, 'left_dock_widget'):
                self.left_dock_widget.setVisible(False)
            return

        if os.path.isdir(path):
            self.file_explorer.set_root_path(path)
            if hasattr(self, 'left_dock_widget') and not self.left_dock_widget.isVisible():
                self.left_dock_widget.setVisible(True)
            self.terminal_widget.start_shell(path)
            if add_to_recents:
                logger.info(f"About to add project to recents: {path}")
                self.user_session_coordinator.add_recent_project(path)
        elif os.path.isfile(path):
            parent_dir: str = os.path.dirname(path)
            if parent_dir:
                self.file_explorer.set_root_path(parent_dir)
                if hasattr(self, 'left_dock_widget') and not self.left_dock_widget.isVisible():
                    self.left_dock_widget.setVisible(True)
                self.terminal_widget.start_shell(parent_dir)
                if add_to_recents:
                    logger.info(f"About to add project to recents: {parent_dir}")
                    self.user_session_coordinator.add_recent_project(parent_dir)
            else:
                current_dir: str = os.getcwd()
                self.file_explorer.set_root_path(current_dir)
                if hasattr(self, 'left_dock_widget') and not self.left_dock_widget.isVisible():
                    self.left_dock_widget.setVisible(True)
                self.terminal_widget.start_shell(current_dir)
                if add_to_recents:
                    logger.info(f"About to add project to recents: {current_dir}")
                    self.user_session_coordinator.add_recent_project(current_dir)
            self.editor_file_coordinator.open_new_tab(path)
        else:
            logger.warning(f"Provided path is neither a file nor a directory: {path}")
            default_path: str = os.path.expanduser("~")
            self.file_explorer.set_root_path(default_path)
            if hasattr(self, 'left_dock_widget') and not self.left_dock_widget.isVisible():
                self.left_dock_widget.setVisible(True)
            self.terminal_widget.start_shell(default_path)
            if add_to_recents:
                logger.info(f"About to add project to recents: {default_path}")
                self.user_session_coordinator.add_recent_project(default_path)
        
    def setup_ui(self) -> None:
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.editor_file_coordinator.close_tab)
        self.setCentralWidget(self.tab_widget)
        self.tab_widget.currentChanged.connect(self._update_status_bar_and_language_selector_on_tab_change)
        self.tab_widget.currentChanged.connect(self._update_undo_redo_actions)

        debugger_main_widget = QWidget()
        debugger_layout = QVBoxLayout(debugger_main_widget)
        self.variables_panel = QTreeWidget()
        self.variables_panel.setHeaderLabels(["Variable", "Value", "Type"])
        locals_item = QTreeWidgetItem(self.variables_panel, ["Locals"])
        self.variables_panel.addTopLevelItem(locals_item)
        debugger_layout.addWidget(self.variables_panel)
        self.call_stack_panel = QListWidget()
        self.call_stack_panel.addItem(QListWidgetItem("main.py:10 - <module>"))
        debugger_layout.addWidget(self.call_stack_panel)
        self.breakpoints_panel = QListWidget()
        debugger_layout.addWidget(self.breakpoints_panel)
        self.debugger_main_widget = debugger_main_widget

        self.file_explorer = FileExplorer()
        self.file_explorer.file_opened.connect(self.editor_file_coordinator.open_new_tab)
        self.file_explorer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_explorer.customContextMenuRequested.connect(self.on_file_tree_context_menu)

        self.left_tab_widget = QTabWidget()
        self.left_tab_widget.addTab(self.file_explorer, "File Explorer")
        self.left_tab_widget.addTab(self.debugger_main_widget, "Debugger")
        self.left_dock_widget = QDockWidget("Explorer/Debugger", self)
        self.left_dock_widget.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.left_dock_widget.setWidget(self.left_tab_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock_widget)

        self.terminal_dock = QDockWidget("Terminal", self)
        self.terminal_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self.terminal_widget = InteractiveTerminal(self)
        self.bottom_dock_tab_widget = QTabWidget()
        self.bottom_dock_tab_widget.addTab(self.terminal_widget, "Shell")
        self.bottom_dock_tab_widget.addTab(self.command_output_viewer, "Output")
        self.terminal_dock.setWidget(self.bottom_dock_tab_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.terminal_dock)

    def setup_menu(self) -> None:
        menu_bar: QMenuBar = self.menuBar()
        file_menu: QMenu = menu_bar.addMenu("&File")
        new_file_action = QAction("&New File", self); new_file_action.setShortcut("Ctrl+N")
        new_file_action.triggered.connect(self.editor_file_coordinator.create_new_file); file_menu.addAction(new_file_action)
        save_file_action = QAction("&Save", self); save_file_action.setShortcut("Ctrl+S")
        save_file_action.triggered.connect(self.editor_file_coordinator.save_current_file); file_menu.addAction(save_file_action)
        save_file_as_action = QAction("Save &As...", self); save_file_as_action.setShortcut("Ctrl+Shift+S")
        save_file_as_action.triggered.connect(self.editor_file_coordinator.save_current_file_as); file_menu.addAction(save_file_as_action)
        open_file_action = QAction("&Open File...", self); open_file_action.setShortcut("Ctrl+Shift+O")
        open_file_action.triggered.connect(self.editor_file_coordinator.open_file); file_menu.addAction(open_file_action)
        open_folder_action = QAction("&Open Folder...", self) # Remains in MainWindow
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
        self.start_host_action = QAction("Start &Hosting Session", self); self.start_host_action.setShortcut("Ctrl+H")
        self.start_host_action.triggered.connect(self.collaboration_service.start_hosting_session) # Connect to service
        session_menu.addAction(self.start_host_action)
        self.connect_host_action = QAction("&Connect to Host...", self); self.connect_host_action.setShortcut("Ctrl+J")
        self.connect_host_action.triggered.connect(self.collaboration_service.connect_to_host_session) # Connect to service
        session_menu.addAction(self.connect_host_action)
        self.stop_session_action = QAction("&Stop Current Session", self); self.stop_session_action.setShortcut("Ctrl+T")
        self.stop_session_action.triggered.connect(self.collaboration_service.stop_current_session) # Connect to service
        session_menu.addAction(self.stop_session_action)

    def _update_recent_menu(self):
        self.recent_projects_menu.clear()
        # Use user_session_coordinator's recent_projects list
        if not self.user_session_coordinator.recent_projects:
            placeholder = QAction("No Recent Projects", self); placeholder.setEnabled(False)
            self.recent_projects_menu.addAction(placeholder)
        else:
            for path in self.user_session_coordinator.recent_projects: # Iterate coordinator's list
                action = QAction(path, self)
                action.triggered.connect(lambda checked, p=path: self.initialize_project(p))
                self.recent_projects_menu.addAction(action)
            self.recent_projects_menu.addSeparator()
            clear_action = QAction("Clear Recent Projects", self)
            clear_action.triggered.connect(self._clear_recent_projects_menu_action) # Connect to MainWindow's dialog method
            self.recent_projects_menu.addAction(clear_action)

    # _handle_remove_recent_project, _handle_rename_recent_project, _update_recent_projects_from_welcome
    # are removed from MainWindow. Their logic is in UserSessionCoordinator.
    # WelcomeScreen signals connect to UserSessionCoordinator slots via AppController.
    # The menu action for clearing recents (_clear_recent_projects) is now _clear_recent_projects_menu_action.

    def _clear_recent_projects_menu_action(self): # Renamed to avoid conflict if old one was slot
        reply = QMessageBox.question(self,
                                     "Confirm Clear",
                                     "Are you sure you want to clear all recent projects?",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.user_session_coordinator.perform_clear_recent_projects_action()
        else:
            self.statusBar().showMessage("Clear operation cancelled.", 3000)

    def setup_toolbar(self):
        toolbar = self.addToolBar("Main Toolbar")
        # The following lines were misplaced and caused an IndentationError.
        # They appear to be part of a QInputDialog call and do not belong in setup_toolbar.
        # QLineEdit.Normal, old_path)
        # if ok and new_path:
        #     if new_path != old_path:
        #         try:
        #             # Attempt to rename the actual folder/file if it exists
        #             if os.path.exists(old_path):
        #                 os.rename(old_path, new_path)
        #                 QMessageBox.information(self, "Rename Successful", f"Renamed '{old_path}' to '{new_path}'.")
        #             else:
        #                 QMessageBox.warning(self, "Path Not Found", f"Original path '{old_path}' does not exist. Updating list only.")
        #
        #             # Update in recent projects list
        #             if old_path in self.recent_projects:
        #                 index = self.recent_projects.index(old_path)
        #                 self.recent_projects[index] = new_path
        # The following lines were misplaced and caused an IndentationError.
        # They appear to be part of a QInputDialog call and do not belong in setup_toolbar.
        #                         self._update_recent_menu()
        #                         self.save_session() # Save the updated session
        #                 except OSError as e:
        #                     QMessageBox.critical(self, "Rename Error", f"Could not rename: {e}")
        #             else:
        #                 QMessageBox.information(self, "No Change", "New path is the same as the old path. No action taken.")

    def setup_toolbar(self):
        toolbar = self.addToolBar("Main Toolbar")
        
        config_mgr = ConfigManager() # Added

        # Mode Selector (QComboBox)
        self.language_selector = QComboBox(self)

        language_items = config_mgr.load_setting(
            'language_selector_items',
            DEFAULT_LANGUAGE_SELECTOR_ITEMS
        )

        self.language_selector.clear() # Clear any default items if QComboBox adds one
        if isinstance(language_items, list) and all(isinstance(item, str) for item in language_items):
            self.language_selector.addItems(language_items)
        else: # Fallback if config is malformed
            logger.warning("Malformed language_selector_items in config, using defaults.")
            self.language_selector.addItems(DEFAULT_LANGUAGE_SELECTOR_ITEMS)

        self.language_selector.setFixedWidth(100) # Adjust width as needed
        toolbar.addWidget(self.language_selector)

        # Run Action Button
        self.run_action_button = QAction(QIcon.fromTheme("media-playback-start"), "Run Code (F5)", self)
        self.run_action_button.setToolTip("Run Code (F5)"); self.run_action_button.setShortcut("F5")
        self.run_action_button.triggered.connect(self.execution_coordinator._handle_run_request) # Connect to coordinator
        toolbar.addAction(self.run_action_button)

        # Debug Action Button
        # Using SP_DialogYesButton as a placeholder, replace with a proper debug icon if available
        debug_icon = self.style().standardIcon(QStyle.SP_DialogYesButton)
        try:
            # Try to get a more specific debug icon if the theme provides it
            if QIcon.hasThemeIcon("debug-run"):
                debug_icon = QIcon.fromTheme("debug-run")
            elif QIcon.hasThemeIcon("system-run"): # Fallback if debug-run not found
                 debug_icon = QIcon.fromTheme("system-run")
        except Exception as e:
            logger.warning(f"Could not load debug icon: {e}", exc_info=True)

        self.debug_action_button = QAction(debug_icon, "Debug Code (Ctrl+F5)", self)
        self.debug_action_button.setToolTip("Debug Code (Ctrl+F5)"); self.debug_action_button.setShortcut("Ctrl+F5")
        self.debug_action_button.triggered.connect(self.execution_coordinator._handle_debug_request) # Connect to coordinator
        toolbar.addAction(self.debug_action_button)

        # Add other buttons to the toolbar
        self.request_control_button = QPushButton("Request Control", self)
        self.request_control_button.clicked.connect(self.collaboration_service.request_control) # Connect to service
        toolbar.addWidget(self.request_control_button); self.request_control_button.setEnabled(False)

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
        # Connect to CollaborationService slots
        self.network_manager.data_received.connect(self.collaboration_service.on_network_data_received)
        self.network_manager.status_changed.connect(self.status_bar.showMessage)
        self.network_manager.peer_connected.connect(self.collaboration_service.on_peer_connected)
        self.network_manager.peer_disconnected.connect(self.collaboration_service.on_peer_disconnected)
        
        self.network_manager.control_request_received.connect(self.collaboration_service.on_control_request_received)
        self.network_manager.control_granted.connect(self.collaboration_service.on_control_granted)
        self.network_manager.control_declined.connect(self.collaboration_service.on_control_declined)
        self.network_manager.control_revoked.connect(self.collaboration_service.on_control_revoked)

    # EXTENSION_TO_LANGUAGE is now loaded from ConfigManager into self.extension_to_language_map_config

    RUNNER_CONFIG = { # This RUNNER_CONFIG in MainWindow is effectively dead code now, ExecutionCoordinator loads its own.
        "Python": ["python", "-u", "{file}"],
        # Simplified C++ command: just compile. Running the output file would be a separate step.
        # This is a temporary adjustment due to ProcessManager not handling '&&' or shell chains directly.
        "C++": ["g++", "{file}", "-o", "{output_file}"],
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

            # Update status bar labels
            self.language_label.setText(f"Language: {editor.current_language}")
            self._update_cursor_position_label(editor.textCursor().blockNumber() + 1, editor.textCursor().columnNumber() + 1)
            
            # Auto-select language in QComboBox
            file_path = self.editor_to_path.get(editor)

            if file_path and not file_path.startswith("untitled:"):
                file_extension = os.path.splitext(file_path)[1].lower()
                detected_language = self.extension_to_language_map_config.get(file_extension, "Plain Text")
                idx = self.language_selector.findText(detected_language)
                if idx != -1:
                    self.language_selector.setCurrentIndex(idx)
                else: # Fallback for unknown extensions
                    self.language_selector.setCurrentIndex(self.language_selector.findText("Plain Text"))
            else: # Untitled file or no path
                self.language_selector.setCurrentIndex(self.language_selector.findText("Plain Text"))
        else:
            # Not a CodeEditor tab, or no editor
            if hasattr(self, 'undo_action'): self.undo_action.setEnabled(False) # Check existence
            if hasattr(self, 'redo_action'): self.redo_action.setEnabled(False) # Check existence
            self._active_editor_undo_stack = None # Ensure it's cleared

            self.language_label.setText("Language: N/A")
            self.cursor_pos_label.setText("Ln 1, Col 1")
            # Set language selector to Plain Text if it exists
            if hasattr(self, 'language_selector'):
                plain_text_idx = self.language_selector.findText("Plain Text")
                if plain_text_idx != -1:
                    self.language_selector.setCurrentIndex(plain_text_idx)
                elif self.language_selector.count() > 0: # Fallback to first item if "Plain Text" not found
                    self.language_selector.setCurrentIndex(0)

            # Update breakpoint display for the current editor if it's a CodeEditor
            if isinstance(editor, CodeEditor):
                file_path = editor.file_path
                current_file_breakpoints = self.execution_coordinator.active_breakpoints.get(file_path, set()) # Use ExecutionCoordinator
                editor.gutter.update_breakpoints_display(current_file_breakpoints)
            # If not a CodeEditor, no gutter to update.

    @Slot()
    def join_session_from_welcome_page(self):
        """Public slot to initiate joining a session from the welcome page."""
        self.connect_to_host_session()
        # After attempting to connect, initialize_project(None) will set up the client-only UI
        self.initialize_project(None)

    @Slot()
    def on_text_editor_changed(self):
        current_editor = self._get_current_code_editor()
        # Use collaboration_service's flag for network updates.
        if not current_editor or self.collaboration_service.is_updating_from_network:
            return

        path = self.editor_file_coordinator.editor_to_path.get(current_editor) # Use EFC map
        if not path:
            # Handle untitled tabs or errors
            if current_editor.toPlainText(): # If there's any text, it's dirty from its initial state
                tab_index = self.tab_widget.indexOf(current_editor)
                if tab_index != -1:
                    current_tab_text = self.tab_widget.tabText(tab_index)
                    if not current_tab_text.endswith("*"):
                        self.tab_widget.setTabText(tab_index, current_tab_text + "*")
            return # Do not call FileManager for untracked paths (e.g. untitled)

        # For tracked files, delegate to FileManager
        self.file_manager.update_file_content_changed(path, current_editor.toPlainText())
        
        # Network sync logic uses collaboration_service state
        if self.collaboration_service.is_connected() and self.collaboration_service.has_control and not current_editor.isReadOnly():
            self.network_manager.send_data(NetworkMessageType.TEXT_UPDATE, current_editor.toPlainText())
        
        self._update_undo_redo_actions()

    # All collaboration related slots are now in CollaborationService.

    # _handle_run_request and _handle_debug_request are now in ExecutionCoordinator.
    # ProcessManager and DebugManager signal handlers (_handle_process_..., _on_debug_...) are in ExecutionCoordinator.
    # _handle_breakpoint_toggled is in ExecutionCoordinator.

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
            self.status_bar.showMessage("No active editor to run.", 3000)
            return

        if not self.save_current_file():
            self.status_bar.showMessage("Save operation cancelled or failed. Run aborted.", 3000)
            return

        file_path = self.editor_to_path.get(editor)
        if not file_path or file_path.startswith("untitled:"):
            QMessageBox.warning(self, "Execution Error", "Please save the file before running.")
            return

        _, extension = os.path.splitext(file_path)
        # Ensure this uses the loaded config, though this method itself is likely dead code
        language_name = self.extension_to_language_map_config.get(extension.lower())
        if not language_name:
            QMessageBox.warning(self, "Execution Error", f"No language is configured for file type '{extension}'.")
            return

        # The RUNNER_CONFIG logic is now handled by ExecutionCoordinator.
        # This section is likely dead code and can be removed or commented out.
        # command_template_list = self.RUNNER_CONFIG.get(language_name)
        # if not command_template_list:
        #     QMessageBox.warning(self, "Execution Error", f"No 'run' command is configured for the language '{language_name}'.")
        #     return

        working_dir = os.path.dirname(file_path) or os.getcwd()
        output_file_no_ext = os.path.splitext(file_path)[0]

        # The command construction and execution logic is now handled by ExecutionCoordinator.
        # This section is likely dead code and can be removed or commented out.
        # command_parts = []
        # for part in command_template_list:
        #     part = part.replace("{file}", file_path)
        #     part = part.replace("{output_file}", output_file_no_ext)
        #     command_parts.append(part)
        #
        # if not command_parts:
        #     QMessageBox.warning(self, "Execution Error", "Command became empty after processing template.")
        #     return
        #
        # self.process_manager.execute(command_parts, working_dir)

    # _run_diagnostic_test is removed as its functionality is superseded by ProcessManager.

    def update_editor_read_only_state(self):
        current_editor = self._get_current_code_editor()
        if current_editor:
            # Use collaboration_service state
            if self.collaboration_service.is_connected(): # Use service's helper
                current_editor.setReadOnly(not self.collaboration_service.has_control)
            else:
                current_editor.setReadOnly(False)

    def update_ui_for_control_state(self):
        cs = self.collaboration_service
        status = "Not in session"
        if cs.is_connected():
            if cs.is_host: status = "You have control." if cs.has_control else "Viewer has control. Press key to reclaim."
            else: status = "You have control." if cs.has_control else "Viewing. Click 'Request Control'."
        self.control_status_label.setText(status)
        self.request_control_button.setEnabled(cs.is_connected() and not cs.is_host and not cs.has_control)
        self.update_editor_read_only_state()
        # editor_read_only_status = self._get_current_code_editor().isReadOnly() if self._get_current_code_editor() else 'N/A'
        # print(f"LOG: update_ui_for_control_state - is_host={cs.is_host}, has_control={cs.has_control}, editor_read_only={editor_read_only_status}")

    # Methods moved to EditorFileCoordinator:
    # _get_next_untitled_name, open_new_tab, _handle_file_opened, _handle_file_open_error,
    # close_tab, create_new_file, open_file,
    # _save_file, save_current_file, save_current_file_as,
    # _handle_file_saved, _handle_file_save_error.

    # Methods moved to UserSessionCoordinator:
    # save_session (MainWindow version now delegates to coordinator),
    # _handle_session_loaded (MainWindow version is now a shell for pending_initial_path),
    # _handle_session_saved_confirmation, _handle_session_error,
    # add_recent_project (MainWindow version now delegates to coordinator),
    # _clear_recent_projects (MainWindow version shows dialog then calls coordinator's core logic),
    # _rename_recent_project, _remove_recent_project, _update_recent_projects_from_welcome (these are removed, WelcomeScreen connects to coordinator)

    # Methods moved to CollaborationService:
    # start_hosting_session, connect_to_host_session, stop_current_session,
    # on_network_data_received, on_peer_connected, on_peer_disconnected,
    # request_control, on_control_request_received, on_control_granted,
    # on_control_declined, on_control_revoked, on_host_reclaim_control.

    # Methods moved to ExecutionCoordinator:
    # _handle_run_request, _handle_debug_request,
    # _handle_process_output, _handle_process_started, _handle_process_finished, _handle_process_error,
    # _on_debug_session_started, _on_debug_session_stopped, _on_debugger_paused, _on_debugger_resumed,
    # _handle_breakpoint_toggled.

    @Slot(str, bool) # path, is_dirty
    def _handle_dirty_status_changed(self, path, is_dirty):
        if path in self.path_to_editor:
            editor = self.path_to_editor[path]
            tab_index = self.tab_widget.indexOf(editor)
            if tab_index != -1:
                current_tab_text = self.tab_widget.tabText(tab_index)
                if is_dirty:
                    if not current_tab_text.endswith("*"):
                        self.tab_widget.setTabText(tab_index, current_tab_text + "*")
                else:
                    if current_tab_text.endswith("*"):
                        self.tab_widget.setTabText(tab_index, current_tab_text[:-1])
        # Also handle untitled placeholders directly, as they are in path_to_editor
        elif path.startswith("untitled:"):
            if path in self.path_to_editor:
                editor = self.path_to_editor[path]
                tab_index = self.tab_widget.indexOf(editor)
                if tab_index != -1:
                    current_tab_text = self.tab_widget.tabText(tab_index)
                    # Untitled tabs are marked dirty if is_dirty is true (e.g. on creation or content change)
                    if is_dirty:
                        if not current_tab_text.endswith("*"):
                            self.tab_widget.setTabText(tab_index, current_tab_text + "*")
                    else: # This case might be less common for untitled unless saved
                        if current_tab_text.endswith("*"):
                             self.tab_widget.setTabText(tab_index, current_tab_text[:-1])
            else:
                logger.warning(f"Dirty status changed for untracked untitled path: {path}")
        else:
            logger.warning(f"Dirty status changed for untracked path: {path}")

    def open_folder(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec():
            selected_directory = dialog.selectedFiles()[0]
            self.file_explorer.set_root_path(selected_directory)
            self.setWindowTitle(f"Aether Editor - {os.path.basename(selected_directory)}")
            self.terminal_widget.start_shell(selected_directory) # Start shell in new directory
            self.user_session_coordinator.add_recent_project(selected_directory) # Add to recent projects via coordinator

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
            
            path_for_editor = self.editor_to_path.get(widget)
            proceed_with_close = True # Assume we can close unless dirty check says otherwise

            if path_for_editor:
                is_dirty = False
                if path_for_editor.startswith("untitled:"):
                    # Check UI for dirty state of untitled tab
                    if self.tab_widget.tabText(index_to_close).endswith("*"):
                        is_dirty = True
                elif path_for_editor in self.file_manager.open_files_data:
                    is_dirty = self.file_manager.get_dirty_state(path_for_editor)

                if is_dirty:
                    # Prompt for this specific tab
                    tab_name = self.tab_widget.tabText(index_to_close)
                    reply = QMessageBox.question(self, f"Unsaved Changes - {tab_name}",
                                                 f"'{tab_name}' has unsaved changes. Save before closing?",
                                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                                 QMessageBox.Save)
                    if reply == QMessageBox.Cancel:
                        proceed_with_close = False
                    elif reply == QMessageBox.Save:
                        if not self._save_file(index_to_close): # Attempt to save
                            # User cancelled the save dialog
                            proceed_with_close = False
                    elif reply == QMessageBox.Discard:
                        proceed_with_close = True # Discard changes, proceed to close

            if not proceed_with_close:
                return # Stop the tab closing process

            # If we are here, either file was not dirty, or user chose Discard, or Save was successful.
            if path_for_editor:
                if widget in self.editor_to_path:
                    del self.editor_to_path[widget]
                if path_for_editor in self.path_to_editor:
                    del self.path_to_editor[path_for_editor]

                if not path_for_editor.startswith("untitled:"):
                    self.file_manager.file_closed_in_editor(path_for_editor)
            
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
        editor = self.tab_widget.widget(index)
        if not isinstance(editor, CodeEditor):
            return False

        current_path_placeholder = self.editor_to_path.get(editor)
        content_to_save = editor.toPlainText()
        path_to_save = None

        is_untitled_file = current_path_placeholder is not None and current_path_placeholder.startswith("untitled:")

        if save_as or is_untitled_file:
            suggested_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            suggested_filename_base = "Untitled.py"
            if not is_untitled_file and current_path_placeholder:
                suggested_dir = os.path.dirname(current_path_placeholder)
                suggested_filename_base = os.path.basename(current_path_placeholder)
            elif is_untitled_file and current_path_placeholder: # Untitled file, use its "Untitled-N" name
                 suggested_filename_base = os.path.basename(current_path_placeholder)


            full_suggested_path = os.path.join(suggested_dir, suggested_filename_base)

            new_path_tuple = QFileDialog.getSaveFileName(
                self, "Save File As", full_suggested_path,
                "All Files (*);;Python Files (*.py);;C++ Files (*.cpp *.cxx *.h *.hpp);;Text Files (*.txt)"
            )
            new_path = new_path_tuple[0]

            if not new_path:
                self.status_bar.showMessage("Save operation cancelled.", 3000)
                return False
            path_to_save = new_path
        else:
            path_to_save = current_path_placeholder

        if not path_to_save:
             QMessageBox.critical(self, "Save Error", "No file path determined for saving.")
             return False

        if path_to_save.lower().endswith(".py"):
            try:
                formatted_content = black.format_str(content_to_save, mode=black.FileMode())
                if formatted_content != content_to_save:
                    self.is_updating_from_network = True
                    current_cursor_pos = editor.textCursor().position()
                    editor.setPlainText(formatted_content)
                    new_cursor = editor.textCursor()
                    new_cursor.setPosition(min(current_cursor_pos, len(formatted_content)))
                    editor.setTextCursor(new_cursor)
                    self.is_updating_from_network = False
                    content_to_save = formatted_content
            except black.parsing.LibCSTError as e:
                QMessageBox.critical(self, "Formatting Error", f"Syntax error in Python code. Cannot format and save:\n{e}")
                return False
            except Exception as e:
                logger.warning(f"Black formatting failed (non-syntax error), saving unformatted: {e}", exc_info=True)
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.file_manager.save_file(editor, content_to_save, path_to_save)
        QApplication.restoreOverrideCursor()
        return True

    @Slot(object, str, str) # widget_ref (editor), saved_path, saved_content
    def _handle_file_saved(self, editor_widget, saved_path, saved_content):
        if editor_widget not in self.editor_to_path:
            logger.warning(f"_handle_file_saved received editor_widget not in editor_to_path map. Path: {saved_path}")
            # This could happen if a new untitled file was saved.
            # Or if the editor_widget reference passed by FileManager isn't the one we have.
            # Assuming editor_widget is the correct CodeEditor instance passed to save_file.

        old_path = self.editor_to_path.get(editor_widget)

        if old_path and old_path != saved_path:
            # File was saved under a new name (Save As) or untitled file saved first time
            if old_path in self.path_to_editor:
                del self.path_to_editor[old_path]
        
        self.editor_to_path[editor_widget] = saved_path
        self.path_to_editor[saved_path] = editor_widget
        # Update the editor's internal file_path attribute as well
        if isinstance(editor_widget, CodeEditor):
            editor_widget.file_path = saved_path


        tab_index = self.tab_widget.indexOf(editor_widget)
        if tab_index != -1:
            self.tab_widget.setTabText(tab_index, os.path.basename(saved_path))
            self.tab_widget.setTabToolTip(tab_index, saved_path)
            # The dirty status update (removing '*') is handled by _handle_dirty_status_changed
            # which is triggered by FileManager's dirty_status_changed signal.

        # Content in editor should already be what was saved, as formatting happens in _save_file before calling fm.save_file.
        # If black formatting changed content, editor was updated then.

        self.status_bar.showMessage(f"File '{os.path.basename(saved_path)}' saved successfully.", 3000)
        if hasattr(self, 'file_explorer') and self.file_explorer:
             self.file_explorer.refresh_tree() # Refresh file explorer to show new file or rename

    @Slot(object, str, str) # widget_ref, path_attempted, error_message
    def _handle_file_save_error(self, widget_ref, path_attempted, error_message):
        QMessageBox.critical(self, "File Save Error", f"Could not save file '{path_attempted}':\n{error_message}")
        self.status_bar.showMessage(f"Save error for {path_attempted}", 5000)

    def format_current_code(self):
        current_editor = self._get_current_code_editor()
        if not current_editor:
            self.status_bar.showMessage("No active editor to format.")
            return

        path = self.editor_to_path.get(current_editor)
        if not path or path.startswith("untitled:"):
            self.status_bar.showMessage("Formatting requires a saved Python file.")
            return

        if path.lower().endswith(".py"):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.status_bar.showMessage("Formatting code...")
            original_text = current_editor.toPlainText()
            try:
                formatted_text = black.format_str(original_text, mode=black.FileMode())
                if original_text != formatted_text:
                    self.is_updating_from_network = True
                    current_cursor_pos = current_editor.textCursor().position()
                    current_editor.setPlainText(formatted_text)
                    new_cursor = current_editor.textCursor()
                    new_cursor.setPosition(min(current_cursor_pos, len(formatted_text)))
                    current_editor.setTextCursor(new_cursor)
                    self.is_updating_from_network = False
                    self.file_manager.update_file_content_changed(path, formatted_text)
                self.status_bar.showMessage("Code formatted.")
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

    def _save_file(self, index: int, save_as: bool = False) -> bool:
        editor = self.tab_widget.widget(index)
        if not isinstance(editor, CodeEditor):
            return False

        current_path_placeholder = self.editor_to_path.get(editor)
        content_to_save = editor.toPlainText()
        path_to_save = None

        is_untitled_file = current_path_placeholder is not None and current_path_placeholder.startswith("untitled:")

        if save_as or is_untitled_file:
            suggested_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            suggested_filename_base = "Untitled.py"
            if not is_untitled_file and current_path_placeholder:
                suggested_dir = os.path.dirname(current_path_placeholder)
                suggested_filename_base = os.path.basename(current_path_placeholder)
            elif is_untitled_file and current_path_placeholder: # Untitled file, use its "Untitled-N" name
                 suggested_filename_base = os.path.basename(current_path_placeholder)


            full_suggested_path = os.path.join(suggested_dir, suggested_filename_base)
            
            new_path_tuple = QFileDialog.getSaveFileName(
                self, "Save File As", full_suggested_path,
                "All Files (*);;Python Files (*.py);;C++ Files (*.cpp *.cxx *.h *.hpp);;Text Files (*.txt)"
            )
            new_path = new_path_tuple[0]

            if not new_path:
                self.status_bar.showMessage("Save operation cancelled.", 3000)
                return False
            path_to_save = new_path
        else:
            path_to_save = current_path_placeholder

        if not path_to_save:
             QMessageBox.critical(self, "Save Error", "No file path determined for saving.")
             return False

        if path_to_save.lower().endswith(".py"):
            try:
                formatted_content = black.format_str(content_to_save, mode=black.FileMode())
                if formatted_content != content_to_save:
                    self.is_updating_from_network = True
                    current_cursor_pos = editor.textCursor().position()
                    editor.setPlainText(formatted_content)
                    new_cursor = editor.textCursor()
                    new_cursor.setPosition(min(current_cursor_pos, len(formatted_content)))
                    editor.setTextCursor(new_cursor)
                    self.is_updating_from_network = False
                    content_to_save = formatted_content
            except black.parsing.LibCSTError as e:
                QMessageBox.critical(self, "Formatting Error", f"Syntax error in Python code. Cannot format and save:\n{e}")
                return False
            except Exception as e:
                print(f"Warning: Black formatting failed (non-syntax error), saving unformatted: {e}")

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.file_manager.save_file(editor, content_to_save, path_to_save)
        QApplication.restoreOverrideCursor()
        return True


    def save_session(self):
        if not self.session_manager: # Might be called during early shutdown
            return

        open_files_data = self.file_manager.get_all_open_files_data()

        current_editor_widget = self.tab_widget.currentWidget()
        active_file_path = None
        if isinstance(current_editor_widget, CodeEditor):
            active_file_path = self.editor_to_path.get(current_editor_widget)
            if active_file_path and active_file_path.startswith("untitled:"):
                active_file_path = None # Don't save placeholder as active path

        root_path_to_save = None
        if hasattr(self.file_explorer, 'model') and self.file_explorer.model is not None:
             root_path_to_save = self.file_explorer.model.rootPath()
        else:
            if active_file_path and os.path.exists(active_file_path):
                root_path_to_save = os.path.dirname(active_file_path)
            # print("Warning: File explorer model not available for saving root_path.")

        self.session_manager.save_session(
            open_files_data,
            self.recent_projects,
            root_path_to_save,
            active_file_path
        )

    # Old load_session method is removed. Session loading is now handled by
    # SessionManager emitting session_loaded, which calls _handle_session_loaded.

    @Slot(dict) # session_data
    def _handle_session_loaded(self, session_data):
        # print(f"MainWindow: _handle_session_loaded received: {session_data}")
        self.recent_projects = session_data.get("recent_projects", [])
        self._update_recent_menu()

        root_path_from_session = session_data.get("root_path")
        open_files_data_from_session = session_data.get("open_files_data", {})
        active_file_path_to_restore = session_data.get("active_file_path") # Changed from active_file_index

        # Restore FileManager's state with data from session
        self.file_manager.load_open_files_data(open_files_data_from_session)

        # Initialize project if root_path is available from session
        # This should happen before trying to open files, to set up the file explorer context
        if root_path_from_session:
            self.initialize_project(root_path_from_session, add_to_recents=False)

        # Open files based on the restored data in FileManager
        paths_to_open = sorted(list(open_files_data_from_session.keys()))
        for path in paths_to_open:
            if os.path.exists(path):
                self.file_manager.open_file(path) # This triggers _handle_file_opened
            else:
                logger.warning(f"File path from session not found, skipping: {path}")

        # Process pending_initial_path after session files are potentially opened
        if self.pending_initial_path:
            # Check if the initial_path is already opened by session loading
            # self.path_to_editor should be populated by _handle_file_opened by now
            if not self.path_to_editor.get(self.pending_initial_path):
                # If initial_path was a directory, initialize_project would handle it.
                # If it was a file, it needs to be explicitly opened if not already.
                if os.path.isfile(self.pending_initial_path):
                    # If initialize_project was not called for this root, call it
                    if not root_path_from_session or os.path.dirname(self.pending_initial_path) != root_path_from_session:
                         self.initialize_project(self.pending_initial_path, add_to_recents=True) # add_to_recents might need adjustment
                    else: # Root path matches, just ensure file is open
                        self.file_manager.open_file(self.pending_initial_path)
                elif os.path.isdir(self.pending_initial_path):
                     self.initialize_project(self.pending_initial_path, add_to_recents=True)
            self.pending_initial_path = None


        # Restore active tab - this needs to happen *after* all tabs are created
        # Use active_file_path_to_restore from session data
        if active_file_path_to_restore and active_file_path_to_restore in self.path_to_editor:
            editor_to_activate = self.path_to_editor[active_file_path_to_restore]
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == editor_to_activate:
                    self.tab_widget.setCurrentIndex(i)
                    break
        elif self.tab_widget.count() > 0: # Default to first tab if active one not found or not specified
            self.tab_widget.setCurrentIndex(0)

        self.status_bar.showMessage("Session loaded.", 2000)

    @Slot()
    def _handle_session_saved_confirmation(self):
        # print("MainWindow: Session saved confirmation received.")
        self.status_bar.showMessage("Session saved.", 2000)

    @Slot(str) # error_message
    def _handle_session_error(self, error_message):
        logger.error(f"MainWindow: Session error: {error_message}")
        QMessageBox.warning(self, "Session Error", error_message)
        self.status_bar.showMessage(f"Session error: {error_message}", 5000)


    def _show_welcome_page(self):
        from welcome_screen import WelcomeScreen # Import here to avoid circular dependency
        # Close existing welcome tab if open
        for i in range(self.tab_widget.count()):
            if isinstance(self.tab_widget.widget(i), WelcomeScreen):
                self.tab_widget.removeTab(i)
                break

        self.welcome_page = WelcomeScreen(recent_projects=self.user_session_coordinator.recent_projects)
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
        # Check for unsaved changes across all open, tracked files
        dirty_files_to_save = []
        for editor_widget, path in list(self.editor_to_path.items()): # Iterate over a copy
            is_dirty = False
            if path.startswith("untitled:"):
                # Untitled files are considered dirty if they have content or just exist and are new
                tab_idx = self.tab_widget.indexOf(editor_widget)
                if tab_idx != -1 and self.tab_widget.tabText(tab_idx).endswith("*"): # Check the UI indicator
                    is_dirty = True
            elif path in self.file_manager.open_files_data: # Check tracked files via FileManager
                is_dirty = self.file_manager.get_dirty_state(path)

            if is_dirty:
                dirty_files_to_save.append(editor_widget) # Store editor widget to find its index later

        if dirty_files_to_save:
            reply = QMessageBox.question(self, "Unsaved Changes",
                                         "You have unsaved changes. Do you want to save them before closing?",
                                         QMessageBox.SaveAll | QMessageBox.Discard | QMessageBox.Cancel,
                                         QMessageBox.SaveAll) # Default to SaveAll

            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.SaveAll:
                all_saved_successfully = True
                for editor_widget in dirty_files_to_save:
                    idx = self.tab_widget.indexOf(editor_widget)
                    if idx != -1:
                        # self.tab_widget.setCurrentIndex(idx) # Ensure tab is current for _save_file context
                        if not self._save_file(idx): # Attempt to save
                            all_saved_successfully = False
                            # If a save is cancelled by user, _save_file returns False.
                            # We should then ignore the close event.
                            QMessageBox.warning(self, "Save Cancelled",
                                                f"Save operation was cancelled for '{self.tab_widget.tabText(idx)}'. Closing aborted.")
                            event.ignore()
                            return
                if not all_saved_successfully: # Should be caught by return above, but as safeguard
                    event.ignore()
                    return
            elif reply == QMessageBox.Discard:
                # User chose to discard changes, proceed to close.
                pass
        
        # If all checks pass (no dirty files, or user chose Discard, or all saves succeeded):
        self.save_session() # Save session state (open files list, etc.)
        event.accept() # Allow window to close

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
            
        # If it's an open editor, update its path in mappings and tab title
        # editor, tab_idx = self._find_editor_for_path(old_path) # This helper might be redundant if path_to_editor is source of truth

        try:
            # Inform FileManager first if the path is tracked
            if old_path in self.path_to_editor: # Check if it's an open tab
                editor_widget = self.path_to_editor[old_path] # Get the editor widget
                self.file_manager.rename_path_tracking(old_path, new_path)

                # Update MainWindow's own mappings and UI
                # Remove old path entry, add new path entry for the same editor widget
                self.path_to_editor.pop(old_path)
                self.path_to_editor[new_path] = editor_widget
                self.editor_to_path[editor_widget] = new_path # Update reverse mapping

                editor_widget.file_path = new_path # Update editor's internal file_path attribute

                tab_idx = self.tab_widget.indexOf(editor_widget)
                if tab_idx != -1:
                    self.tab_widget.setTabText(tab_idx, os.path.basename(new_path))
                    self.tab_widget.setTabToolTip(tab_idx, new_path)

            os.rename(old_path, new_path)
            self.status_bar.showMessage(f"Renamed to {os.path.basename(new_path)}")
            if hasattr(self, 'file_explorer'): self.file_explorer.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Rename Error", f"Error renaming: {e}")
            self.status_bar.showMessage(f"Error renaming: {e}")


    @Slot(str)
    def _handle_process_output(self, output_str):
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.append_output(output_str)
            self.terminal_dock.show()
        else:
            logger.info(f"Process Output (no terminal_widget or command_output_viewer): {output_str}") # Adjusted message

    @Slot()
    def _handle_process_started(self):
        self.status_bar.showMessage("Process started...")
        if hasattr(self, 'run_debug_action_button'):
            self.run_debug_action_button.setEnabled(False)
        if hasattr(self, 'terminal_widget') and self.terminal_widget: # Check added
            self.terminal_widget.clear_output()
            self.terminal_dock.show()
            self.terminal_dock.raise_()

    @Slot(int, QProcess.ExitStatus)
    def _handle_process_finished(self, exit_code, exit_status):
        status_text = "successfully" if exit_status == QProcess.NormalExit and exit_code == 0 else f"with errors (code: {exit_code})"
        message = f"Process finished {status_text}."
        self.status_bar.showMessage(message, 5000)
        if hasattr(self, 'terminal_widget') and self.terminal_widget: # Check added
            self.terminal_widget.append_output(f"\n--- {message} ---\n")
        if hasattr(self, 'run_debug_action_button'):
            self.run_debug_action_button.setEnabled(True)

    @Slot(str)
    def _handle_process_error(self, error_message):
        full_error_message = f"Process error: {error_message}"
        QMessageBox.critical(self, "Process Error", full_error_message)
        self.status_bar.showMessage(full_error_message, 5000)
        if hasattr(self, 'terminal_widget') and self.terminal_widget: # Check added
            self.terminal_widget.append_output(f"\n--- ERROR: {error_message} ---\n")
        if hasattr(self, 'run_debug_action_button'):
            self.run_debug_action_button.setEnabled(True)

    def _delete_file_folder(self, index):
        path_to_delete = self.file_explorer.model.filePath(index)
        name_to_delete = os.path.basename(path_to_delete)

        reply = QMessageBox.question(self, "Delete", f"Are you sure you want to delete '{name_to_delete}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                # If path_to_delete is an open tab, close it first.
                # This needs to handle directories as well: close all tabs for files within the directory.
                tabs_to_close_indices = []
                if os.path.isdir(path_to_delete):
                    for editor_widget, open_path in list(self.editor_to_path.items()): # Iterate over a copy for modification
                        if open_path.startswith(path_to_delete + os.sep):
                            tab_idx = self.tab_widget.indexOf(editor_widget)
                            if tab_idx != -1:
                                tabs_to_close_indices.append(tab_idx)
                elif os.path.isfile(path_to_delete):
                    if path_to_delete in self.path_to_editor:
                        editor_widget = self.path_to_editor[path_to_delete]
                        tab_idx = self.tab_widget.indexOf(editor_widget)
                        if tab_idx != -1:
                            tabs_to_close_indices.append(tab_idx)
                
                # Close tabs in reverse order to avoid index issues
                for tab_idx in sorted(list(set(tabs_to_close_indices)), reverse=True): # Ensure unique indices
                    self.close_tab(tab_idx) # close_tab should handle FM.file_closed_in_editor

                # Now perform the actual deletion from the file system
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

    # --- Debugger Integration Slots ---
    @Slot()
    def _handle_debug_request(self):
        editor = self._get_current_code_editor()
        if not editor:
            QMessageBox.information(self, "Debug", "No active editor to debug.")
            return

        file_path = editor.file_path # Using the proxied property
        if not file_path or file_path.startswith("untitled:"):
            QMessageBox.warning(self, "Debug", "Please save the file before debugging.")
            return

        if not self.save_current_file(): # Ensure latest version is saved
            QMessageBox.warning(self, "Debug", "Save operation cancelled or failed. Debug aborted.")
            return

        # Update DebugManager's internal list of breakpoints for all known files
        # This ensures DebugManager has the latest set before starting.
        for path, lines_set in self.active_breakpoints.items():
            self.debug_manager.update_internal_breakpoints(path, lines_set)

        # Start the debug session via DebugManager
        self.debug_manager.start_session(file_path)

    @Slot()
    def _on_debug_session_started(self):
        logger.info("MainWindow: Debug session started.")
        self.debugger_toolbar.setVisible(True)
        self.run_action_button.setEnabled(False)
        self.debug_action_button.setEnabled(False)

        # Initial state of debugger controls
        self.continue_action.setEnabled(True) # Typically debugger starts paused at entry or first breakpoint
        self.step_over_action.setEnabled(False) # Disabled until actually paused
        self.step_into_action.setEnabled(False)
        self.step_out_action.setEnabled(False)
        self.stop_action.setEnabled(True)


    @Slot()
    def _on_debug_session_stopped(self):
        logger.info("MainWindow: Debug session stopped.")
        self.debugger_toolbar.setVisible(False)
        self.run_action_button.setEnabled(True)
        self.debug_action_button.setEnabled(True)

        # Clear debugger UI panels
        self.variables_panel.clear()
        # Re-add the "Locals" placeholder or other top-level items if necessary
        self.variables_panel.addTopLevelItem(QTreeWidgetItem(self.variables_panel, ["Locals"]))
        self.call_stack_panel.clear()
        # Breakpoints panel (self.breakpoints_panel) should retain its state as breakpoints are persistent

        # Clear execution highlight from all open editors
        for editor in self.path_to_editor.values():
            if isinstance(editor, CodeEditor): # Ensure it's a CodeEditor instance
                editor.set_exec_highlight(None)

    @Slot(int, str, list, list)
    def _on_debugger_paused(self, thread_id: int, reason: str, call_stack: list, variables: list):
        logger.info(f"MainWindow: Debugger paused. Thread: {thread_id}, Reason: {reason}")

        self.call_stack_panel.clear()
        for frame in call_stack:
            # Format: {'id': frame_id, 'name': frame_name, 'file': file_path, 'line': line_num}
            item_text = f"{os.path.basename(frame['file'])}:{frame['line']} - {frame['name']}"
            self.call_stack_panel.addItem(QListWidgetItem(item_text))

        self.variables_panel.clear() # Clear previous variables
        # For simplicity, add all variables under a "Locals" or "Current Scope" top-level item
        # Later, this can be more structured based on scopes from DAP

        # Example: Grouping all variables under a "Variables" top-level item
        # More sophisticated handling would use the actual scope names.
        # For now, a flat list is displayed.
        if not variables:
            placeholder_item = QTreeWidgetItem(self.variables_panel, ["No variables in current scope."])
            self.variables_panel.addTopLevelItem(placeholder_item)
        else:
            for var in variables:
                # Format: {'name': var_name, 'type': var_type, 'value': var_value, 'variablesReference': ref_id}
                var_item = QTreeWidgetItem([var['name'], var['value'], var['type']])
                # TODO: Handle expandable variables using var['variablesReference'] > 0 in a future step
                self.variables_panel.addTopLevelItem(var_item)
        self.variables_panel.expandAll() # Optional: expand all variable items

        # Highlight current execution line
        active_editor = self._get_current_code_editor()
        if call_stack: # Check if call_stack is not empty
            current_frame = call_stack[0]
            file_path = current_frame['file']
            line_number = current_frame['line']
            if active_editor and active_editor.file_path == file_path:
                active_editor.set_exec_highlight(line_number)
            elif active_editor: # Current editor is not the file being debugged, or file not open
                active_editor.set_exec_highlight(None)
            # If no active_editor, nothing to highlight or clear for now.
            # If a file becomes active later, its highlight state will be managed then.
        elif active_editor: # No call_stack, but there is an active editor, clear its highlight
            active_editor.set_exec_highlight(None)

        # Update debugger toolbar actions
        self.continue_action.setEnabled(True)
        self.step_over_action.setEnabled(True)
        self.step_into_action.setEnabled(True)
        self.step_out_action.setEnabled(True)
        self.stop_action.setEnabled(True)

        # Bring window to front and focus relevant debugger panel
        self.activateWindow()
        self.raise_()
        if self.left_tab_widget:
            # Find the "Debugger" tab index and switch to it
            for i in range(self.left_tab_widget.count()):
                if self.left_tab_widget.tabText(i) == "Debugger":
                    self.left_tab_widget.setCurrentIndex(i)
                    break


    @Slot()
    def _on_debugger_resumed(self):
        logger.info("MainWindow: Debugger resumed.")
        # Clear variable and call stack panels as the program is running
        self.variables_panel.clear()
        self.variables_panel.addTopLevelItem(QTreeWidgetItem(self.variables_panel, ["Running..."]))
        self.call_stack_panel.clear()
        self.call_stack_panel.addItem(QListWidgetItem("Running..."))

        # Clear execution highlight
        active_editor = self._get_current_code_editor()
        if active_editor:
            active_editor.set_exec_highlight(None)

        # Update debugger toolbar actions
        self.continue_action.setEnabled(False) # Can't continue if already running
        self.step_over_action.setEnabled(False)
        self.step_into_action.setEnabled(False)
        self.step_out_action.setEnabled(False)
        self.stop_action.setEnabled(True) # Stop is always available