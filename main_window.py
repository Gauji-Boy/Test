import sys
import os
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QDockWidget, QApplication, QWidget,
    QVBoxLayout, QMenuBar, QMenu, QFileDialog, QLabel, QToolBar,
    QMessageBox, QLineEdit, QPushButton, QStyle, QTreeWidget, QTreeWidgetItem,
    QListWidget, QListWidgetItem, QComboBox
)
from PySide6.QtGui import QAction, QIcon, QTextCharFormat, QColor, QTextCursor, QFont, QKeySequence
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QStandardPaths, QSize, QByteArray, QDir, QProcess, QTimer

# Import manager classes
from file_manager import FileManager
from process_manager import ProcessManager
from session_manager import SessionManager
from debug_manager_refactored import DebugManagerRefactored # New Import
from network_manager_refactored import NetworkManagerRefactored
from connection_dialog import ConnectionDialog

# Import UI components
from code_editor import CodeEditor
from interactive_terminal import InteractiveTerminal
from file_explorer import FileExplorer

class MainWindow(QMainWindow):
    EXTENSION_TO_LANGUAGE = {
        ".py": "Python", ".pyw": "Python",
        ".js": "JavaScript", ".json": "JSON",
        ".html": "HTML", ".htm": "HTML",
        ".css": "CSS", ".qss": "QSS",
        ".md": "Markdown", ".txt": "Plain Text",
    }

    RUNNER_CONFIG = {
        "Python": ["python", "-u", "{file}"],
        "JavaScript": ["node", "{file}"]
    }

    def __init__(self, initial_path=None):
        super().__init__()
        self.setWindowTitle("Aether Editor")
        self.setGeometry(100, 100, 1400, 900)

        self.file_manager = FileManager(self)
        self.process_manager = ProcessManager(self)
        self.session_manager = SessionManager(self)
        self.debug_manager = DebugManagerRefactored(self)
        self.network_manager = NetworkManagerRefactored(self)

        self.editors_map = {}
        self.untitled_counter = 0
        self.file_explorer = None
        self.active_breakpoints = {}
        self.is_updating_from_network = False
        self.is_host = False
        self.has_control = False


        self._setup_status_bar()
        self._setup_central_widget()
        self._setup_toolbars()
        self._setup_menus()
        self._setup_docks()

        self._connect_manager_signals()

        self.pending_initial_path = initial_path
        self.session_manager.load_session_data()
        self.setObjectName("MainWindow")
        self._update_network_ui_state()

    def _setup_central_widget(self):
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self.tab_widget)

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.cursor_pos_label = QLabel("Ln 1, Col 1")
        self.language_label = QLabel("Lang: Plain Text")
        self.git_branch_label = QLabel("Git: N/A")
        self.control_status_label = QLabel("Not in session")

        self.status_bar.addPermanentWidget(self.cursor_pos_label)
        self.status_bar.addPermanentWidget(self.language_label)
        self.status_bar.addPermanentWidget(self.git_branch_label)
        self.status_bar.addPermanentWidget(self.control_status_label)
        self.status_bar.showMessage("Ready", 3000)

    def _setup_toolbars(self):
        self.main_toolbar = QToolBar("Main Toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.main_toolbar)

        self.run_action = QAction(QIcon.fromTheme("media-playback-start"), "Run Code", self)
        self.run_action.setShortcut(QKeySequence("F5"))
        self.run_action.triggered.connect(self._on_run_code)
        self.main_toolbar.addAction(self.run_action)

        self.debug_file_action = QAction(QIcon.fromTheme("debug-run"), "Debug File", self)
        self.debug_file_action.setShortcut(QKeySequence("Ctrl+F5"))
        self.debug_file_action.triggered.connect(self._on_debug_file_action)
        self.main_toolbar.addAction(self.debug_file_action)

        self.request_control_button = QPushButton("Request Control")
        self.request_control_button.setObjectName("AccentButton")
        self.request_control_button.clicked.connect(self._on_request_editing_control)
        self.main_toolbar.addWidget(self.request_control_button)


        self.debugger_toolbar = QToolBar("Debugger Toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.debugger_toolbar)

        style = self.style()
        self.continue_action = QAction(style.standardIcon(QStyle.SP_MediaPlay), "Continue (F8)", self)
        self.continue_action.setShortcut(QKeySequence("F8"))
        self.continue_action.triggered.connect(self._on_dbg_continue)
        self.debugger_toolbar.addAction(self.continue_action)

        self.step_over_action = QAction(style.standardIcon(QStyle.SP_MediaSkipForward), "Step Over (F10)", self)
        self.step_over_action.setShortcut(QKeySequence("F10"))
        self.step_over_action.triggered.connect(self._on_dbg_step_over)
        self.debugger_toolbar.addAction(self.step_over_action)

        self.step_into_action = QAction(style.standardIcon(QStyle.SP_MediaSeekForward), "Step Into (F11)", self)
        self.step_into_action.setShortcut(QKeySequence("F11"))
        self.step_into_action.triggered.connect(self._on_dbg_step_into)
        self.debugger_toolbar.addAction(self.step_into_action)

        self.step_out_action = QAction(style.standardIcon(QStyle.SP_MediaSeekBackward), "Step Out (Shift+F11)", self)
        self.step_out_action.setShortcut(QKeySequence("Shift+F11"))
        self.step_out_action.triggered.connect(self._on_dbg_step_out)
        self.debugger_toolbar.addAction(self.step_out_action)

        self.debugger_toolbar.addSeparator()
        self.stop_debug_session_action = QAction(style.standardIcon(QStyle.SP_MediaStop), "Stop Debugging (Ctrl+Shift+F5)", self)
        self.stop_debug_session_action.setShortcut(QKeySequence("Ctrl+Shift+F5"))
        self.stop_debug_session_action.triggered.connect(self._on_dbg_stop_session)
        self.debugger_toolbar.addAction(self.stop_debug_session_action)

        self._update_network_ui_state()


    def _setup_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        self.new_file_action = QAction(QIcon.fromTheme("document-new"), "&New File", self)
        self.new_file_action.setShortcut(QKeySequence.New)
        self.new_file_action.triggered.connect(self._on_new_file)
        file_menu.addAction(self.new_file_action)

        self.open_file_action = QAction(QIcon.fromTheme("document-open"), "&Open File...", self)
        self.open_file_action.setShortcut(QKeySequence.Open)
        self.open_file_action.triggered.connect(self._on_open_file)
        file_menu.addAction(self.open_file_action)

        self.open_folder_action = QAction(QIcon.fromTheme("folder-open"), "Open &Folder...", self)
        self.open_folder_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.open_folder_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(self.open_folder_action)

        file_menu.addSeparator()
        self.save_file_action = QAction(QIcon.fromTheme("document-save"), "&Save", self)
        self.save_file_action.setShortcut(QKeySequence.Save)
        self.save_file_action.triggered.connect(self._on_save_file)
        file_menu.addAction(self.save_file_action)

        self.save_as_action = QAction(QIcon.fromTheme("document-save-as"), "Save &As...", self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.save_as_action.triggered.connect(self._on_save_file_as)
        file_menu.addAction(self.save_as_action)

        self.save_all_action = QAction("Save A&ll", self)
        self.save_all_action.setShortcut("Ctrl+Shift+S")
        self.save_all_action.triggered.connect(self._on_save_all_files)
        file_menu.addAction(self.save_all_action)

        file_menu.addSeparator()
        self.close_tab_action = QAction("Close &Tab", self)
        self.close_tab_action.setShortcut(QKeySequence.Close)
        self.close_tab_action.triggered.connect(self._on_close_current_tab)
        file_menu.addAction(self.close_tab_action)

        self.close_all_tabs_action = QAction("Close All Tabs", self)
        self.close_all_tabs_action.triggered.connect(self._on_close_all_tabs)
        file_menu.addAction(self.close_all_tabs_action)

        file_menu.addSeparator()
        exit_action = QAction(QIcon.fromTheme("application-exit"), "&Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        self.undo_action = QAction(QIcon.fromTheme("edit-undo"), "&Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction(QIcon.fromTheme("edit-redo"), "&Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()
        self.format_code_action = QAction("Format Code", self)
        edit_menu.addAction(self.format_code_action)

        self.view_menu = self.menuBar().addMenu("&View")

        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addAction(self.run_action)
        run_menu.addAction(self.debug_file_action)

        session_menu = self.menuBar().addMenu("&Session")
        self.start_host_action = QAction("Start Hosting Session...", self)
        self.start_host_action.triggered.connect(self._on_start_hosting)
        session_menu.addAction(self.start_host_action)

        self.connect_host_action = QAction("Connect to Host...", self)
        self.connect_host_action.triggered.connect(self._on_connect_to_host)
        session_menu.addAction(self.connect_host_action)

        self.stop_session_action = QAction("Stop Current Session", self)
        self.stop_session_action.triggered.connect(self._on_stop_session)
        session_menu.addAction(self.stop_session_action)

        self.menuBar().addMenu("&Tools")
        self.menuBar().addMenu("&Help")

    def _setup_docks(self):
        self.terminal_dock = QDockWidget("Terminal", self)
        self.terminal_dock.setObjectName("TerminalDockWidget")
        self.terminal_widget = InteractiveTerminal(self)
        self.terminal_dock.setWidget(self.terminal_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal_dock)
        if self.view_menu: self.view_menu.addAction(self.terminal_dock.toggleViewAction())

        self.file_explorer_dock = QDockWidget("File Explorer", self)
        self.file_explorer_dock.setObjectName("FileExplorerDockWidget")
        self.file_explorer = FileExplorer(self)
        self.file_explorer_dock.setWidget(self.file_explorer)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.file_explorer_dock)
        if self.view_menu: self.view_menu.addAction(self.file_explorer_dock.toggleViewAction())

        self.debugger_dock = QDockWidget("Debugger", self)
        self.debugger_dock.setObjectName("DebuggerDockWidget")

        debugger_tabs = QTabWidget()
        self.variables_panel = QTreeWidget()
        self.variables_panel.setObjectName("DebuggerVariablesPanel")
        self.variables_panel.setHeaderLabels(["Variable", "Value", "Type"])
        debugger_tabs.addTab(self.variables_panel, "Variables")

        self.call_stack_panel = QListWidget()
        self.call_stack_panel.setObjectName("DebuggerCallStackPanel")
        debugger_tabs.addTab(self.call_stack_panel, "Call Stack")

        self.breakpoints_panel = QListWidget()
        self.breakpoints_panel.setObjectName("DebuggerBreakpointsPanel")
        debugger_tabs.addTab(self.breakpoints_panel, "Breakpoints")

        self.debugger_dock.setWidget(debugger_tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, self.debugger_dock)
        self.debugger_dock.setVisible(False)
        if self.view_menu: self.view_menu.addAction(self.debugger_dock.toggleViewAction())


    def _connect_manager_signals(self):
        # FileManager
        self.file_manager.file_opened.connect(self._on_file_opened_by_manager)
        self.file_manager.file_saved.connect(self._on_file_saved_by_manager)
        self.file_manager.error_occurred.connect(self._on_file_manager_error)
        self.file_manager.dirty_status_changed.connect(self._on_dirty_status_changed_by_manager)
        self.file_manager.file_closed_in_editor.connect(self._on_file_closed_by_manager)
        self.file_manager.item_created.connect(self._on_fm_item_created)
        self.file_manager.item_renamed.connect(self._on_fm_item_renamed)
        self.file_manager.item_deleted.connect(self._on_fm_item_deleted)

        # ProcessManager
        self.process_manager.output_received.connect(self._on_process_output)
        self.process_manager.process_started.connect(self._on_process_started)
        self.process_manager.process_finished.connect(self._on_process_finished)
        self.process_manager.process_error.connect(self._on_process_error)

        # SessionManager
        self.session_manager.session_data_loaded.connect(self._on_session_data_loaded)
        self.session_manager.session_data_saved.connect(self._on_session_data_saved)
        self.session_manager.session_error.connect(self._on_session_manager_error)

        # FileExplorer
        if self.file_explorer:
            self.file_explorer.file_open_requested.connect(self._on_explorer_file_open_requested)
            self.file_explorer.create_new_file_requested.connect(self._on_explorer_create_new_file)
            self.file_explorer.create_new_folder_requested.connect(self._on_explorer_create_new_folder)
            self.file_explorer.rename_item_requested.connect(self._on_explorer_rename_item)
            self.file_explorer.delete_item_requested.connect(self._on_explorer_delete_item)
            self.file_explorer.open_in_terminal_requested.connect(self._on_explorer_open_in_terminal)

        # DebugManager
        self.debug_manager.session_started.connect(self._on_debug_session_started)
        self.debug_manager.session_stopped.connect(self._on_debug_session_stopped)
        self.debug_manager.paused.connect(self._on_debugger_paused)
        self.debug_manager.resumed.connect(self._on_debugger_resumed)
        self.debug_manager.output_received.connect(self._on_debug_output_received)
        self.debug_manager.dap_error.connect(self._on_dap_error)

        # NetworkManager
        self.network_manager.connected_to_peer.connect(self._on_peer_connected)
        self.network_manager.disconnected_from_peer.connect(self._on_peer_disconnected)
        self.network_manager.data_received_from_peer.connect(self._on_network_data_received)
        self.network_manager.error_occurred.connect(self._on_network_error)
        self.network_manager.status_message.connect(self._on_network_status_message)
        self.network_manager.editing_control_acquired.connect(self._on_editing_control_acquired)
        self.network_manager.editing_control_lost.connect(self._on_editing_control_lost)
        self.network_manager.control_request_received.connect(self._on_network_control_request_received)
        self.network_manager.control_request_declined.connect(self._on_network_control_request_declined)


    @Slot()
    def _on_new_file(self):
        self.untitled_counter += 1
        file_path = f"untitled-{self.untitled_counter}"
        self._create_new_editor_tab(file_path, "", is_dirty=True, is_new_untitled=True)

    @Slot()
    def _on_open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File", QDir.homePath())
        if file_path:
            if file_path in self.editors_map:
                self.tab_widget.setCurrentWidget(self.editors_map[file_path])
            else:
                self.file_manager.open_file(file_path)

    @Slot()
    def _on_open_folder(self):
        start_dir = QDir.homePath()
        if hasattr(self, 'file_explorer') and self.file_explorer and hasattr(self.file_explorer, 'current_root_path') and self.file_explorer.current_root_path:
            start_dir = self.file_explorer.current_root_path

        folder_path = QFileDialog.getExistingDirectory(
            self, "Open Folder", start_dir,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )
        if folder_path:
            norm_folder_path = os.path.normpath(folder_path)
            if hasattr(self, 'file_explorer') and self.file_explorer:
                self.file_explorer.set_root_path(norm_folder_path)
                self.setWindowTitle(f"Aether Editor - {os.path.basename(norm_folder_path)}")
            else:
                self.setWindowTitle(f"Aether Editor - {os.path.basename(norm_folder_path)}")
            if hasattr(self, 'terminal_widget') and self.terminal_widget:
                self.terminal_widget.start_shell(norm_folder_path)
            self.status_bar.showMessage(f"Opened folder: {norm_folder_path}", 3000)
        else:
            self.status_bar.showMessage("Open folder cancelled.", 3000)

    @Slot()
    def _on_save_file(self):
        current_editor = self._get_current_editor()
        if not current_editor: return
        file_path = self._get_current_file_path()
        if not file_path: return
        content = current_editor.get_text()
        if file_path.startswith("untitled-"):
            self._on_save_file_as()
        else:
            self.file_manager.save_file(file_path, content)

    @Slot()
    def _on_save_file_as(self):
        current_editor = self._get_current_editor()
        if not current_editor: return
        current_path_key = self._get_current_file_path()
        if not current_path_key: return

        suggested_name = os.path.basename(current_path_key) if not current_path_key.startswith("untitled-") else f"untitled-{self.untitled_counter}.py"
        default_dir = os.path.dirname(current_path_key) if not current_path_key.startswith("untitled-") and os.path.isdir(os.path.dirname(current_path_key)) else QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)

        new_file_path, _ = QFileDialog.getSaveFileName(self, "Save File As", os.path.join(default_dir, suggested_name))
        if new_file_path:
            content = current_editor.get_text()
            self.file_manager.save_file(current_path_key, content, new_path_for_save_as=new_file_path)


    @Slot()
    def _on_save_all_files(self):
        for path_key, editor in list(self.editors_map.items()):
            if editor.is_modified():
                content = editor.get_text()
                if path_key.startswith("untitled-"):
                    if self.tab_widget.currentWidget() == editor:
                         self._on_save_file_as()
                else:
                    self.file_manager.save_file(path_key, content)

    @Slot(int)
    def _on_tab_close_requested(self, index: int):
        editor_widget = self.tab_widget.widget(index)
        if not isinstance(editor_widget, CodeEditor):
            self.tab_widget.removeTab(index)
            return

        file_path = self._get_path_for_editor(editor_widget)
        if not file_path:
            self.tab_widget.removeTab(index)
            return

        if editor_widget.is_modified():
            reply = QMessageBox.question(self, "Unsaved Changes",
                                         f"'{os.path.basename(file_path)}' has unsaved changes. Save before closing?",
                                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if reply == QMessageBox.Cancel: return
            if reply == QMessageBox.Save:
                current_content = editor_widget.get_text()
                if file_path.startswith("untitled-"):
                    self.file_manager.save_file(file_path, current_content, new_path_for_save_as=None)
                    if not editor_widget.is_modified():
                         self.file_manager.close_file_requested(file_path)
                    return
                else:
                    self.file_manager.save_file(file_path, current_content)
                    if not editor_widget.is_modified():
                        self.file_manager.close_file_requested(file_path)
                    return

        if not editor_widget.is_modified():
            self.file_manager.close_file_requested(file_path)

    @Slot()
    def _on_close_current_tab(self):
        current_index = self.tab_widget.currentIndex()
        if current_index != -1:
            self._on_tab_close_requested(current_index)

    @Slot()
    def _on_close_all_tabs(self):
        for i in range(self.tab_widget.count() - 1, -1, -1):
            self.tab_widget.setCurrentIndex(i)
            self._on_tab_close_requested(i)
            if self.tab_widget.widget(i) and self.tab_widget.widget(i).is_modified():
                break

    @Slot(str, str, bool)
    def _on_file_opened_by_manager(self, path: str, content: str, is_dirty: bool):
        if path in self.editors_map:
            self.tab_widget.setCurrentWidget(self.editors_map[path])
            return
        self._create_new_editor_tab(path, content, is_dirty)
        self.status_bar.showMessage(f"Opened: {path}", 3000)

    @Slot(str, str)
    def _on_file_saved_by_manager(self, path: str, new_content: str):
        editor_to_update = None
        old_path_key_to_remove = None

        for p_key, ed in list(self.editors_map.items()):
            if p_key.startswith("untitled-") and ed.get_text() == new_content:
                editor_to_update = ed
                old_path_key_to_remove = p_key
                break
            elif ed.get_text() == new_content and p_key != path:
                 if self.tab_widget.currentWidget() == ed:
                    editor_to_update = ed
                    old_path_key_to_remove = p_key
                    break

        if not editor_to_update and path in self.editors_map:
             editor_to_update = self.editors_map[path]
        elif not editor_to_update and not old_path_key_to_remove:
            print(f"MainWindow: _on_file_saved_by_manager for a new path '{path}' with no clear prior editor instance.")
            if path not in self.editors_map:
                self._create_new_editor_tab(path, new_content, is_dirty=False)
            return

        if editor_to_update:
            if old_path_key_to_remove and old_path_key_to_remove != path:
                if old_path_key_to_remove in self.editors_map:
                    del self.editors_map[old_path_key_to_remove]

            self.editors_map[path] = editor_to_update
            editor_to_update.set_file_path_context(path)

            if editor_to_update.get_text() != new_content:
                editor_to_update.set_text(new_content, is_modified=False)
            else:
                editor_to_update.set_modified(False)

            tab_index = self.tab_widget.indexOf(editor_to_update)
            if tab_index != -1:
                self.tab_widget.setTabText(tab_index, os.path.basename(path))
                self.tab_widget.setTabToolTip(tab_index, path)

            self.status_bar.showMessage(f"Saved: {path}", 3000)
            self._update_status_bar_for_editor(editor_to_update)
            if self.tab_widget.currentWidget() == editor_to_update:
                 self._on_current_tab_changed(tab_index)
        else:
             if path not in self.editors_map:
                 self._create_new_editor_tab(path, new_content, is_dirty=False)
                 self.status_bar.showMessage(f"Saved new file: {path}", 3000)
             else:
                 editor = self.editors_map[path]
                 editor.set_text(new_content, is_modified=False)
                 self.status_bar.showMessage(f"Formatted and Saved: {path}", 3000)


    @Slot(str, bool)
    def _on_dirty_status_changed_by_manager(self, path: str, is_dirty: bool):
        editor = self.editors_map.get(path)
        if editor:
            tab_index = self.tab_widget.indexOf(editor)
            if tab_index != -1:
                current_tab_text = self.tab_widget.tabText(tab_index)
                base_name = os.path.basename(path) if not path.startswith("untitled-") else path

                has_star = current_tab_text.endswith("*")
                if is_dirty and not has_star:
                    self.tab_widget.setTabText(tab_index, base_name + "*")
                elif not is_dirty and has_star:
                    self.tab_widget.setTabText(tab_index, base_name)
            editor.set_modified(is_dirty)

    @Slot(str)
    def _on_file_closed_by_manager(self, path: str):
        editor_to_close = self.editors_map.pop(path, None)
        if editor_to_close:
            tab_index = self.tab_widget.indexOf(editor_to_close)
            if tab_index != -1:
                try: editor_to_close.text_changed.disconnect(self._on_editor_text_changed)
                except RuntimeError: pass
                try: editor_to_close.cursor_position_changed.disconnect(self._on_editor_cursor_position_changed)
                except RuntimeError: pass
                try: editor_to_close.modification_changed.disconnect()
                except RuntimeError: pass
                try: editor_to_close.breakpoint_toggled_in_editor.disconnect(self._on_editor_breakpoint_toggled)
                except RuntimeError: pass

                self.tab_widget.removeTab(tab_index)
            editor_to_close.deleteLater()
            print(f"MainWindow: Closed tab and editor for {path}")
            if self.tab_widget.count() == 0:
                self._clear_status_bar_file_specifics()
                self.undo_action.setEnabled(False)
                self.redo_action.setEnabled(False)
        else:
            print(f"MainWindow: Warning - file_closed_by_manager for path not in editor_map: {path}")
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if isinstance(widget, CodeEditor) and self._get_path_for_editor(widget) == path:
                    self.tab_widget.removeTab(i)
                    widget.deleteLater()
                    break


    @Slot(str, str)
    def _on_file_manager_error(self, title: str, message: str):
        QMessageBox.critical(self, title, message)
        self.status_bar.showMessage(f"File Error: {title}", 5000)

    def _create_new_editor_tab(self, file_path: str, content: str, is_dirty: bool = False, is_new_untitled: bool = False):
        if file_path in self.editors_map:
            self.tab_widget.setCurrentWidget(self.editors_map[file_path])
            return

        editor = CodeEditor(file_path_context=file_path, parent=self)
        editor.set_text(content, is_modified=is_dirty)

        editor.text_changed.connect(self._on_editor_text_changed)
        editor.cursor_position_changed.connect(self._on_editor_cursor_position_changed)
        editor.modification_changed.connect(lambda modified, p=file_path: self._on_editor_modification_changed(p, modified))
        editor.breakpoint_toggled_in_editor.connect(self._on_editor_breakpoint_toggled)

        editor.update_breakpoints_display(self.active_breakpoints.get(file_path, set()))


        self.editors_map[file_path] = editor

        tab_name = os.path.basename(file_path) if not file_path.startswith("untitled-") else file_path
        if is_dirty and not tab_name.endswith("*"):
            tab_name += "*"

        tab_index = self.tab_widget.addTab(editor, tab_name)
        self.tab_widget.setTabToolTip(tab_index, file_path if not file_path.startswith("untitled-") else "New unsaved file")
        self.tab_widget.setCurrentIndex(tab_index)

        if is_new_untitled:
            self.file_manager.update_dirty_status(file_path, True)


    @Slot()
    def _on_editor_text_changed(self):
        current_editor = self._get_current_editor()
        if current_editor:
            if not self.is_updating_from_network:
                current_editor.document().setModified(True)
                if self.network_manager.is_connected() and self.has_control:
                    path = self._get_current_file_path()
                    if path:
                        payload = {"path": path, "content": current_editor.get_text(), "is_dirty": current_editor.is_modified()}
                        self.network_manager.send_data_to_peer("full_text_sync", payload)

    @Slot(int, int)
    def _on_editor_cursor_position_changed(self, line: int, col: int):
        self.cursor_pos_label.setText(f"Ln {line}, Col {col}")

    @Slot(str, bool)
    def _on_editor_modification_changed(self, path: str, modified_state: bool):
        self.file_manager.update_dirty_status(path, modified_state)
        editor = self.editors_map.get(path)
        if editor and self.tab_widget.currentWidget() == editor:
            self.undo_action.setEnabled(editor.get_undo_stack().canUndo())
            self.redo_action.setEnabled(editor.get_undo_stack().canRedo())

    @Slot(int)
    def _on_current_tab_changed(self, index: int):
        if index == -1:
            self._clear_status_bar_file_specifics()
            self.undo_action.setEnabled(False); self.redo_action.setEnabled(False)
            try:
                self.undo_action.triggered.disconnect()
                self.redo_action.triggered.disconnect()
            except RuntimeError: pass
            return

        current_editor = self.tab_widget.widget(index)
        if isinstance(current_editor, CodeEditor):
            self._update_status_bar_for_editor(current_editor)
            current_editor.set_read_only(self.network_manager.is_connected() and not self.has_control)
            try:
                self.undo_action.triggered.disconnect()
                self.redo_action.triggered.disconnect()
            except RuntimeError: pass
            self.undo_action.triggered.connect(current_editor.undo)
            self.redo_action.triggered.connect(current_editor.redo)
            self.undo_action.setEnabled(current_editor.get_undo_stack().canUndo())
            self.redo_action.setEnabled(current_editor.get_undo_stack().canRedo())
            current_editor.ensure_cursor_visible()
        else:
            self._clear_status_bar_file_specifics()
            self.undo_action.setEnabled(False); self.redo_action.setEnabled(False)
            try:
                self.undo_action.triggered.disconnect()
                self.redo_action.triggered.disconnect()
            except RuntimeError: pass


    def _update_status_bar_for_editor(self, editor: CodeEditor):
        path = self._get_path_for_editor(editor)
        language = "Plain Text"
        if path and not path.startswith("untitled-"):
            _, ext = os.path.splitext(path)
            language = self.EXTENSION_TO_LANGUAGE.get(ext.lower(), "Plain Text")
        elif path and path.startswith("untitled-"):
             language = "Plain Text"
        editor.set_language(language)
        self.language_label.setText(f"Lang: {language}")

    def _clear_status_bar_file_specifics(self):
        self.cursor_pos_label.setText("Ln 1, Col 1")
        self.language_label.setText("Lang: N/A")

    def _get_current_editor(self) -> CodeEditor | None:
        widget = self.tab_widget.currentWidget()
        return widget if isinstance(widget, CodeEditor) else None

    def _get_current_file_path(self) -> str | None:
        editor = self._get_current_editor()
        return self._get_path_for_editor(editor) if editor else None

    def _get_path_for_editor(self, editor_to_find: CodeEditor) -> str | None:
        for path, editor in self.editors_map.items():
            if editor == editor_to_find: return path
        return None

    @Slot()
    def _on_run_code(self):
        current_editor = self._get_current_editor()
        if not current_editor:
            QMessageBox.warning(self, "Run Error", "No active file to run."); return
        file_path = self._get_current_file_path()
        if not file_path or file_path.startswith("untitled-"):
            QMessageBox.warning(self, "Run Error", "Please save the file before running."); return

        if current_editor.is_modified():
            if not self.file_manager.save_file(file_path, current_editor.get_text()):
                 QMessageBox.warning(self, "Run Error", "Could not save file. Run aborted."); return

        _, extension = os.path.splitext(file_path)
        language_name = self.EXTENSION_TO_LANGUAGE.get(extension.lower())
        if not language_name:
            QMessageBox.warning(self, "Run Error", f"No language configured for '{extension}'."); return
        command_template = self.RUNNER_CONFIG.get(language_name)
        if not command_template:
            QMessageBox.warning(self, "Run Error", f"No runner configured for '{language_name}'."); return

        command_parts = [part.replace("{file}", file_path) for part in command_template]
        working_dir = os.path.dirname(file_path) if file_path else os.getcwd()

        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.clear_output()
            if hasattr(self, 'terminal_dock') and self.terminal_dock:
                self.terminal_dock.show()
                self.terminal_dock.raise_()

        self.process_manager.execute(command_parts, working_dir)

    @Slot(str)
    def _on_process_output(self, output: str):
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.append_output(output)
        else:
            print(f"Process Output (no terminal): {output.strip()}")

    @Slot()
    def _on_process_started(self):
        self.status_bar.showMessage("Process started...", 2000)
        self.run_action.setEnabled(False)
        if hasattr(self, 'terminal_dock') and self.terminal_dock:
            self.terminal_dock.show()
            self.terminal_dock.raise_()

    @Slot(int, "QProcess::ExitStatus")
    def _on_process_finished(self, exit_code: int, exit_status):
        status_text = "successfully" if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0 else f"with errors (code: {exit_code})"
        msg = f"Process finished {status_text}."
        self.status_bar.showMessage(msg, 3000)
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.append_output(f"\n--- {msg} ---\n")
        self.run_action.setEnabled(True)

    @Slot(str)
    def _on_process_error(self, error_message: str):
        QMessageBox.critical(self, "Process Error", error_message)
        self.status_bar.showMessage(f"Process error: {error_message}", 5000)
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.append_output(f"\n--- PROCESS ERROR: {error_message} ---\n")
        self.run_action.setEnabled(True)

    @Slot(dict)
    def _on_session_data_loaded(self, data: dict):
        print(f"MainWindow: Session data loaded: {list(data.keys())}")

        if "window_geometry" in data:
            try: self.restoreGeometry(QByteArray.fromBase64(data["window_geometry"].encode()))
            except Exception as e: print(f"Error restoring window geometry: {e}")

        self.active_breakpoints = data.get("active_breakpoints", {})
        self._update_breakpoints_panel_ui()

        open_file_paths = data.get("open_file_paths", [])
        active_file_path_from_session = data.get("active_file_path")

        for path in open_file_paths:
            self.file_manager.open_file(path)

        if self.pending_initial_path and self.pending_initial_path not in open_file_paths:
            self.file_manager.open_file(self.pending_initial_path)
            if not active_file_path_from_session:
                 active_file_path_from_session = self.pending_initial_path
        self.pending_initial_path = None

        QTimer.singleShot(100, lambda: self._set_active_tab_from_session(active_file_path_from_session))

        file_explorer_root = data.get("file_explorer_root")
        effective_fe_root = QDir.homePath()
        if self.file_explorer:
            if file_explorer_root and os.path.isdir(file_explorer_root):
                effective_fe_root = file_explorer_root
            elif open_file_paths:
                first_file_dir = os.path.dirname(open_file_paths[0])
                if os.path.isdir(first_file_dir): effective_fe_root = first_file_dir

            self.file_explorer.set_root_path(effective_fe_root)
            if effective_fe_root != QDir.homePath() or os.path.basename(effective_fe_root) != "":
                 self.setWindowTitle(f"Aether Editor - {os.path.basename(effective_fe_root if effective_fe_root != QDir.homePath() else 'Home')}")


        terminal_start_path = effective_fe_root
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.start_shell(terminal_start_path)

        self.status_bar.showMessage("Session loaded.", 2000)

    def _set_active_tab_from_session(self, active_path: str | None):
        if active_path and active_path in self.editors_map:
            self.tab_widget.setCurrentWidget(self.editors_map[active_path])
        elif self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)


    @Slot()
    def _on_session_data_saved(self):
        self.status_bar.showMessage("Session saved.", 2000)

    @Slot(str)
    def _on_session_manager_error(self, message: str):
        QMessageBox.warning(self, "Session Error", message)
        self.status_bar.showMessage(f"Session Error: {message}", 5000)

    def closeEvent(self, event):
        dirty_paths = [path for path, editor in self.editors_map.items() if editor.is_modified()]
        if dirty_paths:
            file_list_str = "\n - ".join([os.path.basename(p) for p in dirty_paths[:5]])
            if len(dirty_paths) > 5: file_list_str += f"\n - ...and {len(dirty_paths) - 5} more."

            reply = QMessageBox.question(self, "Unsaved Changes",
                                         f"Save changes to the following files before closing?\n - {file_list_str}",
                                         QMessageBox.SaveAll | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.SaveAll)
            if reply == QMessageBox.Cancel:
                event.ignore(); return
            if reply == QMessageBox.SaveAll:
                self._on_save_all_files()
                if any(self.editors_map[p].is_modified() for p in dirty_paths if p in self.editors_map):
                    QMessageBox.warning(self, "Close Aborted", "Some files were not saved. Closing aborted.")
                    event.ignore(); return

        session_state = {
            "open_file_paths": list(self.editors_map.keys()),
            "active_file_path": self._get_current_file_path(),
            "window_geometry": self.saveGeometry().toBase64().data().decode(),
            "file_explorer_root": self.file_explorer.current_root_path if self.file_explorer else QDir.homePath(),
            "active_breakpoints": self.active_breakpoints,
        }
        self.session_manager.save_session_data(session_state)
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.stop_shell()
        event.accept()

    # --- FileExplorer Signal Handlers ---
    @Slot(str)
    def _on_explorer_file_open_requested(self, path: str):
        if path in self.editors_map:
            self.tab_widget.setCurrentWidget(self.editors_map[path])
        else:
            self.file_manager.open_file(path)

    @Slot(str)
    def _on_explorer_create_new_file(self, parent_dir_path: str):
        file_name, ok = QInputDialog.getText(self, "New File", "Enter file name:", QLineEdit.Normal, "untitled.txt")
        if ok and file_name:
            full_path = os.path.join(parent_dir_path, file_name)
            self.file_manager.create_new_file(full_path)

    @Slot(str)
    def _on_explorer_create_new_folder(self, parent_dir_path: str):
        folder_name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:", QLineEdit.Normal, "NewFolder")
        if ok and folder_name:
            full_path = os.path.join(parent_dir_path, folder_name)
            self.file_manager.create_new_folder(full_path)

    @Slot(str, str)
    def _on_explorer_rename_item(self, old_path: str, new_name: str):
        parent_dir = os.path.dirname(old_path)
        new_full_path = os.path.join(parent_dir, new_name)
        self.file_manager.rename_item(old_path, new_full_path)

    @Slot(str)
    def _on_explorer_delete_item(self, path_to_delete: str):
        self.file_manager.delete_item(path_to_delete)

    @Slot(str)
    def _on_explorer_open_in_terminal(self, directory_path: str):
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.start_shell(directory_path)
            if hasattr(self, 'terminal_dock') and self.terminal_dock:
                self.terminal_dock.show()
                self.terminal_dock.raise_()
        else:
            QMessageBox.information(self, "Terminal", "Terminal component not available.")

    # --- FileManager Item Change Signal Handlers ---
    @Slot(str, bool)
    def _on_fm_item_created(self, path: str, is_directory: bool):
        if hasattr(self, 'file_explorer') and self.file_explorer:
            parent_dir = os.path.dirname(path)
            if parent_dir == self.file_explorer.current_root_path or parent_dir.startswith(self.file_explorer.current_root_path + os.sep):
                 self.file_explorer.refresh_path(parent_dir)
            elif path == self.file_explorer.current_root_path:
                 self.file_explorer.refresh_path(path)
        item_type = "Folder" if is_directory else "File"
        self.status_bar.showMessage(f"{item_type} created: {os.path.basename(path)}", 3000)

    @Slot(str, str)
    def _on_fm_item_renamed(self, old_path: str, new_path: str):
        if hasattr(self, 'file_explorer') and self.file_explorer:
            self.file_explorer.refresh_path(os.path.dirname(old_path))
            if os.path.dirname(old_path) != os.path.dirname(new_path):
                self.file_explorer.refresh_path(os.path.dirname(new_path))

        if old_path in self.editors_map:
            editor = self.editors_map.pop(old_path)
            self.editors_map[new_path] = editor
            editor.set_file_path_context(new_path)
            tab_index = self.tab_widget.indexOf(editor)
            if tab_index != -1:
                self.tab_widget.setTabText(tab_index, os.path.basename(new_path))
                self.tab_widget.setTabToolTip(tab_index, new_path)
                is_dirty = editor.is_modified()
                self.file_manager.update_dirty_status(new_path, is_dirty)
            if self.tab_widget.currentWidget() == editor:
                 self._update_status_bar_for_editor(editor)

        if hasattr(self, 'active_breakpoints') and old_path in self.active_breakpoints:
            self.active_breakpoints[new_path] = self.active_breakpoints.pop(old_path)
            self._update_breakpoints_panel_ui()

        self.status_bar.showMessage(f"Renamed: {os.path.basename(old_path)} to {os.path.basename(new_path)}", 3000)

    @Slot(str)
    def _on_fm_item_deleted(self, path_deleted: str):
        if hasattr(self, 'file_explorer') and self.file_explorer:
            self.file_explorer.refresh_path(os.path.dirname(path_deleted))

        if path_deleted in self.editors_map:
            editor_to_close = self.editors_map.pop(path_deleted)
            tab_index = self.tab_widget.indexOf(editor_to_close)
            if tab_index != -1:
                try: editor_to_close.text_changed.disconnect(self._on_editor_text_changed)
                except RuntimeError: pass
                try: editor_to_close.cursor_position_changed.disconnect(self._on_editor_cursor_position_changed)
                except RuntimeError: pass
                try: editor_to_close.modification_changed.disconnect()
                except RuntimeError: pass
                try: editor_to_close.breakpoint_toggled_in_editor.disconnect(self._on_editor_breakpoint_toggled)
                except RuntimeError: pass
                self.tab_widget.removeTab(tab_index)
            editor_to_close.deleteLater()
            QMessageBox.information(self, "File Deleted", f"The open file '{os.path.basename(path_deleted)}' has been deleted from disk and closed.")

        if hasattr(self, 'active_breakpoints') and path_deleted in self.active_breakpoints:
            del self.active_breakpoints[path_deleted]
            self._update_breakpoints_panel_ui()

        self.status_bar.showMessage(f"Deleted: {os.path.basename(path_deleted)}", 3000)

    # --- Debugger Related Slots & Methods ---
    @Slot()
    def _on_debug_file_action(self):
        current_editor = self._get_current_editor()
        if not current_editor:
            QMessageBox.warning(self, "Debug Error", "No active file to debug."); return
        file_path = self._get_current_file_path()
        if not file_path or file_path.startswith("untitled-"):
            QMessageBox.warning(self, "Debug Error", "Please save the file before debugging."); return

        if current_editor.is_modified():
            reply = QMessageBox.question(self, "Save File",
                                         f"'{os.path.basename(file_path)}' has unsaved changes. Save before debugging?",
                                         QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Save)
            if reply == QMessageBox.Cancel: return
            if reply == QMessageBox.Save:
                if not self.file_manager.save_file(file_path, current_editor.get_text()):
                    QMessageBox.warning(self, "Debug Error", "Could not save file. Debug aborted."); return

        self.debug_manager.start_session(file_path)

    @Slot()
    def _on_dbg_continue(self): self.debug_manager.continue_execution()
    @Slot()
    def _on_dbg_step_over(self): self.debug_manager.step_over()
    @Slot()
    def _on_dbg_step_into(self): self.debug_manager.step_into()
    @Slot()
    def _on_dbg_step_out(self): self.debug_manager.step_out()
    @Slot()
    def _on_dbg_stop_session(self): self.debug_manager.stop_session()

    @Slot()
    def _on_debug_session_started(self):
        self.debugger_toolbar.setVisible(True)
        self.debugger_dock.setVisible(True)
        self.run_action.setEnabled(False)
        self.debug_file_action.setEnabled(False)
        self.stop_debug_session_action.setEnabled(True)
        self.continue_action.setEnabled(False)
        self.step_over_action.setEnabled(False)
        self.step_into_action.setEnabled(False)
        self.step_out_action.setEnabled(False)
        self.status_bar.showMessage("Debug session started.", 3000)

    @Slot()
    def _on_debug_session_stopped(self):
        self.debugger_toolbar.setVisible(False)
        self.debugger_dock.setVisible(False)
        self.run_action.setEnabled(True)
        self.debug_file_action.setEnabled(True)
        self.continue_action.setEnabled(False)
        self.step_over_action.setEnabled(False)
        self.step_into_action.setEnabled(False)
        self.step_out_action.setEnabled(False)
        self.stop_debug_session_action.setEnabled(False)

        self.call_stack_panel.clear()
        self.variables_panel.clear()
        for editor in self.editors_map.values():
            editor.set_exec_highlight(None)
        self.status_bar.showMessage("Debug session stopped.", 3000)

    @Slot(int, str, list, list)
    def _on_debugger_paused(self, thread_id: int, reason: str, call_stack_data: list, variables_data: list):
        self.call_stack_panel.clear()
        for frame in call_stack_data:
            item_text = f"{os.path.basename(frame['file'])}:{frame['line']} - {frame['name']}"
            self.call_stack_panel.addItem(QListWidgetItem(item_text))

        self.variables_panel.clear()
        for var in variables_data:
            item = QTreeWidgetItem([var.get('name', ''), var.get('value', ''), var.get('type', '')])
            self.variables_panel.addTopLevelItem(item)
        self.variables_panel.expandAll()

        self.continue_action.setEnabled(True)
        self.step_over_action.setEnabled(True)
        self.step_into_action.setEnabled(True)
        self.step_out_action.setEnabled(True)
        self.stop_debug_session_action.setEnabled(True)

        if call_stack_data:
            top_frame = call_stack_data[0]
            file_path = top_frame.get("file")
            line_number = top_frame.get("line")
            if file_path and line_number > 0:
                editor = self.editors_map.get(file_path)
                if editor:
                    editor.set_exec_highlight(line_number)
                    if self.tab_widget.currentWidget() != editor:
                         self.tab_widget.setCurrentWidget(editor)
                    editor.ensure_cursor_visible()
                else:
                    self.file_manager.open_file(file_path)
        self.status_bar.showMessage(f"Debugger paused: {reason}", 0)
        self.debugger_dock.show()
        self.debugger_dock.raise_()

    @Slot()
    def _on_debugger_resumed(self):
        self.call_stack_panel.clear()
        self.variables_panel.clear()
        self.continue_action.setEnabled(False)
        self.step_over_action.setEnabled(False)
        self.step_into_action.setEnabled(False)
        self.step_out_action.setEnabled(False)
        for editor in self.editors_map.values():
            editor.set_exec_highlight(None)
        self.status_bar.showMessage("Debugger resumed...", 2000)

    @Slot(str, str)
    def _on_debug_output_received(self, category: str, message: str):
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.append_output(f"[DBG:{category}] {message}")
            if category in ["stderr", "adapter_error", "dap_error"]:
                if hasattr(self, 'terminal_dock') and self.terminal_dock:
                    self.terminal_dock.show()
                    self.terminal_dock.raise_()
        else:
            print(f"[DBG:{category}] {message.strip()}")

    @Slot(str)
    def _on_dap_error(self, message: str):
        QMessageBox.critical(self, "Debugger Error", message)
        self.status_bar.showMessage(f"Debugger Error: {message}", 5000)

    # --- Breakpoint Management ---
    @Slot(str, int)
    def _on_editor_breakpoint_toggled(self, file_path: str, line_number: int):
        norm_path = os.path.normpath(file_path)
        if norm_path not in self.active_breakpoints:
            self.active_breakpoints[norm_path] = set()

        if line_number in self.active_breakpoints[norm_path]:
            self.active_breakpoints[norm_path].remove(line_number)
        else:
            self.active_breakpoints[norm_path].add(line_number)

        if not self.active_breakpoints[norm_path]:
            del self.active_breakpoints[norm_path]

        self.debug_manager.update_internal_breakpoints(norm_path, self.active_breakpoints.get(norm_path, set()))
        self._update_breakpoints_panel_ui()

    def _update_breakpoints_panel_ui(self):
        if not hasattr(self, 'breakpoints_panel'): return
        self.breakpoints_panel.clear()
        for path, lines in self.active_breakpoints.items():
            for line in sorted(list(lines)):
                self.breakpoints_panel.addItem(f"{os.path.basename(path)}:{line}")

    # --- Network/Collaboration Slots ---
    @Slot()
    def _on_start_hosting(self):
        port, ok = QInputDialog.getInt(self, "Start Hosting", "Enter port number:", 12345, 1024, 65535, 1)
        if ok:
            if self.network_manager.start_hosting_session(port):
                self.is_host = True
                self.has_control = True # Host starts with control
                self._update_network_ui_state()
            # else: NetworkManager will emit error_occurred

    @Slot()
    def _on_connect_to_host(self):
        details, ok = ConnectionDialog.get_details(self) # Assuming ConnectionDialog is available
        if ok and details:
            host, port_str = details.split(":")
            try:
                port = int(port_str)
                if self.network_manager.connect_to_host_session(host, port):
                    self.is_host = False
                    self.has_control = False # Client starts without control
                    self._update_network_ui_state()
                # else: NetworkManager will emit error_occurred
            except ValueError:
                QMessageBox.warning(self, "Connection Error", "Invalid port number.")


    @Slot()
    def _on_stop_session(self):
        self.network_manager.stop_current_session()
        # UI updates will be handled by _on_peer_disconnected and _update_network_ui_state

    @Slot()
    def _on_request_editing_control(self):
        if self.network_manager.is_connected() and not self.is_host and not self.has_control:
            self.network_manager.request_editing_control()
        elif self.is_host and not self.has_control: # Host wants to reclaim control
            self.network_manager.reclaim_editing_control()


    @Slot()
    def _on_peer_connected(self):
        self._update_network_ui_state()
        self.status_bar.showMessage("Connected to peer.", 3000)
        # If client, send initial text of current document if any
        if not self.is_host:
            current_editor = self._get_current_editor()
            current_path = self._get_current_file_path()
            if current_editor and current_path:
                 payload = {"path": current_path, "content": current_editor.get_text(), "is_dirty": current_editor.is_modified()}
                 self.network_manager.send_data_to_peer("full_text_sync", payload)


    @Slot()
    def _on_peer_disconnected(self):
        self.is_host = False # Reset host status
        self.has_control = False # Reset control status
        self._update_network_ui_state()
        self.status_bar.showMessage("Disconnected from peer.", 3000)
        QMessageBox.information(self, "Network Session", "Disconnected from peer.")


    @Slot(str, object)
    def _on_network_data_received(self, message_type: str, payload: dict):
        self.is_updating_from_network = True
        try:
            if message_type == "full_text_sync":
                path = payload.get("path")
                content = payload.get("content")
                is_dirty = payload.get("is_dirty", False)
                if path:
                    editor = self.editors_map.get(path)
                    if not editor: # File not open, open it
                        self._create_new_editor_tab(path, content, is_dirty)
                        self.file_manager.open_files_data[path] = {"content_on_disk": content, "is_dirty": is_dirty} # Track it in FM too
                    else:
                        # Preserve cursor position if possible (simple version)
                        cursor = editor.text_edit.textCursor()
                        old_pos = cursor.position()
                        editor.set_text(content, is_modified=is_dirty)
                        if old_pos <= len(content):
                            cursor.setPosition(old_pos)
                            editor.text_edit.setTextCursor(cursor)
                    self.status_bar.showMessage(f"Received update for {os.path.basename(path)}", 2000)
            # Add other message_type handlers here (e.g., incremental diffs, cursor positions)
        finally:
            self.is_updating_from_network = False


    @Slot(str)
    def _on_network_error(self, message: str):
        QMessageBox.critical(self, "Network Error", message)
        self.status_bar.showMessage(f"Network Error: {message}", 5000)
        self._update_network_ui_state() # Update UI as connection might be lost

    @Slot(str)
    def _on_network_status_message(self, message: str):
        self.status_bar.showMessage(message, 3000)

    @Slot()
    def _on_editing_control_acquired(self):
        self.has_control = True
        self._update_network_ui_state()
        self.status_bar.showMessage("You now have editing control.", 3000)

    @Slot()
    def _on_editing_control_lost(self):
        self.has_control = False
        self._update_network_ui_state()
        self.status_bar.showMessage("You no longer have editing control.", 3000)

    @Slot()
    def _on_network_control_request_received(self): # Host-side
        if self.is_host:
            reply = QMessageBox.question(self, "Control Request",
                                         "Client is requesting editing control. Grant?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            self.network_manager.respond_to_control_request(reply == QMessageBox.Yes)

    @Slot()
    def _on_network_control_request_declined(self): # Client-side
        QMessageBox.information(self, "Control Request", "Host declined your request for editing control.")
        self._update_network_ui_state()


    def _update_network_ui_state(self):
        connected = self.network_manager.is_connected()

        self.start_host_action.setEnabled(not connected)
        self.connect_host_action.setEnabled(not connected)
        self.stop_session_action.setEnabled(connected)

        if connected:
            if self.is_host:
                self.request_control_button.setText("Reclaim Control")
                self.request_control_button.setEnabled(not self.has_control) # Can reclaim if client has control
                self.control_status_label.setText(f"Hosting. You {'have' if self.has_control else 'gave away'} control.")
            else: # Client
                self.request_control_button.setText("Request Control")
                self.request_control_button.setEnabled(not self.has_control) # Can request if client doesn't have control
                self.control_status_label.setText(f"Client. You {'have' if self.has_control else 'do not have'} control.")
        else: # Not connected
            self.request_control_button.setText("Request Control")
            self.request_control_button.setEnabled(False)
            self.control_status_label.setText("Not in session")

        # Update editor read-only states
        for editor in self.editors_map.values():
            is_read_only = connected and not self.has_control
            editor.set_read_only(is_read_only)

        # Update debugger toolbar based on debug state (this might be better in _update_debug_ui_state)
        # For now, just ensuring network state doesn't wrongly enable/disable them.
        # self.debugger_toolbar.setVisible(self.debug_manager.is_session_active()) # Example


# Minimal main execution for testing if this file is run directly (usually done in main.py)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     window = MainWindow()
#     window.show()
#     sys.exit(app.exec())

[end of main_window.py]
