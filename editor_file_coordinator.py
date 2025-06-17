import os
import json
import black
import logging
from PySide6.QtCore import QObject, Slot, QStandardPaths, Qt # Added Qt for Qt.WaitCursor
from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox, QApplication, QLineEdit, QInputDialog
# To avoid circular import, 'MainWindow' type hint is as string.
# from main_window import MainWindow # This would be circular.
from code_editor import CodeEditor
from typing import Any # Added for type hints

logger = logging.getLogger(__name__)

class EditorFileCoordinator(QObject):
    main_win: 'MainWindow' # Forward reference for MainWindow
    editor_to_path: dict[CodeEditor, str]
    path_to_editor: dict[str, CodeEditor]

    def __init__(self, main_window: 'MainWindow') -> None:
        super().__init__()
        self.main_win = main_window
        # These will be populated by MainWindow after its own dicts are initialized
        self.editor_to_path = main_window.editor_to_path
        self.path_to_editor = main_window.path_to_editor

    def _save_file(self, index: int, save_as: bool = False) -> bool:
        editor_widget: QWidget | None = self.main_win.tab_widget.widget(index)
        if not isinstance(editor_widget, CodeEditor):
            return False

        editor: CodeEditor = editor_widget # Now we know it's a CodeEditor

        current_path_placeholder: str | None = self.editor_to_path.get(editor)
        content_to_save: str = editor.toPlainText()
        path_to_save: str | None = None
        is_untitled_file: bool = current_path_placeholder is not None and current_path_placeholder.startswith("untitled:")

        if save_as or is_untitled_file:
            suggested_dir: str = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            suggested_fn_base: str = os.path.basename(current_path_placeholder) if current_path_placeholder and not is_untitled_file else "Untitled.py"
            if is_untitled_file and current_path_placeholder:
                suggested_fn_base = os.path.basename(current_path_placeholder)

            full_suggested_path: str = os.path.join(suggested_dir, suggested_fn_base)
            # QFileDialog.getSaveFileName returns a tuple (filePath, selectedFilter)
            new_path_tuple: tuple[str, str] = QFileDialog.getSaveFileName(self.main_win, "Save File As", full_suggested_path,
                "All Files (*);;Python Files (*.py);;C++ Files (*.cpp *.cxx *.h *.hpp);;Text Files (*.txt)")
            new_path: str = new_path_tuple[0]
            if not new_path:
                self.main_win.status_bar.showMessage("Save cancelled.", 3000)
                return False
            path_to_save = new_path
        else:
            path_to_save = current_path_placeholder

        if not path_to_save:
            logger.error("No path for saving determined during _save_file.")
            QMessageBox.critical(self.main_win, "Save Error", "No path for saving.")
            return False

        if path_to_save.lower().endswith(".py"):
            try:
                formatted_content: str = black.format_str(content_to_save, mode=black.FileMode())
                if formatted_content != content_to_save:
                    self.main_win.collaboration_service.is_updating_from_network = True
                    cursor_pos: int = editor.textCursor().position()
                    editor.setPlainText(formatted_content)
                    new_cursor = editor.textCursor()
                    new_cursor.setPosition(min(cursor_pos, len(formatted_content)))
                    editor.setTextCursor(new_cursor)
                    self.main_win.collaboration_service.is_updating_from_network = False
                    content_to_save = formatted_content
            except black.parsing.LibCSTError as e:
                logger.error(f"Syntax error during Black formatting: {e}", exc_info=True)
                QMessageBox.critical(self.main_win, "Format Error", f"Syntax error:\n{e}")
                return False
            except Exception as e:
                logger.error(f"Black formatting failed: {e}", exc_info=True)

        QApplication.setOverrideCursor(Qt.WaitCursor) # Qt.WaitCursor needs Qt import
        self.main_win.file_manager.save_file(editor, content_to_save, path_to_save)
        QApplication.restoreOverrideCursor()
        return True

    def save_current_file(self) -> bool:
        idx: int = self.main_win.tab_widget.currentIndex()
        if idx == -1:
            self.main_win.status_bar.showMessage("No active editor.")
            return False
        return self._save_file(idx)

    def save_current_file_as(self) -> bool:
        idx: int = self.main_win.tab_widget.currentIndex()
        if idx == -1:
            self.main_win.status_bar.showMessage("No active editor.")
            return False
        return self._save_file(idx, save_as=True)

    @Slot(object, str, str)
    def _handle_file_saved(self, editor_widget: QWidget, saved_path: str, saved_content: str) -> None:
        # editor_widget is expected to be a CodeEditor instance.
        if not isinstance(editor_widget, CodeEditor):
            logger.warning(f"_handle_file_saved called with non-CodeEditor widget: {type(editor_widget)}")
            return

        logger.info(f"File saved: {saved_path}")
        old_path: str | None = self.editor_to_path.get(editor_widget)
        if old_path and old_path != saved_path:
            logger.info(f"File saved under new name. Old path: {old_path}, New path: {saved_path}")
            if old_path in self.path_to_editor:
                del self.path_to_editor[old_path]

        self.editor_to_path[editor_widget] = saved_path
        self.path_to_editor[saved_path] = editor_widget
        editor_widget.file_path = saved_path # Update CodeEditor's internal path

        idx: int = self.main_win.tab_widget.indexOf(editor_widget)
        if idx != -1:
            self.main_win.tab_widget.setTabText(idx, os.path.basename(saved_path))
            self.main_win.tab_widget.setTabToolTip(idx, saved_path)
        self.main_win.status_bar.showMessage(f"File '{os.path.basename(saved_path)}' saved.", 3000)
        if hasattr(self.main_win, 'file_explorer'):
            self.main_win.file_explorer.refresh_tree()

    @Slot(object, str, str)
    def _handle_file_save_error(self, widget: QWidget, path: str, error: str) -> None:
        # widget is expected to be a CodeEditor instance.
        logger.error(f"Error saving file '{path}': {error}")
        QMessageBox.critical(self.main_win, "Save Error", f"Could not save '{path}':\n{error}")
        self.main_win.status_bar.showMessage(f"Save error for {path}", 5000)

    def open_file(self) -> None:
        dialog = QFileDialog(self.main_win)
        dialog.setFileMode(QFileDialog.ExistingFile)
        if dialog.exec():
            fpath: str = dialog.selectedFiles()[0]
            self.main_win.initialize_project(fpath)
            self.open_new_tab(fpath)

    def _get_next_untitled_name(self) -> str:
        count: int = 1
        while True:
            name: str = f"Untitled-{count}"
            if not any(p.startswith("untitled:") and os.path.basename(p) == name for p in self.path_to_editor.keys()):
                return name
            count += 1
        # This part of the code should be unreachable due to the loop structure,
        # but linters might complain if 'name' is not guaranteed to be defined after the loop.
        # However, the loop is infinite until a name is found.
        # logger.debug(f"Generated new untitled name: {name}")

    def open_new_tab(self, file_path: str | None = None) -> None:
        if file_path:
            logger.info(f"Opening new tab for file: {file_path}")
            if file_path in self.path_to_editor:
                editor: CodeEditor = self.path_to_editor[file_path]
                idx: int = self.main_win.tab_widget.indexOf(editor)
                if idx != -1:
                    logger.debug(f"File {file_path} already open in tab {idx}. Switching to it.")
                    self.main_win.tab_widget.setCurrentIndex(idx)
                    return
            self.main_win.file_manager.open_file(file_path)
        else:
            logger.info("Opening new untitled tab.")
            editor = CodeEditor(self.main_win) # main_win is 'MainWindow'
            title: str = self._get_next_untitled_name()
            placeholder_path: str = f"untitled:{title}"
            logger.debug(f"Untitled tab placeholder path: {placeholder_path}")

            idx = self.main_win.tab_widget.addTab(editor, title)
            self.main_win.tab_widget.setCurrentIndex(idx)
            self.main_win.tab_widget.setTabToolTip(idx, title)

            self.editor_to_path[editor] = placeholder_path
            self.path_to_editor[placeholder_path] = editor
            editor.file_path = placeholder_path # Set file_path on the CodeEditor instance

            editor.textChanged.connect(self.main_win.on_text_editor_changed)
            editor.cursor_position_changed_signal.connect(self.main_win._update_cursor_position_label)
            editor.language_changed_signal.connect(self.main_win._update_language_label)
            editor.control_reclaim_requested.connect(self.main_win.collaboration_service.on_host_reclaim_control)
            editor.breakpoint_toggled.connect(self.main_win.execution_coordinator._handle_breakpoint_toggled)

            self.main_win._update_status_bar_and_language_selector_on_tab_change(idx)
            self.main_win.update_editor_read_only_state()
            self.main_win._update_undo_redo_actions()
            self.main_win._handle_dirty_status_changed(placeholder_path, True)

    @Slot(str, str)
    def _handle_file_opened(self, path: str, content: str) -> None:
        if path in self.path_to_editor:
            editor: CodeEditor = self.path_to_editor[path]
            idx: int = self.main_win.tab_widget.indexOf(editor)
            if idx != -1:
                logger.debug(f"File {path} already open. Switching to tab {idx}.")
                self.main_win.tab_widget.setCurrentIndex(idx)
                return

        logger.info(f"Handling file opened: {path}")
        editor = CodeEditor(self.main_win) # main_win is 'MainWindow'
        editor.setPlainText(content)
        editor.file_path = path # Set file_path on the CodeEditor instance

        # Lambda for cursor position: types are (lambda: None)
        editor.cursorPositionChanged.connect(lambda: self.main_win._update_cursor_position_label(
            editor.textCursor().blockNumber() + 1, editor.textCursor().columnNumber() + 1))
        editor.set_file_path_and_update_language(path)

        idx = self.main_win.tab_widget.addTab(editor, os.path.basename(path))
        self.main_win.tab_widget.setCurrentIndex(idx)
        self.main_win.tab_widget.setTabToolTip(idx, path)

        self.editor_to_path[editor] = path
        self.path_to_editor[path] = editor

        editor.textChanged.connect(self.main_win.on_text_editor_changed)
        editor.cursor_position_changed_signal.connect(self.main_win._update_cursor_position_label)
        editor.language_changed_signal.connect(self.main_win._update_language_label)
        editor.control_reclaim_requested.connect(self.main_win.collaboration_service.on_host_reclaim_control)
        editor.breakpoint_toggled.connect(self.main_win.execution_coordinator._handle_breakpoint_toggled)

        self.main_win._update_status_bar_and_language_selector_on_tab_change(idx)
        self.main_win.update_editor_read_only_state()
        self.main_win._update_undo_redo_actions()
        self.main_win.status_bar.showMessage(f"Opened {path}", 2000)

    @Slot(str, str)
    def _handle_file_open_error(self, path: str, error: str) -> None:
        logger.error(f"Error opening file '{path}': {error}")
        QMessageBox.critical(self.main_win, "Open Error", f"Could not open '{path}':\n{error}")
        self.main_win.status_bar.showMessage(f"Error opening {path}", 5000)

    def get_active_file_path(self) -> str | None:
        editor: CodeEditor | None = self.main_win._get_current_code_editor() # _get_current_code_editor returns CodeEditor | None
        if editor:
            path: str | None = self.editor_to_path.get(editor)
            if path and not path.startswith("untitled:"):
                return path
        return None

    def close_tab(self, index: int | None = None) -> None:
        idx_to_close: int = self.main_win.tab_widget.currentIndex() if index is None else index
        if idx_to_close == -1:
            return

        widget: QWidget | None = self.main_win.tab_widget.widget(idx_to_close)
        if not widget:
            return

        path_for_editor: str | None = self.editor_to_path.get(widget) # type: ignore # widget might not be CodeEditor initially
        proceed: bool = True

        if path_for_editor:
            is_dirty: bool = self.main_win.file_manager.get_dirty_state(path_for_editor) if not path_for_editor.startswith("untitled:") \
                         else self.main_win.tab_widget.tabText(idx_to_close).endswith("*")
            if is_dirty:
                reply: QMessageBox.StandardButton = QMessageBox.question(self.main_win, "Unsaved Changes",
                                             f"'{self.main_win.tab_widget.tabText(idx_to_close)}' has changes. Save?",
                                             QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
                if reply == QMessageBox.Save:
                    proceed = self._save_file(idx_to_close)
                elif reply == QMessageBox.Cancel:
                    proceed = False

        if not proceed:
            return

        if isinstance(widget, CodeEditor):
            try: widget.textChanged.disconnect(self.main_win.on_text_editor_changed)
            except RuntimeError: pass # Signal not connected or already disconnected
            try: widget.control_reclaim_requested.disconnect(self.main_win.collaboration_service.on_host_reclaim_control)
            except RuntimeError: pass
            try: widget.cursor_position_changed_signal.disconnect(self.main_win._update_cursor_position_label)
            except RuntimeError: pass
            try: widget.language_changed_signal.disconnect(self.main_win._update_language_label)
            except RuntimeError: pass
            try: widget.breakpoint_toggled.disconnect(self.main_win.execution_coordinator._handle_breakpoint_toggled)
            except RuntimeError: pass

        if path_for_editor:
            if widget in self.editor_to_path:
                del self.editor_to_path[widget] # type: ignore
            if path_for_editor in self.path_to_editor:
                del self.path_to_editor[path_for_editor]
            if not path_for_editor.startswith("untitled:"):
                self.main_win.file_manager.file_closed_in_editor(path_for_editor)

        widget.deleteLater()
        self.main_win.tab_widget.removeTab(idx_to_close)

    def create_new_file(self) -> None:
        # sel_idx type can be QModelIndex
        sel_idx = self.main_win.file_explorer.selectionModel().currentIndex()
        target_dir: str | None = None
        if sel_idx.isValid():
            selected_path = self.main_win.file_explorer.model.filePath(sel_idx)
            if os.path.isdir(selected_path):
                target_dir = selected_path
            else:
                target_dir = os.path.dirname(selected_path)
        else:
            target_dir = self.main_win.file_explorer.model.rootPath()

        if not target_dir:
            logger.error("Cannot determine target directory for new file.")
            QMessageBox.critical(self.main_win, "Error", "Cannot determine target directory.")
            return

        # QInputDialog.getText returns tuple (text, ok_bool)
        name_tuple: tuple[str, bool] = QInputDialog.getText(self.main_win, "New File", "File name:", QLineEdit.Normal, "")
        name: str = name_tuple[0]
        ok: bool = name_tuple[1]

        if not (ok and name):
            logger.info("New file creation cancelled by user.")
            return

        fpath: str = os.path.join(target_dir, name)
        if os.path.exists(fpath):
            logger.warning(f"Attempted to create existing file: {fpath}")
            QMessageBox.warning(self.main_win, "Exists", "File already exists.")
            return

        try:
            with open(fpath, 'w', encoding='utf-8') as f:
                pass
            logger.info(f"Created new file: {fpath}")
            self.open_new_tab(fpath)
            self.main_win.status_bar.showMessage(f"Created: {fpath}", 3000)
        except OSError as e:
            logger.error(f"Failed to create file '{fpath}': {e}", exc_info=True)
            QMessageBox.critical(self.main_win, "Error", f"Failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error creating file '{fpath}': {e}", exc_info=True)
            QMessageBox.critical(self.main_win, "Error", f"Unexpected error: {e}")
