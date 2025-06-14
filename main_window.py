import sys
import os
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QDockWidget, QApplication, QWidget,
    QVBoxLayout, QMenuBar, QMenu, QFileDialog, QLabel, QToolBar,
    QMessageBox, QLineEdit, QPushButton, QStyle, QTreeWidget, QTreeWidgetItem,
    QListWidget, QListWidgetItem, QComboBox
)
from PySide6.QtGui import QAction, QIcon, QTextCharFormat, QColor, QTextCursor, QFont, QKeySequence
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QStandardPaths, QSize, QByteArray, QDir, QProcess

# Import new manager classes
from file_manager import FileManager
from process_manager import ProcessManager
from session_manager import SessionManager

# Import new manager classes
from file_manager import FileManager
from process_manager import ProcessManager
from session_manager import SessionManager

# Import refactored CodeEditor and other UI components
from code_editor import CodeEditor
from interactive_terminal import InteractiveTerminal # Added import
from file_explorer import FileExplorer # Added import

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
        self.setWindowTitle("Aether Editor (Refactored)")
        self.setGeometry(100, 100, 1200, 800)

        self.file_manager = FileManager(self)
        self.process_manager = ProcessManager(self)
        self.session_manager = SessionManager(self)

        self.editors_map = {}
        self.untitled_counter = 0
        self.file_explorer = None # Initialize file_explorer attribute

        self._setup_status_bar()
        self._setup_central_widget()
        self._setup_toolbars()
        self._setup_menus()
        self._setup_docks()

        self._connect_manager_signals()

        self.pending_initial_path = initial_path
        self.session_manager.load_session_data()
        self.setObjectName("MainWindow")

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

        self.request_control_button = QPushButton("Request Control")
        self.request_control_button.setObjectName("AccentButton")
        self.request_control_button.setEnabled(False)
        self.main_toolbar.addWidget(self.request_control_button)

        self.debugger_toolbar = QToolBar("Debugger Toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.debugger_toolbar)
        self.debugger_toolbar.setVisible(False)

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
        self.open_folder_action.setShortcut(QKeySequence("Ctrl+Shift+O")) # Or another suitable shortcut
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

        self.menuBar().addMenu("&View")
        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addAction(self.run_action)
        self.menuBar().addMenu("&Session")
        self.menuBar().addMenu("&Tools")
        self.menuBar().addMenu("&Help")

    def _setup_docks(self):
        # Terminal Dock
        self.terminal_dock = QDockWidget("Terminal", self)
        self.terminal_dock.setObjectName("TerminalDockWidget") # For QSS if needed
        self.terminal_widget = InteractiveTerminal(self)
        self.terminal_dock.setWidget(self.terminal_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal_dock)
        # Optionally, create a view menu action to toggle this dock
        # view_menu = self.menuBar().findChild(QMenu, "&View") # This might be how to find it if already created
        # if view_menu:
        #    view_menu.addAction(self.terminal_dock.toggleViewAction())
        # elif hasattr(self, 'view_menu'): # Check if view_menu exists as an attribute
        #    self.view_menu.addAction(self.terminal_dock.toggleViewAction())

        # File Explorer Dock
        self.file_explorer_dock = QDockWidget("File Explorer", self)
        self.file_explorer_dock.setObjectName("FileExplorerDockWidget")
        self.file_explorer = FileExplorer(self)
        self.file_explorer_dock.setWidget(self.file_explorer)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.file_explorer_dock)
        # Optionally, add to a View menu if one exists
        # if hasattr(self, 'view_menu') and self.view_menu:
        #     self.view_menu.addAction(self.file_explorer_dock.toggleViewAction())


    def _connect_manager_signals(self):
        self.file_manager.file_opened.connect(self._on_file_opened_by_manager)
        self.file_manager.file_saved.connect(self._on_file_saved_by_manager)
        self.file_manager.error_occurred.connect(self._on_file_manager_error)
        self.file_manager.dirty_status_changed.connect(self._on_dirty_status_changed_by_manager)
        self.file_manager.file_closed_in_editor.connect(self._on_file_closed_by_manager)
        self.file_manager.item_created.connect(self._on_fm_item_created)
        self.file_manager.item_renamed.connect(self._on_fm_item_renamed)
        self.file_manager.item_deleted.connect(self._on_fm_item_deleted)

        self.process_manager.output_received.connect(self._on_process_output)
        self.process_manager.process_started.connect(self._on_process_started)
        self.process_manager.process_finished.connect(self._on_process_finished)
        self.process_manager.process_error.connect(self._on_process_error)

        self.session_manager.session_data_loaded.connect(self._on_session_data_loaded)
        self.session_manager.session_data_saved.connect(self._on_session_data_saved)
        self.session_manager.session_error.connect(self._on_session_manager_error)

        if self.file_explorer:
            self.file_explorer.file_open_requested.connect(self._on_explorer_file_open_requested)
            self.file_explorer.create_new_file_requested.connect(self._on_explorer_create_new_file)
            self.file_explorer.create_new_folder_requested.connect(self._on_explorer_create_new_folder)
            self.file_explorer.rename_item_requested.connect(self._on_explorer_rename_item)
            self.file_explorer.delete_item_requested.connect(self._on_explorer_delete_item)
            self.file_explorer.open_in_terminal_requested.connect(self._on_explorer_open_in_terminal)

    @Slot()
    def _on_new_file(self):
        self.untitled_counter += 1
        file_path = f"untitled-{self.untitled_counter}"
        self._create_new_editor_tab(file_path, "", is_dirty=True, is_new_untitled=True)

    @Slot()
    def _on_open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File")
        if file_path:
            if file_path in self.editors_map:
                self.tab_widget.setCurrentWidget(self.editors_map[file_path])
            else:
                self.file_manager.open_file(file_path)

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
        current_path = self._get_current_file_path()
        suggested_name = os.path.basename(current_path) if current_path and not current_path.startswith("untitled-") else "untitled.py"
        default_dir = os.path.dirname(current_path) if current_path and not current_path.startswith("untitled-") and os.path.isdir(os.path.dirname(current_path)) else QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        new_file_path, _ = QFileDialog.getSaveFileName(self, "Save File As", os.path.join(default_dir, suggested_name))
        if new_file_path:
            content = current_editor.get_text()
            self.file_manager.save_file(current_path, content, new_path_for_save_as=new_file_path)

    @Slot()
    def _on_save_all_files(self):
        for path, editor in list(self.editors_map.items()): # Iterate on copy
            if editor.is_modified():
                content = editor.get_text()
                if path.startswith("untitled-"):
                    # This is complex: Save As for each untitled? For now, only save current if untitled.
                    if self.tab_widget.currentWidget() == editor:
                        self._on_save_file_as() # Trigger Save As for the current untitled tab
                else:
                    self.file_manager.save_file(path, content)

    @Slot(int)
    def _on_tab_close_requested(self, index: int):
        editor_widget = self.tab_widget.widget(index)
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
                    # Forcing Save As for untitled files. If user cancels Save As, tab won't close yet.
                    # This save_file call for untitled will trigger a save_as flow.
                    # If save_as is successful, FM emits file_saved, which updates editor to not dirty.
                    # Then FM emits file_closed_in_editor.
                    # If save_as is cancelled, file remains dirty, tab remains. This is okay.
                    self.file_manager.save_file(file_path, current_content, new_path_for_save_as=None)
                    if not editor_widget.is_modified(): # Check if save was successful (no longer dirty)
                         self.file_manager.close_file_requested(file_path) # Safe to close now
                    return # Don't proceed to FM close_file_requested if save was cancelled/file still dirty
                else:
                    self.file_manager.save_file(file_path, current_content)
                    # Assume save is synchronous for this check for now, or rely on dirty_status_changed signal
                    if not editor_widget.is_modified(): # If save successful
                        self.file_manager.close_file_requested(file_path)
                    return # Don't proceed if save failed and it's still dirty

        # If not dirty, or if Discard, or if Save was successful and handled above
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
            self.tab_widget.setCurrentIndex(i) # Set current to ensure focus for dialogs
            self._on_tab_close_requested(i)
            # If a tab closure was cancelled, it's tricky. For now, assume it tries all.

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
        old_path_key = path # Initially assume path hasn't changed

        # Check if this save corresponds to a previous "untitled" or a "save as" operation
        for p, ed in list(self.editors_map.items()):
            if p.startswith("untitled-") and ed.get_text() == new_content: # Heuristic for untitled save
                # If the saved path is different from the placeholder untitled path
                if p != path:
                    editor_to_update = ed
                    old_path_key = p
                    break
            elif ed.get_text() == new_content and p != path : # Heuristic for "Save As" from existing file
                 # This case is harder if content hasn't changed but path has.
                 # We need a more robust way to track which editor instance initiated the save_as.
                 # For now, if current editor matches, assume it was that.
                 current_editor = self._get_current_editor()
                 if current_editor == ed:
                    editor_to_update = ed
                    old_path_key = p
                    break


        if not editor_to_update and path in self.editors_map: # Standard save, path exists
             editor_to_update = self.editors_map[path]


        if editor_to_update:
            if old_path_key != path and old_path_key in self.editors_map:
                del self.editors_map[old_path_key]
            
            self.editors_map[path] = editor_to_update
            editor_to_update.set_file_path_context(path)
            
            if editor_to_update.get_text() != new_content: # Content might have been formatted
                editor_to_update.set_text(new_content, is_modified=False)
            else:
                editor_to_update.set_modified(False)

            tab_index = self.tab_widget.indexOf(editor_to_update)
            if tab_index != -1:
                self.tab_widget.setTabText(tab_index, os.path.basename(path))
                self.tab_widget.setTabToolTip(tab_index, path)

            self.status_bar.showMessage(f"Saved: {path}", 3000)
            self._update_status_bar_for_editor(editor_to_update) # Update language, etc.
            if self.tab_widget.currentWidget() == editor_to_update: # Ensure undo/redo enabled correctly
                 self._on_current_tab_changed(tab_index)

        else:
            print(f"MainWindow: Warning - file_saved signal for path not in editor_map or ambiguous: {path}")


    @Slot(str, bool)
    def _on_dirty_status_changed_by_manager(self, path: str, is_dirty: bool):
        editor = self.editors_map.get(path)
        if editor:
            tab_index = self.tab_widget.indexOf(editor)
            if tab_index != -1:
                current_tab_text = self.tab_widget.tabText(tab_index)
                base_name = os.path.basename(path)
                has_star = current_tab_text.endswith("*")
                if is_dirty and not has_star:
                    self.tab_widget.setTabText(tab_index, base_name + "*")
                elif not is_dirty and has_star:
                    self.tab_widget.setTabText(tab_index, base_name)
            # Optionally sync editor's internal modified state, but be careful with undo stack
            # editor.set_modified(is_dirty)


    @Slot(str)
    def _on_file_closed_by_manager(self, path: str):
        editor_to_close = self.editors_map.pop(path, None)
        if editor_to_close:
            tab_index = self.tab_widget.indexOf(editor_to_close)
            if tab_index != -1:
                self.tab_widget.removeTab(tab_index)
            editor_to_close.deleteLater()
            print(f"MainWindow: Closed tab and editor for {path}")
            if self.tab_widget.count() == 0:
                self._clear_status_bar_file_specifics()
                self.undo_action.setEnabled(False)
                self.redo_action.setEnabled(False)
        else:
            print(f"MainWindow: Warning - file_closed_by_manager for path not in editor_map: {path}")

    @Slot(str, str)
    def _on_file_manager_error(self, title: str, message: str):
        QMessageBox.critical(self, title, message)
        self.status_bar.showMessage(f"File Error: {title}", 5000)

    def _create_new_editor_tab(self, file_path: str, content: str, is_dirty: bool = False, is_new_untitled: bool = False):
        if file_path in self.editors_map:
            self.tab_widget.setCurrentWidget(self.editors_map[file_path])
            return

        editor = CodeEditor(file_path_context=file_path)
        editor.set_text(content, is_modified=is_dirty)

        editor.text_changed.connect(self._on_editor_text_changed) # Generic text changed
        editor.cursor_position_changed.connect(self._on_editor_cursor_position_changed)
        editor.modification_changed.connect(lambda modified, p=file_path: self._on_editor_modification_changed(p, modified))
        # editor.breakpoint_toggled_in_editor.connect(self._on_breakpoint_toggled)

        self.editors_map[file_path] = editor

        tab_name = os.path.basename(file_path)
        if is_dirty and not tab_name.endswith("*"):
            tab_name += "*"

        tab_index = self.tab_widget.addTab(editor, tab_name)
        self.tab_widget.setTabToolTip(tab_index, file_path)
        self.tab_widget.setCurrentIndex(tab_index)

        if is_new_untitled: # For new untitled files, directly tell FM about their "dirty" conceptual state
            self.file_manager.update_dirty_status(file_path, True)


    @Slot()
    def _on_editor_text_changed(self):
        # Could be used for live validation, etc.
        # The primary dirty tracking is via modification_changed.
        current_editor = self._get_current_editor()
        if current_editor:
            # This will trigger _on_editor_modification_changed if the modified state actually changes
            current_editor.document().setModified(True)


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

    def _update_status_bar_for_editor(self, editor: CodeEditor):
        path = self._get_path_for_editor(editor)
        language = "Plain Text" # Default
        if path:
            _, ext = os.path.splitext(path)
            language = self.EXTENSION_TO_LANGUAGE.get(ext.lower(), "Plain Text")
        editor.set_language(language)
        self.language_label.setText(f"Lang: {language}")
        # Cursor pos updated by direct signal

    def _clear_status_bar_file_specifics(self):
        self.cursor_pos_label.setText("Ln 1, Col 1")
        self.language_label.setText("Lang: N/A")

    def _get_current_editor(self) -> CodeEditor | None:
        return self.tab_widget.currentWidget() if isinstance(self.tab_widget.currentWidget(), CodeEditor) else None

    def _get_current_file_path(self) -> str | None:
        return self._get_path_for_editor(self._get_current_editor()) if self._get_current_editor() else None

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

        if current_editor.is_modified(): # Save before run
            # This save is crucial. If it involves "Save As" (e.g., first save of a non-untitled but modified file)
            # the file_path might change. The current self.file_manager.save_file doesn't return new path.
            # This needs robust handling. For now, assume save_file saves to existing 'file_path'.
            self.file_manager.save_file(file_path, current_editor.get_text())
            # A more robust way: connect to file_saved, then run. Or make save_file blocking/return status.

        _, extension = os.path.splitext(file_path)
        language_name = self.EXTENSION_TO_LANGUAGE.get(extension.lower())
        if not language_name:
            QMessageBox.warning(self, "Run Error", f"No language for '{extension}'."); return
        command_template = self.RUNNER_CONFIG.get(language_name)
        if not command_template:
            QMessageBox.warning(self, "Run Error", f"No runner for '{language_name}'."); return

        command_parts = [part.replace("{file}", file_path) for part in command_template]
        working_dir = os.path.dirname(file_path)

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
        # self.status_bar.showMessage("Process output...", 1000) # Optional

    @Slot()
    def _on_process_started(self):
        self.status_bar.showMessage("Process started...", 2000)
        self.run_action.setEnabled(False)
        if hasattr(self, 'terminal_dock') and self.terminal_dock: # Ensure terminal is visible
            self.terminal_dock.show()
            self.terminal_dock.raise_()

    @Slot(int, "QProcess::ExitStatus") # Use string literal for QProcess types if QProcess not directly imported
    def _on_process_finished(self, exit_code: int, exit_status): # exit_status type hint might need adjustment
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

        # Restore window geometry if available
        if "window_geometry" in data:
            try:
                self.restoreGeometry(QByteArray.fromBase64(data["window_geometry"].encode()))
            except Exception as e:
                print(f"Error restoring window geometry: {e}")

        open_file_paths = data.get("open_file_paths", [])
        active_file_path_from_session = data.get("active_file_path")

        for path in open_file_paths: # Request FM to open these
            self.file_manager.open_file(path) # This will emit file_opened signal

        # Handle initial_path from command line (if any, and not already opened by session)
        if self.pending_initial_path and self.pending_initial_path not in open_file_paths:
            self.file_manager.open_file(self.pending_initial_path)
            if not active_file_path_from_session: # If no active path from session, make initial_path active
                 active_file_path_from_session = self.pending_initial_path
        self.pending_initial_path = None

        # Setting active tab is tricky due to async file opening.
        # For now, if an active_file_path_from_session is specified and exists in editors_map
        # (meaning it was opened synchronously or very quickly), set it.
        # A more robust solution might involve a queue or waiting for all files to signal 'opened'.
        if active_file_path_from_session and active_file_path_from_session in self.editors_map:
            self.tab_widget.setCurrentWidget(self.editors_map[active_file_path_from_session])
        elif self.tab_widget.count() > 0: # Fallback
            self.tab_widget.setCurrentIndex(0)

        file_explorer_root = data.get("file_explorer_root")
        if self.file_explorer and file_explorer_root and os.path.isdir(file_explorer_root):
            self.file_explorer.set_root_path(file_explorer_root)
            self.setWindowTitle(f"Aether Editor - {os.path.basename(file_explorer_root)}")
        elif self.file_explorer: # Default if not in session or invalid
            default_fe_path = QDir.homePath()
            # If any files were opened, try to use their directory as a hint for FE root
            if open_file_paths: default_fe_path = os.path.dirname(open_file_paths[0])
            if not os.path.isdir(default_fe_path): default_fe_path = QDir.homePath()
            self.file_explorer.set_root_path(default_fe_path)
            if default_fe_path != QDir.homePath(): self.setWindowTitle(f"Aether Editor - {os.path.basename(default_fe_path)}")

        terminal_start_path = file_explorer_root if file_explorer_root and os.path.isdir(file_explorer_root) else QDir.homePath()
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.start_shell(terminal_start_path)

        self.status_bar.showMessage("Session loaded.", 2000)

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
                self._on_save_all_files() # Attempt to save all
                # Re-check if any are still dirty (e.g., Save As cancelled)
                if any(self.editors_map[p].is_modified() for p in dirty_paths if p in self.editors_map):
                    QMessageBox.warning(self, "Close Aborted", "Some files were not saved. Closing aborted.")
                    event.ignore(); return

        session_state = {
            "open_file_paths": list(self.editors_map.keys()),
            "active_file_path": self._get_current_file_path(),
            "window_geometry": self.saveGeometry().toBase64().data().decode(),
            "file_explorer_root": self.file_explorer.current_root_path if self.file_explorer else QDir.homePath(),
            # TODO: Add recent projects, other settings
        }
        self.session_manager.save_session_data(session_state)
        # Ideally, ensure session save completes before app fully quits.
        # For simple JSON write, it's usually fast enough.
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.stop_shell()
        event.accept()

# Minimal main execution for testing if this file is run directly (usually done in main.py)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # In a real app, stylesheet and fonts are loaded in main.py
    # from PySide6.QtCore import QByteArray # Add this import if testing restoreGeometry here
    # from PySide6.QtCore import QProcess # Add this if type hinting QProcess.ExitStatus etc.
    # from PySide6.QtCore import QDir # Add this if testing set_root_path or open_folder
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

# New Slots for FileExplorer signals
    @Slot(str)
    def _on_explorer_file_open_requested(self, path: str):
        if path in self.editors_map:
            self.tab_widget.setCurrentWidget(self.editors_map[path])
        else:
            self.file_manager.open_file(path)

    @Slot(str) # parent_dir_path
    def _on_explorer_create_new_file(self, parent_dir_path: str):
        file_name, ok = QInputDialog.getText(self, "New File", "Enter file name:", QLineEdit.Normal, "untitled.txt")
        if ok and file_name:
            full_path = os.path.join(parent_dir_path, file_name)
            if not self.file_manager.create_new_file(full_path):
                # Error already handled by FileManager's signal
                pass
            else:
                # Optionally open the new file
                # self.file_manager.open_file(full_path)
                pass # QFileSystemModel should update FileExplorer

    @Slot(str) # parent_dir_path
    def _on_explorer_create_new_folder(self, parent_dir_path: str):
        folder_name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:", QLineEdit.Normal, "NewFolder")
        if ok and folder_name:
            full_path = os.path.join(parent_dir_path, folder_name)
            self.file_manager.create_new_folder(full_path)
            # QFileSystemModel should update FileExplorer

    @Slot(str, str) # old_path, new_name (just the name, not full new path)
    def _on_explorer_rename_item(self, old_path: str, new_name: str):
        parent_dir = os.path.dirname(old_path)
        new_full_path = os.path.join(parent_dir, new_name)
        self.file_manager.rename_item(old_path, new_full_path)
        # QFileSystemModel should update FileExplorer. MainWindow updates tabs via _on_fm_item_renamed.

    @Slot(str) # path_to_delete
    def _on_explorer_delete_item(self, path_to_delete: str):
        # Confirmation is already done in FileExplorer before emitting signal
        self.file_manager.delete_item(path_to_delete)
        # QFileSystemModel should update. MainWindow updates tabs via _on_fm_item_deleted.

    @Slot(str) # directory_path
    def _on_explorer_open_in_terminal(self, directory_path: str):
        if hasattr(self, 'terminal_widget') and self.terminal_widget:
            self.terminal_widget.start_shell(directory_path)
            if hasattr(self, 'terminal_dock') and self.terminal_dock:
                self.terminal_dock.show()
                self.terminal_dock.raise_()
        else:
            QMessageBox.information(self, "Terminal", "Terminal component not available.")

# New Slots for FileManager item change signals
    @Slot(str, bool) # path, is_directory
    def _on_fm_item_created(self, path: str, is_directory: bool):
        # QFileSystemModel in FileExplorer should auto-update.
        # If not, FileExplorer might need a refresh_path(os.path.dirname(path)) call.
        if self.file_explorer:
            self.file_explorer.refresh_path(os.path.dirname(path)) # Tell FE to hint a refresh
        self.status_bar.showMessage(f"Created: {os.path.basename(path)}", 3000)

    @Slot(str, str) # old_path, new_path
    def _on_fm_item_renamed(self, old_path: str, new_path: str):
        if self.file_explorer:
            self.file_explorer.refresh_path(os.path.dirname(old_path)) # Refresh old parent
            self.file_explorer.refresh_path(os.path.dirname(new_path)) # Refresh new parent

        # Update any open editor tab that was tracking the old_path
        if old_path in self.editors_map:
            editor = self.editors_map.pop(old_path)
            self.editors_map[new_path] = editor
            editor.set_file_path_context(new_path)
            tab_index = self.tab_widget.indexOf(editor)
            if tab_index != -1:
                self.tab_widget.setTabText(tab_index, os.path.basename(new_path))
                self.tab_widget.setTabToolTip(tab_index, new_path)
                # Update dirty status if necessary (though rename shouldn't change content dirty state)
                is_dirty = editor.is_modified()
                self._on_dirty_status_changed_by_manager(new_path, is_dirty)
            if self.tab_widget.currentWidget() == editor:
                 self._update_status_bar_for_editor(editor)

        self.status_bar.showMessage(f"Renamed: {os.path.basename(old_path)} to {os.path.basename(new_path)}", 3000)

    @Slot(str) # path_deleted
    def _on_fm_item_deleted(self, path_deleted: str):
        if self.file_explorer:
            self.file_explorer.refresh_path(os.path.dirname(path_deleted))

        # Close any open editor tab for the deleted file
        if path_deleted in self.editors_map:
            editor_to_close = self.editors_map.pop(path_deleted)
            tab_index = self.tab_widget.indexOf(editor_to_close)
            if tab_index != -1:
                self.tab_widget.removeTab(tab_index) # This calls currentChanged, which handles status bar etc.
            editor_to_close.deleteLater()
            QMessageBox.information(self, "File Deleted",
                                    f"The open file '{os.path.basename(path_deleted)}' has been deleted.")

        self.status_bar.showMessage(f"Deleted: {os.path.basename(path_deleted)}", 3000)

# Slot for "Open Folder..." action
    @Slot()
    def _on_open_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Open Folder", QDir.homePath())
        if folder_path and self.file_explorer:
            self.file_explorer.set_root_path(folder_path)
            self.setWindowTitle(f"Aether Editor - {os.path.basename(folder_path)}")
            # Optionally, tell terminal to switch to this folder too
            if hasattr(self, 'terminal_widget') and self.terminal_widget:
                self.terminal_widget.start_shell(folder_path)
