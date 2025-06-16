import sys
import os
import platform
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QDockWidget, QToolBar, QPlainTextEdit,
    QListView, QMessageBox, QFileDialog, QTreeView,
    QListWidget, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, QSize, QByteArray, QProcess, QStringListModel, QFileInfo, QDir, QFileIconProvider
from PySide6.QtGui import (
    QAction, QKeySequence, QTextCursor, QCloseEvent,
    QIcon, QStandardItemModel, QStandardItem
)

# Custom module imports
from session_manager import SessionManager
from file_manager import FileManager
from process_manager import ProcessManager
from interactive_terminal import InteractiveTerminal
from debug_manager import DebugManager
from code_editor import CodeEditor
from file_explorer import FileExplorer # Added import
from welcome_page import WelcomePage # Added import

class MainWindow(QMainWindow):
    RUNNER_CONFIG = {
        "python": ["python", "{filepath}"],
        "javascript": ["node", "{filepath}"],
        "html": ["open", "{filepath}"],
        "text": ["cat", "{filepath}"],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aether Editor")
        self.resize(QSize(1200, 800))
        self.untitled_counter = 1
        self.current_thread_id = None
        self._program_to_launch_after_dap_init = None
        self.breakpoints_map = {}
        self.scope_item_map = {} # For mapping variablesReference to QTreeWidgetItem

        self._define_actions()

        self.session_manager = SessionManager()
        self.file_manager = FileManager()
        self.process_manager = ProcessManager()
        self.debug_manager = DebugManager(self)
        self.welcome_page = None # Initialize welcome_page attribute

        self._setup_ui() # This will call _setup_debugger_ui internally
        self._setup_menus()
        self._setup_connections()

        self.load_session() # This might open files

        # Show welcome page if no tabs are open after loading session
        if self.tab_widget.count() == 0:
            self._show_welcome_page()

        if not self.statusBar().currentMessage() and self.tab_widget.count() > 0 : # Avoid overwriting session messages
            self.statusBar().showMessage("Application initialized.", 3000)


    def _define_actions(self):
        self.new_file_action = QAction("&New", self)
        self.new_file_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_file_action.setStatusTip("Create a new file")

        self.open_file_action = QAction("&Open...", self)
        self.open_file_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_file_action.setStatusTip("Open an existing file")

        self.save_file_action = QAction("&Save", self)
        self.save_file_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_file_action.setStatusTip("Save the current file")

        self.save_as_file_action = QAction("Save &As...", self)
        self.save_as_file_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_file_action.setStatusTip("Save the current file with a new name")

        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.setStatusTip("Quit the application")
        self.quit_action.triggered.connect(QApplication.instance().quit)

        self.run_action = QAction("&Run", self)
        self.run_action.setShortcut(QKeySequence(Qt.Key_F5))
        self.run_action.setStatusTip("Run the current file")

        self.start_debug_action = QAction("Start &Debugging", self)
        self.start_debug_action.setShortcut(QKeySequence(Qt.Key_F6))
        self.start_debug_action.setStatusTip("Start a debug session for the current file")

        self.continue_action = QAction("&Continue", self)
        self.continue_action.setShortcut(QKeySequence(Qt.Key_F8))
        self.continue_action.setStatusTip("Continue execution")
        self.continue_action.setEnabled(False)

        self.step_over_action = QAction("Step &Over", self)
        self.step_over_action.setShortcut(QKeySequence(Qt.Key_F10))
        self.step_over_action.setStatusTip("Step over the current line")
        self.step_over_action.setEnabled(False)

        self.step_in_action = QAction("Step &In", self)
        self.step_in_action.setShortcut(QKeySequence(Qt.Key_F11))
        self.step_in_action.setStatusTip("Step into the current function call")
        self.step_in_action.setEnabled(False)

        self.step_out_action = QAction("Step O&ut", self)
        self.step_out_action.setShortcut(QKeySequence(Qt.ShiftModifier | Qt.Key_F11))
        self.step_out_action.setStatusTip("Step out of the current function")
        self.step_out_action.setEnabled(False)

        self.stop_debug_action = QAction("S&top Debugging", self)
        self.stop_debug_action.setShortcut(QKeySequence(Qt.ShiftModifier | Qt.Key_F5))
        self.stop_debug_action.setStatusTip("Stop the current debug session")
        self.stop_debug_action.setEnabled(False)
        
        self.toggle_breakpoint_action = QAction("&Toggle Breakpoint", self)
        self.toggle_breakpoint_action.setShortcut(QKeySequence(Qt.Key_F9))
        self.toggle_breakpoint_action.setStatusTip("Toggle a breakpoint on the current line")

        self.request_control_action = QAction("Request Control", self)
        # Add icon later: self.request_control_action.setIcon(QIcon.fromTheme("system-run")) # Example
        self.request_control_action.setStatusTip("Request control from AI co-pilot")

        self.ai_assistant_action = QAction("AI Assistant", self)
        # Add icon later: self.ai_assistant_action.setIcon(QIcon.fromTheme("help-contents")) # Example
        self.ai_assistant_action.setStatusTip("Open AI Assistant panel")

    def _setup_ui(self):
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.setCentralWidget(self.tab_widget)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        
        self.terminal = InteractiveTerminal(self)
        terminal_dock = QDockWidget("Terminal", self)
        terminal_dock.setObjectName("TerminalDockWidget")
        terminal_dock.setWidget(self.terminal)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, terminal_dock)
        working_dir = os.getcwd() if os.path.exists(os.getcwd()) else os.path.expanduser("~")
        if working_dir: self.terminal.start_shell(working_dir)
        else: self.terminal.display_area.appendPlainText("[System: Critical error - no valid CWD for terminal.]")

        self.file_explorer_dock = QDockWidget("File Explorer", self) # Changed to self.file_explorer_dock
        self.file_explorer_dock.setObjectName("FileExplorerDockWidget")
        self.file_explorer = FileExplorer(self) # Create actual FileExplorer
        self.file_explorer_dock.setWidget(self.file_explorer)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.file_explorer_dock)


        # File Operations Toolbar
        self.file_toolbar = QToolBar("File Operations")
        self.file_toolbar.setObjectName("FileOperationsToolBar") # Changed object name for clarity
        self.file_toolbar.setWindowTitle("File Operations")
        self.file_toolbar.addAction(self.new_file_action)
        self.file_toolbar.addAction(self.open_file_action)
        self.file_toolbar.addAction(self.save_file_action)
        self.file_toolbar.addAction(self.save_as_file_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.file_toolbar) # Ensure it's added to a specific area
        self.file_toolbar.setMovable(True)
        self.file_toolbar.setFloatable(True)

        # Execution Toolbar
        self.execution_toolbar = QToolBar("Execution")
        self.execution_toolbar.setObjectName("ExecutionToolBar")

        self.language_selector = QComboBox()
        self.language_selector.addItems(["Python", "JavaScript", "HTML"]) # Placeholder items
        self.language_selector.setToolTip("Select Language")
        self.execution_toolbar.addWidget(self.language_selector)

        self.run_mode_selector = QComboBox()
        self.run_mode_selector.addItems(["Run", "Debug"])
        self.run_mode_selector.setToolTip("Select Run Mode")
        self.execution_toolbar.addWidget(self.run_mode_selector)

        self.execution_toolbar.addAction(self.run_action) # Moved from old run_toolbar
        self.execution_toolbar.addAction(self.request_control_action)
        self.execution_toolbar.addAction(self.ai_assistant_action)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.execution_toolbar)
        self.execution_toolbar.setMovable(True)
        self.execution_toolbar.setFloatable(True)

        # Remove old run_toolbar as its functionality is merged into execution_toolbar
        # if hasattr(self, 'run_toolbar'):
        #     self.removeToolBar(self.run_toolbar)
        #     del self.run_toolbar

        self.debug_toolbar = QToolBar("Debug Toolbar") # This might be conditionally shown later based on run_mode_selector
        self.debug_toolbar.setObjectName("DebugToolBar")
        self.debug_toolbar.addAction(self.start_debug_action)
        self.debug_toolbar.addAction(self.continue_action)
        self.debug_toolbar.addAction(self.step_over_action)
        self.debug_toolbar.addAction(self.step_in_action)
        self.debug_toolbar.addAction(self.step_out_action)
        self.debug_toolbar.addAction(self.stop_debug_action)
        self.debug_toolbar.addAction(self.toggle_breakpoint_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.debug_toolbar) # Added to the same area for consistency
        self.debug_toolbar.setMovable(True)
        self.debug_toolbar.setFloatable(True)
        self.debug_toolbar.setVisible(True) # Keep visible for now, future logic might hide/show it

        self._setup_debugger_ui() # New consolidated debugger UI

    def _setup_debugger_ui(self):
        self.debugger_dock = QDockWidget("Debugger", self)
        self.debugger_dock.setObjectName("DebuggerDockWidget")
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.debugger_dock)

        self.debugger_tabs = QTabWidget()
        self.debugger_dock.setWidget(self.debugger_tabs)

        # Call Stack Tab
        self.call_stack_list = QListWidget()
        self.debugger_tabs.addTab(self.call_stack_list, "Call Stack")

        # Variables Tab
        self.variables_tree = QTreeWidget()
        self.variables_tree.setHeaderLabels(["Name", "Value", "Type"])
        self.debugger_tabs.addTab(self.variables_tree, "Variables")

        # Watch Tab
        self.watch_tree = QTreeWidget()
        self.watch_tree.setHeaderLabels(["Name", "Value", "Type"]) # Assuming same structure
        self.debugger_tabs.addTab(self.watch_tree, "Watch")

        # Breakpoints Tab
        self.breakpoints_list = QListWidget()
        self.debugger_tabs.addTab(self.breakpoints_list, "Breakpoints")

        self.debugger_dock.setVisible(False) # Initially hidden

    def _setup_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_file_action)
        file_menu.addAction(self.open_file_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_file_action)
        file_menu.addAction(self.save_as_file_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addAction(self.run_action)
        
        debug_menu = self.menuBar().addMenu("&Debug")
        debug_menu.addAction(self.start_debug_action)
        debug_menu.addAction(self.stop_debug_action)
        debug_menu.addSeparator()
        debug_menu.addAction(self.continue_action)
        debug_menu.addAction(self.step_over_action)
        debug_menu.addAction(self.step_in_action)
        debug_menu.addAction(self.step_out_action)
        debug_menu.addSeparator()
        debug_menu.addAction(self.toggle_breakpoint_action)

        help_menu = self.menuBar().addMenu("&Help")
        if not hasattr(self, 'about_action'):
            self.about_action = QAction("About", self)
        help_menu.addAction(self.about_action)

    def _setup_connections(self):
        self.new_file_action.triggered.connect(self._on_new_file_action)
        self.open_file_action.triggered.connect(self._on_open_file_action)
        self.save_file_action.triggered.connect(self._on_save_file_action)
        self.save_as_file_action.triggered.connect(self._on_save_as_file_action)

        self.file_manager.file_content_loaded.connect(self._on_file_content_loaded)
        self.file_manager.file_saved.connect(self._on_file_saved)
        self.file_manager.error_occurred.connect(self._on_file_manager_error)

        self.run_action.triggered.connect(self._on_run_action)
        self.process_manager.output_received.connect(self._on_process_output)
        self.process_manager.process_finished.connect(self._on_process_finished)
        self.process_manager.process_error.connect(self._on_process_error)

        self.start_debug_action.triggered.connect(self._on_start_debug_action)
        self.continue_action.triggered.connect(self._on_continue_action)
        self.step_over_action.triggered.connect(self._on_step_over_action)
        self.step_in_action.triggered.connect(self._on_step_in_action)
        self.step_out_action.triggered.connect(self._on_step_out_action)
        self.stop_debug_action.triggered.connect(self._on_stop_debug_action)
        self.toggle_breakpoint_action.triggered.connect(self._on_toggle_breakpoint_action)

        self.debug_manager.dap_initialized.connect(self._on_dap_initialized)
        self.debug_manager.dap_launched.connect(self._on_dap_launched)
        self.debug_manager.dap_terminated.connect(self._on_dap_terminated)
        self.debug_manager.breakpoint_hit.connect(self._on_breakpoint_hit)
        self.debug_manager.threads_received.connect(self._on_threads_received)
        self.debug_manager.stack_frames_received.connect(self._on_stack_frames_received)
        self.debug_manager.scopes_received.connect(self._on_scopes_received)
        self.debug_manager.variables_received.connect(self._on_variables_received)
        self.debug_manager.dap_output.connect(self._on_dap_output)
        self.debug_manager.dap_error.connect(self._on_dap_error)

        if hasattr(self, 'file_explorer'):
            self.file_explorer.file_opened.connect(self._on_file_explorer_open_file)
            self.file_explorer.back_to_welcome_requested.connect(self._on_back_to_welcome_requested)


    def _on_file_explorer_open_file(self, path_str: str):
        # This slot is called when a file is double-clicked in the FileExplorer
        self.file_manager.open_file(path_str) # This will trigger _on_file_content_loaded
        # _on_file_content_loaded will handle switching from welcome page

    def _on_new_file_action(self):
        if self.centralWidget() == self.welcome_page and self.welcome_page is not None:
            self.setCentralWidget(self.tab_widget)
            self.welcome_page.setVisible(False)
            # Make relevant toolbars visible if they were hidden for welcome page
            self.file_toolbar.setVisible(True)
            self.execution_toolbar.setVisible(True)
            self.debug_toolbar.setVisible(True)


        editor = CodeEditor(self)
        editor.textChanged.connect(lambda editor_instance=editor: self._on_editor_text_changed_generic(editor_instance))
        if hasattr(editor, 'breakpoint_toggled'):
             editor.breakpoint_toggled.connect(self._on_editor_breakpoint_toggled)
        tab_name = f"Untitled-{self.untitled_counter}"
        self.untitled_counter += 1
        tab_index = self.tab_widget.addTab(editor, tab_name)
        self.tab_widget.setCurrentIndex(tab_index)
        self.file_manager.track_new_tab(editor, None)
        editor.setFocus()
        self.statusBar().showMessage(f"Created {tab_name}", 3000)

    def _on_save_file_action(self):
        current_widget = self.tab_widget.currentWidget()
        if isinstance(current_widget, CodeEditor):
            file_path = self.file_manager.get_file_path(current_widget)
            if file_path:
                self.file_manager.save_file(current_widget, file_path)
            else:
                self._on_save_as_file_action()
        else:
            self.statusBar().showMessage("No active editor tab to save.", 3000)

    def _on_save_as_file_action(self):
        current_widget = self.tab_widget.currentWidget()
        if isinstance(current_widget, CodeEditor):
            current_tab_text = self.tab_widget.tabText(self.tab_widget.currentIndex())
            suggested_name = current_tab_text if not current_tab_text.startswith("Untitled-") else "untitled.txt"
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save File As", suggested_name,
                "All Files (*);;Text Files (*.txt);;Python Files (*.py)"
            )
            if file_path:
                self.file_manager.save_file(current_widget, file_path)
        else:
            self.statusBar().showMessage("No active editor tab to save as.", 3000)

    def _on_open_file_action(self):
        # This is for the "File > Open" menu or toolbar action
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open File", os.getcwd(), # Start in current working directory or last known
            "All Files (*);;Text Files (*.txt);;Python Files (*.py)"
        )
        if file_paths:
            for path_str in file_paths:
                if path_str:
                    self.file_manager.open_file(path_str) # This will trigger _on_file_content_loaded
                    # _on_file_content_loaded will handle switching from welcome page

    def _on_file_content_loaded(self, path: str, content: str):
        if self.centralWidget() == self.welcome_page and self.welcome_page is not None:
            self.setCentralWidget(self.tab_widget)
            self.welcome_page.setVisible(False)
            # Make relevant toolbars visible if they were hidden for welcome page
            self.file_toolbar.setVisible(True)
            self.execution_toolbar.setVisible(True)
            self.debug_toolbar.setVisible(True)

        for i in range(self.tab_widget.count()):
            editor_widget = self.tab_widget.widget(i)
            if isinstance(editor_widget, CodeEditor) and self.file_manager.get_file_path(editor_widget) == path:
                self.tab_widget.setCurrentIndex(i)
                if hasattr(editor_widget, 'textChanged') and not self._is_signal_connected(editor_widget.textChanged, self._on_editor_text_changed_generic):
                    editor_widget.textChanged.connect(lambda editor_instance=editor_widget: self._on_editor_text_changed_generic(editor_instance))
                if hasattr(editor_widget, 'breakpoint_toggled') and not self._is_signal_connected(editor_widget.breakpoint_toggled, self._on_editor_breakpoint_toggled):
                     editor_widget.breakpoint_toggled.connect(self._on_editor_breakpoint_toggled)
                if hasattr(editor_widget, 'set_file_path_and_update_language'):
                    editor_widget.set_file_path_and_update_language(path)
                return

        editor = CodeEditor(self)
        editor.setPlainText(content)
        if hasattr(editor, 'set_file_path_and_update_language'):
            editor.set_file_path_and_update_language(path)

        editor.textChanged.connect(lambda editor_instance=editor: self._on_editor_text_changed_generic(editor_instance))
        if hasattr(editor, 'breakpoint_toggled'):
             editor.breakpoint_toggled.connect(self._on_editor_breakpoint_toggled)

        filename = Path(path).name
        tab_index = self.tab_widget.addTab(editor, filename)

        # Set tab icon
        icon_provider = QFileIconProvider()
        file_info = QFileInfo(path)
        icon = icon_provider.icon(file_info)
        self.tab_widget.setTabIcon(tab_index, icon)

        self.tab_widget.setCurrentIndex(tab_index)
        self.file_manager.track_new_tab(editor, path)
        self.statusBar().showMessage(f"Opened: {filename}", 3000)
        editor.setFocus()

    def _on_file_saved(self, widget: QWidget, new_path: str, new_content: str):
        if isinstance(widget, CodeEditor):
            widget.blockSignals(True)
            old_cursor_pos = widget.textCursor().position()
            old_h_scroll = widget.horizontalScrollBar().value()
            old_v_scroll = widget.verticalScrollBar().value()

            widget.setPlainText(new_content)

            new_cursor = widget.textCursor()
            new_cursor.setPosition(min(old_cursor_pos, len(new_content)))
            widget.setTextCursor(new_cursor)
            widget.horizontalScrollBar().setValue(old_h_scroll)
            widget.verticalScrollBar().setValue(old_v_scroll)

            widget.blockSignals(False)

            tab_index = self.tab_widget.indexOf(widget)
            if tab_index != -1:
                filename = Path(new_path).name
                self.tab_widget.setTabText(tab_index, filename)
                self.statusBar().showMessage(f"Saved: {filename}", 3000)
        else:
            self.statusBar().showMessage(f"Error: Saved widget not a CodeEditor for {new_path}", 3000)

    def _on_file_manager_error(self, message: str):
        QMessageBox.critical(self, "File Operation Error", message)

    def _on_tab_close_requested(self, index: int):
        widget_to_close = self.tab_widget.widget(index)
        if not widget_to_close: return
        if self.file_manager.is_dirty(widget_to_close):
            file_path_str = self.file_manager.get_file_path(widget_to_close)
            filename = Path(file_path_str).name if file_path_str else self.tab_widget.tabText(index)
            reply = QMessageBox.question(self, 'Save Changes?',
                                       f"'{filename}' has unsaved changes. Save before closing?",
                                       QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                if file_path_str:
                    self.file_manager.save_file(widget_to_close, file_path_str)
                else:
                    self._on_save_as_file_action()
                    if self.file_manager.is_dirty(widget_to_close):
                        if self.file_manager.is_dirty(widget_to_close): # Check if save as actually saved it
                            return # Don't close if still dirty (e.g., user cancelled save as dialog)
            elif reply == QMessageBox.StandardButton.Cancel:
                return # User cancelled closing, do nothing
            # If Discard or if Save was successful and file is no longer dirty:

        self.file_manager.untrack_tab(widget_to_close)
        self.tab_widget.removeTab(index)

        if self.tab_widget.count() == 0:
            self._show_welcome_page()

    def _on_run_action(self):
        current_editor = self.tab_widget.currentWidget()
        if not isinstance(current_editor, CodeEditor):
            self.statusBar().showMessage("No active code editor selected to run.", 3000); return
        file_path_str = self.file_manager.get_file_path(current_editor)
        if not file_path_str:
            reply = QMessageBox.question(self, "Save Before Running?", "This file needs to be saved. Save now?",
                                       QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                self._on_save_as_file_action(); file_path_str = self.file_manager.get_file_path(current_editor)
                if not file_path_str: self.statusBar().showMessage("File not saved. Run cancelled.", 3000); return
            else: self.statusBar().showMessage("Run cancelled.", 3000); return
        if self.file_manager.is_dirty(current_editor):
            reply = QMessageBox.question(self, "Save Changes Before Running?",
                                       f"'{Path(file_path_str).name}' has unsaved changes. Save before running?",
                                       QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Run | QMessageBox.StandardButton.Cancel,
                                       defaultButton=QMessageBox.StandardButton.Run)
            if reply == QMessageBox.StandardButton.Save: self.file_manager.save_file(current_editor, file_path_str)
            elif reply == QMessageBox.StandardButton.Cancel: self.statusBar().showMessage("Run cancelled.", 3000); return
        file_path_obj = Path(file_path_str); file_extension = file_path_obj.suffix.lstrip('.')
        runner_command_template = self.RUNNER_CONFIG.get(file_extension)
        if platform.system() == "Windows":
            if file_extension == "html": runner_command_template = ["cmd", "/c", "start", "{filepath}"]
            elif file_extension == "text": runner_command_template = ["cmd", "/c", "type", "{filepath}"]
        if not runner_command_template:
            QMessageBox.warning(self, "Cannot Run File", f"No runner for '.{file_extension}'."); return
        command_list = [part.replace("{filepath}", str(file_path_obj.resolve())) for part in runner_command_template]
        working_dir = str(file_path_obj.parent)
        self.terminal.display_area.appendPlainText(f"\n[Running: {' '.join(command_list)} in {working_dir}]\n")
        self.process_manager.execute_command(command_list, working_dir)
        for dock in self.findChildren(QDockWidget):
            if dock.objectName() == "TerminalDockWidget": dock.setVisible(True); dock.raise_(); self.terminal.setFocus(); break
        self.statusBar().showMessage(f"Executing {file_path_obj.name}...", 3000)

    def _on_process_output(self, output: str):
        if self.terminal: self.terminal.display_area.insertPlainText(output); self.terminal.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _on_process_finished(self, exit_code: int):
        msg = f"Process finished with exit code: {exit_code}"; self.statusBar().showMessage(msg, 5000)
        if self.terminal:
            prefix = "\n" if self.terminal.display_area.toPlainText() and not self.terminal.display_area.toPlainText().endswith("\n") else ""
            self.terminal.display_area.appendPlainText(f"{prefix}[{msg}]\n"); self.terminal.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _on_process_error(self, error_message: str):
        self.statusBar().showMessage(f"Process Error: {error_message}", 5000)
        if self.terminal:
            prefix = "\n" if self.terminal.display_area.toPlainText() and not self.terminal.display_area.toPlainText().endswith("\n") else ""
            self.terminal.display_area.appendPlainText(f"{prefix}[Process Error: {error_message}]\n"); self.terminal.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _on_editor_text_changed_generic(self, editor_instance):
       if isinstance(editor_instance, CodeEditor):
           self.file_manager.update_dirty_status(editor_instance, True)
           tab_index = self.tab_widget.indexOf(editor_instance)
           if tab_index != -1:
               current_tab_text = self.tab_widget.tabText(tab_index)
               if not current_tab_text.endswith("*"):
                   self.tab_widget.setTabText(tab_index, current_tab_text + "*")

    def _on_editor_breakpoint_toggled(self, line_number: int):
        sender_widget = self.sender()
        editor_widget = None
        if isinstance(sender_widget, CodeEditor):
            editor_widget = sender_widget
        # This logic might need to be more robust if the sender is the gutter itself
        # and not the CodeEditor instance directly.
        # Assuming CodeEditor proxies the signal and is the sender.

        if not isinstance(editor_widget, CodeEditor):
            current_tab_widget = self.tab_widget.currentWidget()
            if isinstance(current_tab_widget, CodeEditor):
                editor_widget = current_tab_widget
            else:
                self.statusBar().showMessage("Error identifying editor for breakpoint.", 3000)
                return

        if editor_widget:
            file_path_str = self.file_manager.get_file_path(editor_widget)
            if not file_path_str:
                self.statusBar().showMessage("Save file to set breakpoints.", 2000)
                return

            file_bps = self.breakpoints_map.setdefault(file_path_str, {})
            if line_number in file_bps:
                del file_bps[line_number]
                print(f"UI: Breakpoint removed at {file_path_str}:{line_number}")
            else:
                file_bps[line_number] = {'line': line_number}
                print(f"UI: Breakpoint added at {file_path_str}:{line_number}")
            
            if hasattr(editor_widget, 'gutter') and hasattr(editor_widget.gutter, 'update_breakpoints_display'):
                 editor_widget.gutter.update_breakpoints_display(set(file_bps.keys()))
            elif hasattr(editor_widget, 'update_gutter_breakpoints'):
                 editor_widget.update_gutter_breakpoints(set(file_bps.keys()))

            # Update new breakpoints_list
            if hasattr(self, 'breakpoints_list'):
                self.breakpoints_list.clear()
                for f_path, lines_dict in self.breakpoints_map.items():
                    for line_num_key in lines_dict:
                        self.breakpoints_list.addItem(f"{Path(f_path).name}:{line_num_key}")

            if self.debug_manager and self.debug_manager.is_debugging:
                dap_bps_for_file = list(file_bps.values())
                self.debug_manager.dap_set_breakpoints(file_path_str, dap_bps_for_file)
            
            self.statusBar().showMessage(f"Breakpoint toggled at {Path(file_path_str).name}:{line_number}.", 2000)
        else:
            print(f"Warning: _on_editor_breakpoint_toggled could not resolve CodeEditor instance. Sender: {self.sender()}")

    def _is_signal_connected(self, signal_instance, slot_method):
        return False # Placeholder, assume not connected to simplify logic for now

    def load_session(self):
        self.statusBar().showMessage("Loading session...", 0)
        state = self.session_manager.load_session()
        if not state:
            self.statusBar().showMessage("No previous session found or error loading session.", 3000)
            # self._on_new_file_action() # Replaced by welcome page logic below
            # No previous session or error, and no tabs are open, show welcome page.
            # This is handled by the check in __init__ after load_session completes.
            return

        try:
            if 'window_geometry' in state:
                self.restoreGeometry(QByteArray.fromHex(state['window_geometry'].encode()))
            if 'window_state' in state:
                self.restoreState(QByteArray.fromHex(state['window_state'].encode()))

            open_files = state.get('open_files', [])
            active_file_path = state.get('active_file', None)

            if open_files:
                for path_str in open_files:
                    if Path(path_str).is_file():
                        self.file_manager.open_file(path_str) # This eventually calls _on_file_content_loaded
                    else:
                        self.statusBar().showMessage(f"Session: File not found '{path_str}', removed from session.", 3000)
            
                if active_file_path: # Check if active_file_path was in open_files and successfully opened
                    for i in range(self.tab_widget.count()):
                        editor_widget = self.tab_widget.widget(i)
                        if editor_widget and self.file_manager.get_file_path(editor_widget) == active_file_path:
                            self.tab_widget.setCurrentIndex(i)
                            break
                if self.tab_widget.count() > 0 : # Only show if files were actually opened
                    self.statusBar().showMessage("Session loaded successfully.", 3000)
            # If open_files is empty, or all files failed to load, tab_widget.count() will be 0.
            # The logic in __init__ will then call _show_welcome_page().

        except Exception as e:
            self.statusBar().showMessage(f"Error restoring session: {e}", 5000)
            QMessageBox.warning(self, "Session Load Error", f"Could not fully restore session: {e}")
            # If session loading fails catastrophically, __init__ will call _show_welcome_page if no tabs.


    def save_session(self):
        if not self.session_manager:
            print("Error: SessionManager not initialized.")
            self.statusBar().showMessage("Error: SessionManager not available. Cannot save session.", 5000)
            return
        state = {}
        state['window_geometry'] = self.saveGeometry().toHex().data().decode('utf-8')
        state['window_state'] = self.saveState().toHex().data().decode('utf-8')
        open_files_paths = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, CodeEditor):
                file_path = self.file_manager.get_file_path(widget)
                if file_path:
                    open_files_paths.append(file_path)
        state['open_files'] = open_files_paths
        active_widget = self.tab_widget.currentWidget()
        active_file_path = None
        if isinstance(active_widget, CodeEditor):
            path_of_active = self.file_manager.get_file_path(active_widget)
            if path_of_active:
                active_file_path = path_of_active
        state['active_file'] = active_file_path
        try:
            self.session_manager.save_session(state)
            self.statusBar().showMessage("Session saved.", 2000)
        except Exception as e:
            print(f"Error during session save: {e}")
            self.statusBar().showMessage(f"Error saving session: {e}", 5000)

    def closeEvent(self, event: QCloseEvent):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, CodeEditor) and self.file_manager.is_dirty(widget):
                self.tab_widget.setCurrentIndex(i)
                file_path_str = self.file_manager.get_file_path(widget)
                tab_text = self.tab_widget.tabText(i)
                filename_for_prompt = Path(file_path_str).name if file_path_str else tab_text
                reply = QMessageBox.question(self,
                                           'Unsaved Changes',
                                           f"'{filename_for_prompt}' has unsaved changes. Save before exiting?",
                                           QMessageBox.StandardButton.Save |
                                           QMessageBox.StandardButton.Discard |
                                           QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Save:
                    if file_path_str:
                        self.file_manager.save_file(widget, file_path_str)
                        if self.file_manager.is_dirty(widget):
                            event.ignore()
                            self.statusBar().showMessage(f"Save failed for '{filename_for_prompt}'. Close cancelled.", 3000)
                            return
                    else:
                        self._on_save_as_file_action()
                        if self.file_manager.is_dirty(widget):
                            event.ignore()
                            self.statusBar().showMessage(f"File '{filename_for_prompt}' not saved. Close cancelled.", 3000)
                            return
                elif reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    self.statusBar().showMessage("Close cancelled by user.", 3000)
                    return
        
        self.statusBar().showMessage("Saving session before exit...", 2000)
        try:
            self.save_session()
        except Exception as e:
            print(f"Error saving session during application close: {e}")
            self.statusBar().showMessage(f"Error saving session: {e}. Proceeding with exit.", 3000)

        if self.terminal and self.terminal.shell_process and \
           self.terminal.shell_process.state() != QProcess.ProcessState.NotRunning:
            try:
                self.terminal.shell_process.terminate()
                if not self.terminal.shell_process.waitForFinished(1000):
                    print("Terminal shell process did not finish gracefully, killing.")
                    self.terminal.shell_process.kill()
                    self.terminal.shell_process.waitForFinished(500)
            except Exception as e:
                print(f"Error trying to close/terminate terminal shell process: {e}")
        
        event.accept()

    # --- Helper for UI State ---
    def _update_debug_action_states(self, is_debugging_active: bool, is_paused: bool = False):
        self.start_debug_action.setEnabled(not is_debugging_active)
        self.run_action.setEnabled(not is_debugging_active)
        self.stop_debug_action.setEnabled(is_debugging_active)
        self.continue_action.setEnabled(is_debugging_active and is_paused)
        self.step_over_action.setEnabled(is_debugging_active and is_paused)
        self.step_in_action.setEnabled(is_debugging_active and is_paused)
        self.step_out_action.setEnabled(is_debugging_active and is_paused)

    # --- Slots for DebugManager -> UI ---
    def _on_dap_initialized(self):
        self.statusBar().showMessage("Debug Adapter Protocol initialized.", 3000)
        if hasattr(self, '_program_to_launch_after_dap_init') and self._program_to_launch_after_dap_init:
            program_path = self._program_to_launch_after_dap_init
            self._program_to_launch_after_dap_init = None
            for filepath, bp_lines_dict in self.breakpoints_map.items():
                if bp_lines_dict:
                    bps_to_send = list(bp_lines_dict.values())
                    print(f"Pre-launch: Sending stored breakpoints for {filepath}: {bps_to_send}")
                    self.debug_manager.dap_set_breakpoints(filepath, bps_to_send)
            launch_args = {"stopOnEntry": True}
            print(f"DAP initialized. Launching program: {program_path}")
            self.debug_manager.dap_launch(program_path=program_path, launch_args=launch_args)
        else:
            self.statusBar().showMessage("DAP initialized, ready to launch/attach.", 3000)
            self._update_debug_action_states(is_debugging_active=True, is_paused=False)

    def _on_dap_launched(self):
        self.statusBar().showMessage("Debug session launched. Requesting threads...", 3000)
        self._update_debug_action_states(is_debugging_active=True, is_paused=False)
        self.debug_manager.dap_threads()

    def _on_dap_terminated(self):
        self.statusBar().showMessage("Debug session terminated.", 5000)
        self.current_thread_id = None
        self._program_to_launch_after_dap_init = None
        self.scope_item_map.clear()
        self._update_debug_action_states(is_debugging_active=False, is_paused=False)
        
        if hasattr(self, 'debugger_dock'):
            self.debugger_dock.setVisible(False)
        if hasattr(self, 'call_stack_list'):
            self.call_stack_list.clear()
        if hasattr(self, 'variables_tree'):
            self.variables_tree.clear()
        if hasattr(self, 'watch_tree'):
            self.watch_tree.clear()
        # Breakpoints list is not cleared here, as it reflects user settings, not session state.
        # However, the old code did not clear breakpoints_view here either.

    def _on_breakpoint_hit(self, filepath: str, line: int, thread_id: int, frame_details: dict):
        self.statusBar().showMessage(f"Paused: {frame_details.get('reason', 'breakpoint')} at {Path(filepath).name}:{line}, Thread: {thread_id}", 0)
        self.current_thread_id = thread_id
        self.scope_item_map.clear() # Clear for new context
        if hasattr(self, 'variables_tree'): # Clear previous variables before new scopes arrive
            self.variables_tree.clear()
        self._update_debug_action_states(is_debugging_active=True, is_paused=True)
        
        if hasattr(self, 'debugger_dock'):
            self.debugger_dock.setVisible(True)
            self.debugger_dock.raise_()

        found_tab = False
        if filepath and filepath != "UnknownFile":
            for i in range(self.tab_widget.count()):
                editor_widget = self.tab_widget.widget(i)
                if isinstance(editor_widget, CodeEditor) and self.file_manager.get_file_path(editor_widget) == filepath:
                    self.tab_widget.setCurrentWidget(editor_widget)
                    block = editor_widget.document().findBlockByNumber(line - 1)
                    if block.isValid():
                        cursor = editor_widget.textCursor()
                        cursor.setPosition(block.position())
                        editor_widget.setTextCursor(cursor)
                    editor_widget.setFocus()
                    found_tab = True
                    break
            if not found_tab:
                print(f"Breakpoint hit in file not open: {filepath}:{line}. Consider opening.")

        self.debug_manager.dap_threads()
        self.debug_manager.dap_stack_trace(thread_id)

    def _on_threads_received(self, threads_list: list):
        # This method might need to update a specific "Threads" view if one was added.
        # For now, the call stack is often tied to a selected thread.
        # If call_stack_list is meant to show threads first, this needs adjustment.
        # Assuming call_stack_list shows stack frames of the *current* or *first* thread.
        # The current design implies dap_stack_trace is called for a specific (current) thread_id.
        print(f"Threads received (info): {threads_list}")
        # If you had a dedicated QListWidget for threads:
        # self.threads_list_widget.clear()
        # for t in threads_list:
        #     self.threads_list_widget.addItem(f"Thread {t.get('id')} : {t.get('name', 'Unnamed')}")

    def _on_stack_frames_received(self, frames_list: list):
        if hasattr(self, 'call_stack_list'):
            self.call_stack_list.clear()
            for frame in frames_list:
                name = frame.get('name', 'frame')
                source_data = frame.get('source', {})
                file_name_from_source = source_data.get('name', Path(source_data.get('path', 'Unknown')).name)
                line = frame.get('line', 0)
                frame_id = frame.get('id') # This ID is crucial for fetching scopes
                item_text = f"{name} ({file_name_from_source}:{line}) [id:{frame_id}]"
                list_item = QListWidgetItem(item_text, self.call_stack_list)
                list_item.setData(Qt.ItemDataRole.UserRole, frame_id) # Store frame_id for potential use

            if frames_list and self.debug_manager.is_debugging:
                top_frame_id = frames_list[0].get('id')
                if top_frame_id is not None:
                    print(f"Top stack frame ID: {top_frame_id}. Requesting scopes.")
                    self.debug_manager.dap_scopes(top_frame_id)
                else: # No frames or no ID, clear variables view
                    if hasattr(self, 'variables_tree'):
                        self.variables_tree.clear()
                        self.scope_item_map.clear()
        else:
            print(f"Stack frames received, but call_stack_list not ready.")

    def _on_scopes_received(self, scopes_list: list):
        if hasattr(self, 'variables_tree'):
            # self.variables_tree.clear() # Clearing here would remove scopes before children are added if async.
                                        # Clearing is now done in _on_breakpoint_hit.
            # self.scope_item_map.clear() # Also moved to _on_breakpoint_hit

            # Check if the tree is empty (first time after a pause or clear)
            # This is to avoid adding duplicate scopes if the signal is somehow emitted multiple times
            # without an intervening _on_breakpoint_hit.
            if self.variables_tree.topLevelItemCount() == 0:
                for scope in scopes_list:
                    scope_name = scope.get('name', 'Scope')
                    variables_ref = scope.get('variablesReference')
                    scope_item = QTreeWidgetItem(self.variables_tree, [scope_name, "", "<Scope>"])
                    scope_item.setData(0, Qt.ItemDataRole.UserRole, variables_ref) # Store ref for expansion/identification
                    if variables_ref > 0:
                        self.scope_item_map[variables_ref] = scope_item # Map ref to item for _on_variables_received
                        self.debug_manager.dap_variables(variables_ref)
            else:
                # If tree is not empty, it implies scopes are already there.
                # We might need to update them or handle this case more gracefully.
                # For now, assume _on_breakpoint_hit correctly clears for a new context.
                print("Variables tree not empty in _on_scopes_received, potential re-entry or stale state.")


        else:
             print(f"Scopes received, but variables_tree not ready.")

    def _on_variables_received(self, variables_list: list, original_request_ref: int = 0): # original_request_ref is ideal
        print(f"Variables received for ref {original_request_ref} (simplified display): {variables_list}")
        if hasattr(self, 'variables_tree'):
            parent_item = self.scope_item_map.get(original_request_ref)

            if not parent_item: # Fallback heuristic if original_request_ref was not available or mapping failed
                # Try to find a suitable parent: last top-level item with no children and matching ref if possible
                # This is imperfect.
                for i in range(self.variables_tree.topLevelItemCount() -1, -1, -1):
                    item = self.variables_tree.topLevelItem(i)
                    stored_ref = item.data(0, Qt.ItemDataRole.UserRole)
                    if stored_ref == original_request_ref or (original_request_ref == 0 and stored_ref > 0 and item.childCount() == 0) : # original_request_ref=0 means we don't know
                        parent_item = item
                        break
                if not parent_item:
                     parent_item = self.variables_tree.invisibleRootItem()


            # Clear existing children of this specific scope item before adding new ones
            # Take a copy of children list before iterating for removal
            children = []
            for i in range(parent_item.childCount()):
                children.append(parent_item.child(i))
            for child in children:
                parent_item.removeChild(child)

            for var_info in variables_list:
                name = var_info.get('name', 'N/A')
                value = str(var_info.get('value', '')) # Ensure value is string
                var_type = var_info.get('type', '')
                var_ref = var_info.get('variablesReference', 0)

                var_item = QTreeWidgetItem(parent_item, [name, value, var_type])
                if var_ref > 0:
                    var_item.setData(0, Qt.ItemDataRole.UserRole, var_ref) # For expandable variables
                    self.scope_item_map[var_ref] = var_item # So nested variables can find their parent
                    # Potentially, could auto-expand or fetch children here if desired:
                    # self.debug_manager.dap_variables(var_ref)
            if parent_item is not self.variables_tree.invisibleRootItem():
                 parent_item.setExpanded(True)
        else:
            print(f"Variables received, but variables_tree not ready.")

    def _on_dap_output(self, category: str, text: str):
        if self.terminal:
            for dock in self.findChildren(QDockWidget):
                if dock.objectName() == "TerminalDockWidget":
                    dock.setVisible(True); dock.raise_(); break
            self.terminal.display_area.appendPlainText(f"[{category.upper()}_DAP] {text.strip()}\n")
            self.terminal.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _on_dap_error(self, message: str):
        QMessageBox.critical(self, "DAP Error", message)
        self.statusBar().showMessage(f"DAP Error: {message}", 5000)
        if self.terminal:
            self.terminal.display_area.appendPlainText(f"[DAP SYSTEM ERROR] {message.strip()}\n")
            self.terminal.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _on_start_debug_action(self):
        current_editor = self.tab_widget.currentWidget()
        if not isinstance(current_editor, CodeEditor):
            self.statusBar().showMessage("No active code editor selected for debugging.", 3000)
            return
        file_path_str = self.file_manager.get_file_path(current_editor)
        if not file_path_str:
            QMessageBox.warning(self, "Cannot Debug", "Please save the file before starting a debug session.")
            return

        self._program_to_launch_after_dap_init = file_path_str
        self.debug_manager.start_dap_server(["python", "-m", "debugpy.adapter"], os.path.dirname(file_path_str))
        self.statusBar().showMessage(f"Starting debug session for {Path(file_path_str).name}...", 3000)
        self._update_debug_action_states(True, False)

    def _on_continue_action(self):
        if self.debug_manager.is_debugging and self.current_thread_id is not None:
            self.debug_manager.dap_continue(self.current_thread_id)
            self.statusBar().showMessage("Continuing execution...", 2000)
            self._update_debug_action_states(True, False)

    def _on_step_over_action(self):
        if self.debug_manager.is_debugging and self.current_thread_id is not None:
            self.debug_manager.dap_next(self.current_thread_id)
            self.statusBar().showMessage("Stepping over...", 2000)
            self._update_debug_action_states(True, False)

    def _on_step_in_action(self):
        if self.debug_manager.is_debugging and self.current_thread_id is not None:
            self.debug_manager.dap_step_in(self.current_thread_id)
            self.statusBar().showMessage("Stepping in...", 2000)
            self._update_debug_action_states(True, False)

    def _on_step_out_action(self):
        if self.debug_manager.is_debugging and self.current_thread_id is not None:
            self.debug_manager.dap_step_out(self.current_thread_id)
            self.statusBar().showMessage("Stepping out...", 2000)
            self._update_debug_action_states(True, False)

    def _on_stop_debug_action(self):
        if self.debug_manager.is_debugging:
            self.debug_manager.dap_disconnect()
            self.statusBar().showMessage("Stopping debug session...", 3000)
            self._update_debug_action_states(False, False)
        else:
            self.statusBar().showMessage("No active debug session to stop.", 2000)

    def _on_toggle_breakpoint_action(self):
        current_editor = self.tab_widget.currentWidget()
        if isinstance(current_editor, CodeEditor):
            current_line = current_editor.textCursor().blockNumber() + 1
            current_editor.toggle_breakpoint(current_line)
        else:
            self.statusBar().showMessage("No active code editor to toggle breakpoint.", 3000)

    def _is_signal_connected(self, signal, slot):
        try:
            # PySide6 does not expose a direct way to check if a specific slot is connected
            # to a signal. This is a workaround that might not be perfectly reliable
            # across all PySide6 versions or complex scenarios.
            # It attempts to connect the slot again; if it's already connected,
            # it might return False or raise an error depending on the signal type.
            # A more robust solution might involve tracking connections manually.
            signal.connect(slot)
            signal.disconnect(slot) # Disconnect if it was successfully connected (meaning it wasn't before)
            return False
        except RuntimeError:
            # If connecting raises a RuntimeError, it often means it's already connected
            return True
        except Exception:
            # Catch other potential exceptions
            return False

    def _close_all_tabs(self) -> bool:
        """Closes all open tabs, prompting for save if necessary. Returns True if all tabs closed, False otherwise."""
        while self.tab_widget.count() > 0:
            current_tab_widget_count = self.tab_widget.count()
            # _on_tab_close_requested will remove the tab if close is not cancelled
            self._on_tab_close_requested(0) # Always try to close the first tab
            if self.tab_widget.count() == current_tab_widget_count:
                # User cancelled the close operation for a tab
                return False
        return True


    def _show_welcome_page(self):
        # This check is important to avoid issues if called when tabs are still open
        if self.tab_widget.count() > 0:
            # If for some reason this is called with tabs open, switch to tabs and log warning
            if self.centralWidget() != self.tab_widget:
                 self.setCentralWidget(self.tab_widget)
            print("Warning: _show_welcome_page called while tabs are open. Aborting welcome page display.")
            return

        if not hasattr(self, 'welcome_page') or self.welcome_page is None:
            try:
                # recent_folders = self.session_manager.get_recent_folders() # TODO: Implement in SessionManager
                recent_folders = [] # Placeholder for now
            except AttributeError: # Fallback if SessionManager method doesn't exist yet
                recent_folders = []
                print("Warning: SessionManager.get_recent_folders() not found. Using empty list for recent folders.")

            self.welcome_page = WelcomePage(recent_folders)
            self.welcome_page.new_file_requested.connect(self._on_new_file_action)
            self.welcome_page.open_file_requested.connect(self._on_open_file_action)
            self.welcome_page.open_folder_requested.connect(self._on_open_folder_action)
            self.welcome_page.recent_path_selected.connect(self._on_recent_folder_selected)
            # self.welcome_page.join_session_requested.connect(...) # TODO: Implement join session

        self.setCentralWidget(self.welcome_page)
        self.welcome_page.setVisible(True)

        # Hide toolbars and docks that are not relevant for the welcome page
        if hasattr(self, 'debugger_dock'):
            self.debugger_dock.setVisible(False)
        # self.file_toolbar.setVisible(False) # Decided to keep file ops for now
        # self.execution_toolbar.setVisible(False) # Keep for consistency or if user opens folder
        # self.debug_toolbar.setVisible(False) # Keep for consistency

    def _on_back_to_welcome_requested(self):
        if self._close_all_tabs():
            self._show_welcome_page()

    def _on_open_folder_action(self):
        start_dir = QDir.homePath()
        try:
            # recent_folders = self.session_manager.get_recent_folders() # TODO
            # if recent_folders and len(recent_folders) > 0: start_dir = recent_folders[0]
            pass # Using QDir.homePath() for now
        except AttributeError:
            print("Warning: SessionManager.get_recent_folders() not found for _on_open_folder_action.")

        dir_path = QFileDialog.getExistingDirectory(self, "Open Folder", start_dir)
        if dir_path:
            if hasattr(self, 'file_explorer'):
                self.file_explorer.set_root_path(dir_path)
            try:
                # self.session_manager.add_recent_folder(dir_path) # TODO: Implement in SessionManager
                pass
            except AttributeError:
                print(f"Warning: SessionManager.add_recent_folder() not found for {dir_path}.")

            if self.centralWidget() == self.welcome_page and self.welcome_page is not None:
                self.setCentralWidget(self.tab_widget) # Switch to tab view (even if empty)
                self.welcome_page.setVisible(False)
                # Make relevant toolbars visible
                self.file_toolbar.setVisible(True)
                self.execution_toolbar.setVisible(True)
                self.debug_toolbar.setVisible(True)
            self.statusBar().showMessage(f"Opened folder: {dir_path}", 3000)


    def _on_recent_folder_selected(self, path: str):
        if Path(path).is_dir():
            if hasattr(self, 'file_explorer'):
                self.file_explorer.set_root_path(path)
            try:
                # self.session_manager.add_recent_folder(path) # TODO: Implement in SessionManager
                pass
            except AttributeError:
                 print(f"Warning: SessionManager.add_recent_folder() not found for {path}.")


            if self.centralWidget() == self.welcome_page and self.welcome_page is not None:
                self.setCentralWidget(self.tab_widget) # Switch to tab view
                self.welcome_page.setVisible(False)
                # Make relevant toolbars visible
                self.file_toolbar.setVisible(True)
                self.execution_toolbar.setVisible(True)
                self.debug_toolbar.setVisible(True)
            self.statusBar().showMessage(f"Opened recent folder: {path}", 3000)
        else:
            QMessageBox.warning(self, "Folder Not Found", f"The folder '{path}' could not be found.")
            # TODO: Consider removing it from recent list via session_manager


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    # print("MainWindow integration with CodeEditor for dirty status and breakpoints updated.") # Old message
    print("Aether Editor started.")
    sys.exit(app.exec())
