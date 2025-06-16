import sys
import os
import platform
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QDockWidget, QToolBar, QPlainTextEdit,
    QListView, QMessageBox, QFileDialog, QTreeView
)
from PySide6.QtCore import Qt, QSize, QByteArray, QProcess, QStringListModel
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

        self._define_actions()

        self.session_manager = SessionManager()
        self.file_manager = FileManager()
        self.process_manager = ProcessManager()
        self.debug_manager = DebugManager(self)

        self._setup_ui()
        self._setup_menus()
        self._setup_connections()

        self.load_session()
        if not self.statusBar().currentMessage():
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
        self.run_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        self.run_action.setStatusTip("Run the current file")

        self.start_debug_action = QAction("Start &Debugging", self)
        self.start_debug_action.setShortcut(QKeySequence(Qt.Key.Key_F6))
        self.start_debug_action.setStatusTip("Start a debug session for the current file")

        self.continue_action = QAction("&Continue", self)
        self.continue_action.setShortcut(QKeySequence(Qt.Key.Key_F8))
        self.continue_action.setStatusTip("Continue execution")
        self.continue_action.setEnabled(False)

        self.step_over_action = QAction("Step &Over", self)
        self.step_over_action.setShortcut(QKeySequence(Qt.Key.Key_F10))
        self.step_over_action.setStatusTip("Step over the current line")
        self.step_over_action.setEnabled(False)

        self.step_in_action = QAction("Step &In", self)
        self.step_in_action.setShortcut(QKeySequence(Qt.Key.Key_F11))
        self.step_in_action.setStatusTip("Step into the current function call")
        self.step_in_action.setEnabled(False)

        self.step_out_action = QAction("Step O&ut", self)
        self.step_out_action.setShortcut(QKeySequence(Qt.Key.Key_ShiftModifier | Qt.Key.Key_F11))
        self.step_out_action.setStatusTip("Step out of the current function")
        self.step_out_action.setEnabled(False)

        self.stop_debug_action = QAction("S&top Debugging", self)
        self.stop_debug_action.setShortcut(QKeySequence(Qt.Key.Key_ShiftModifier | Qt.Key.Key_F5))
        self.stop_debug_action.setStatusTip("Stop the current debug session")
        self.stop_debug_action.setEnabled(False)
        
        self.toggle_breakpoint_action = QAction("&Toggle Breakpoint", self)
        self.toggle_breakpoint_action.setShortcut(QKeySequence(Qt.Key.Key_F9))
        self.toggle_breakpoint_action.setStatusTip("Toggle a breakpoint on the current line")

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

        file_explorer_dock = QDockWidget("File Explorer", self)
        file_explorer_dock.setObjectName("FileExplorerDockWidget")
        placeholder_file_list = QListView()
        file_explorer_dock.setWidget(placeholder_file_list)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, file_explorer_dock)

        self.file_toolbar = QToolBar("File Toolbar")
        self.file_toolbar.setObjectName("FileToolBar")
        self.file_toolbar.addAction(self.new_file_action)
        self.file_toolbar.addAction(self.open_file_action)
        self.file_toolbar.addAction(self.save_file_action)
        self.file_toolbar.addAction(self.save_as_file_action)
        self.addToolBar(self.file_toolbar)
        self.file_toolbar.setMovable(True)
        self.file_toolbar.setFloatable(True)

        self.run_toolbar = QToolBar("Run Toolbar")
        self.run_toolbar.setObjectName("RunToolBar")
        self.run_toolbar.addAction(self.run_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.run_toolbar)
        self.run_toolbar.setMovable(True)
        self.run_toolbar.setFloatable(True)

        self.debug_toolbar = QToolBar("Debug Toolbar")
        self.debug_toolbar.setObjectName("DebugToolBar")
        self.debug_toolbar.addAction(self.start_debug_action)
        self.debug_toolbar.addAction(self.continue_action)
        self.debug_toolbar.addAction(self.step_over_action)
        self.debug_toolbar.addAction(self.step_in_action)
        self.debug_toolbar.addAction(self.step_out_action)
        self.debug_toolbar.addAction(self.stop_debug_action)
        self.debug_toolbar.addAction(self.toggle_breakpoint_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.debug_toolbar)
        self.debug_toolbar.setMovable(True)
        self.debug_toolbar.setFloatable(True)
        self.debug_toolbar.setVisible(True)

        self.call_stack_dock = QDockWidget("Call Stack", self)
        self.call_stack_dock.setObjectName("CallStackDockWidget")
        self.call_stack_view = QListView()
        self.call_stack_view.setModel(QStringListModel([]))
        self.call_stack_dock.setWidget(self.call_stack_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.call_stack_dock)

        self.variables_dock = QDockWidget("Variables", self)
        self.variables_dock.setObjectName("VariablesDockWidget")
        self.variables_view = QTreeView()
        model_vars = QStandardItemModel()
        model_vars.setHorizontalHeaderLabels(["Name", "Value", "Type"])
        self.variables_view.setModel(model_vars)
        self.variables_dock.setWidget(self.variables_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.variables_dock)

        self.watch_dock = QDockWidget("Watch", self)
        self.watch_dock.setObjectName("WatchDockWidget")
        self.watch_view = QTreeView()
        self.watch_view.setModel(QStandardItemModel())
        self.watch_dock.setWidget(self.watch_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.watch_dock)
        
        self.breakpoints_dock = QDockWidget("Breakpoints", self)
        self.breakpoints_dock.setObjectName("BreakpointsDockWidget")
        self.breakpoints_view = QListView()
        self.breakpoints_view.setModel(QStringListModel([]))
        self.breakpoints_dock.setWidget(self.breakpoints_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.breakpoints_dock)

        self.tabifyDockWidget(self.call_stack_dock, self.variables_dock)
        self.tabifyDockWidget(self.variables_dock, self.watch_dock)
        self.tabifyDockWidget(self.watch_dock, self.breakpoints_dock)

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

    def _on_new_file_action(self):
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
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open File", "",
            "All Files (*);;Text Files (*.txt);;Python Files (*.py)"
        )
        if file_paths:
            for path_str in file_paths:
                if path_str:
                    self.file_manager.open_file(path_str)

    def _on_file_content_loaded(self, path: str, content: str):
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
                        return
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        self.file_manager.untrack_tab(widget_to_close)
        self.tab_widget.removeTab(index)

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

            if hasattr(self, 'breakpoints_view') and self.breakpoints_view.model():
                if isinstance(self.breakpoints_view.model(), QStringListModel):
                    bp_list_str = []
                    for f_path, lines_dict in self.breakpoints_map.items():
                        for line_num_key in lines_dict:
                            bp_list_str.append(f"{Path(f_path).name}:{line_num_key}")
                    self.breakpoints_view.model().setStringList(bp_list_str)

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
            if self.tab_widget.count() == 0:
                self._on_new_file_action()
            return

        try:
            if 'window_geometry' in state:
                self.restoreGeometry(QByteArray.fromHex(state['window_geometry'].encode()))
            if 'window_state' in state:
                self.restoreState(QByteArray.fromHex(state['window_state'].encode()))

            open_files = state.get('open_files', [])
            active_file_path = state.get('active_file', None)
            opened_paths_for_active_check = []

            if open_files:
                for path_str in open_files:
                    if Path(path_str).is_file():
                        self.file_manager.open_file(path_str)
                        opened_paths_for_active_check.append(path_str)
                    else:
                        self.statusBar().showMessage(f"Session: File not found '{path_str}', removed from session.", 3000)
            
            if active_file_path and active_file_path in opened_paths_for_active_check:
                for i in range(self.tab_widget.count()):
                    editor_widget = self.tab_widget.widget(i)
                    if editor_widget and self.file_manager.get_file_path(editor_widget) == active_file_path:
                        self.tab_widget.setCurrentIndex(i)
                        break
            elif self.tab_widget.count() == 0:
                 self._on_new_file_action()
            self.statusBar().showMessage("Session loaded successfully.", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Error restoring session: {e}", 5000)
            QMessageBox.warning(self, "Session Load Error", f"Could not fully restore session: {e}")
            if self.tab_widget.count() == 0:
                self._on_new_file_action()

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
        self._update_debug_action_states(is_debugging_active=False, is_paused=False)
        
        if hasattr(self, 'call_stack_view') and isinstance(self.call_stack_view.model(), QStringListModel):
            self.call_stack_view.model().setStringList([])
        if hasattr(self, 'variables_view') and isinstance(self.variables_view.model(), QStandardItemModel):
            self.variables_view.model().removeRows(0, self.variables_view.model().rowCount())
        
        for dock_name in ["call_stack_dock", "variables_dock", "watch_dock", "breakpoints_dock"]:
            if hasattr(self, dock_name):
                getattr(self, dock_name).hide()

    def _on_breakpoint_hit(self, filepath: str, line: int, thread_id: int, frame_details: dict):
        self.statusBar().showMessage(f"Paused: {frame_details.get('reason', 'breakpoint')} at {Path(filepath).name}:{line}, Thread: {thread_id}", 0)
        self.current_thread_id = thread_id
        self._update_debug_action_states(is_debugging_active=True, is_paused=True)
        
        for dock_name in ["call_stack_dock", "variables_dock", "watch_dock", "breakpoints_dock"]:
            if hasattr(self, dock_name):
                getattr(self, dock_name).setVisible(True); getattr(self, dock_name).raise_()

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
        if hasattr(self, 'call_stack_view') and isinstance(self.call_stack_view.model(), QStringListModel):
            model = self.call_stack_view.model()
            thread_items = [f"Thread {t.get('id')} : {t.get('name', 'Unnamed')}" for t in threads_list]
            model.setStringList(thread_items)
        else:
            print(f"Threads received, but call_stack_view or its QStringListModel not ready/available.")

    def _on_stack_frames_received(self, frames_list: list):
        if hasattr(self, 'call_stack_view') and isinstance(self.call_stack_view.model(), QStringListModel):
            model = self.call_stack_view.model()
            frame_strings = []
            for frame in frames_list:
                name = frame.get('name', 'frame')
                source_data = frame.get('source', {})
                file_name_from_source = source_data.get('name', Path(source_data.get('path', '')).name)
                line = frame.get('line', 0)
                frame_id = frame.get('id')
                frame_strings.append(f"{name} ({file_name_from_source}:{line}) [id:{frame_id}]")
            model.setStringList(frame_strings)

            if frames_list and self.debug_manager.is_debugging:
                top_frame_id = frames_list[0].get('id')
                if top_frame_id is not None:
                    print(f"Top stack frame ID: {top_frame_id}. Requesting scopes.")
                    self.debug_manager.dap_scopes(top_frame_id)
                else:
                    if hasattr(self, 'variables_view') and isinstance(self.variables_view.model(), QStandardItemModel):
                        self.variables_view.model().removeRows(0, self.variables_view.model().rowCount())
        else:
            print(f"Stack frames received, but call_stack_view or its QStringListModel not ready.")

    def _on_scopes_received(self, scopes_list: list):
        if hasattr(self, 'variables_view') and isinstance(self.variables_view.model(), QStandardItemModel):
            model = self.variables_view.model()
            model.removeRows(0, model.rowCount())
            model.setHorizontalHeaderLabels(["Name", "Value", "Type"])
            root_item = model.invisibleRootItem()
            for scope in scopes_list:
                scope_name = scope.get('name', 'Scope')
                variables_ref = scope.get('variablesReference')
                name_col_item = QStandardItem(scope_name)
                name_col_item.setEditable(False)
                name_col_item.setData(variables_ref, Qt.ItemDataRole.UserRole)
                value_col_item = QStandardItem("")
                value_col_item.setEditable(False)
                type_col_item = QStandardItem("<Scope>")
                type_col_item.setEditable(False)
                root_item.appendRow([name_col_item, value_col_item, type_col_item])
                if variables_ref > 0:
                    self.debug_manager.dap_variables(variables_ref)
        else:
             print(f"Scopes received, but variables_view or its QStandardItemModel not ready.")

    def _on_variables_received(self, variables_list: list):
        print(f"Variables received (simplified display): {variables_list}")
        if hasattr(self, 'variables_view') and isinstance(self.variables_view.model(), QStandardItemModel):
            model = self.variables_view.model()
            parent_item_for_vars = model.invisibleRootItem()
            for var_info in variables_list:
                name = var_info.get('name', 'N/A')
                value = var_info.get('value', '')
                var_type = var_info.get('type', '')
                var_ref = var_info.get('variablesReference', 0)
                name_item = QStandardItem(name)
                name_item.setEditable(False)
                value_item = QStandardItem(value)
                value_item.setEditable(False)
                type_item = QStandardItem(var_type)
                type_item.setEditable(False)
                if var_ref > 0:
                    name_item.setData(var_ref, Qt.ItemDataRole.UserRole)
                parent_item_for_vars.appendRow([name_item, value_item, type_item])
        else:
            print(f"Variables received, but variables_view or its QStandardItemModel not ready.")

    def _on_dap_output(self, category: str, text: str):
        if self.terminal:
            for dock in self.findChildren(QDockWidget):
                if dock.objectName() == "TerminalDockWidget":
                    dock.setVisible(True); dock.raise_(); break
            self.terminal.display_area.appendPlainText(f"[{category.upper()}_DAP] {text.strip()}\n")
            self.terminal.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _on_dap_error(self, message: str):
        self.statusBar().showMessage(f"DAP Error: {message}", 7000)
        if self.terminal:
            self.terminal.display_area.appendPlainText(f"[DAP SYSTEM ERROR] {message.strip()}\n")
            self.terminal.display_area.moveCursor(QTextCursor.MoveOperation.End)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    print("MainWindow integration with CodeEditor for dirty status and breakpoints updated.")
    sys.exit(app.exec())
