import os
from PySide6.QtCore import QObject, Signal, Slot

class FileManager(QObject):
    # Signals
    file_opened = Signal(str, str)  # path, content
    file_saved = Signal(object, str, str)  # widget_ref (context for MainWindow), new_path, new_content

    file_open_error = Signal(str, str) # path_attempted, error_message
    file_save_error = Signal(object, str, str) # widget_ref (context for MainWindow), path_attempted, error_message
    dirty_status_changed = Signal(str, bool) # path, is_dirty

    def __init__(self, parent=None):
        super().__init__(parent)
        # Stores data about open files: {path: {"is_dirty": bool, "content_hash": int}}
        self.open_files_data = {}

    @Slot(str)
    def open_file(self, path):
        if not path:
            self.file_open_error.emit(path or "", "File path is empty.")
            return
        if not os.path.exists(path):
            self.file_open_error.emit(path, f"File not found: {path}")
            return
        if not os.path.isfile(path):
            self.file_open_error.emit(path, f"Path is not a file: {path}")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.open_files_data[path] = {"is_dirty": False, "content_hash": hash(content)}
            self.file_opened.emit(path, content)
        except Exception as e:
            self.file_open_error.emit(path, f"Could not open file {path}: {e}")

    @Slot(object, str, str) # widget_ref, content, path
    def save_file(self, widget_ref, content, path):
        if not path:
            self.file_save_error.emit(widget_ref, path or "", "File path cannot be None for saving.")
            return

        try:
            dir_name = os.path.dirname(path)
            if dir_name: # Ensure directory exists only if path includes a directory
                os.makedirs(dir_name, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            initial_dirty_state = self.open_files_data.get(path, {}).get("is_dirty", False)
            self.open_files_data[path] = {"is_dirty": False, "content_hash": hash(content)}
            self.file_saved.emit(widget_ref, path, content)
            if initial_dirty_state:
                self.dirty_status_changed.emit(path, False)

        except Exception as e:
            self.file_save_error.emit(widget_ref, path, f"Could not save file {path}: {e}")

    @Slot(str, str) # path, current_editor_content
    def update_file_content_changed(self, path, current_editor_content):
        '''
        Called by MainWindow when a tracked editor's content changes.
        Updates the dirty status.
        '''
        if path in self.open_files_data:
            current_hash = hash(current_editor_content)
            saved_hash = self.open_files_data[path].get("content_hash")

            is_dirty = current_hash != saved_hash

            if self.open_files_data[path]["is_dirty"] != is_dirty:
                self.open_files_data[path]["is_dirty"] = is_dirty
                self.dirty_status_changed.emit(path, is_dirty)

    @Slot(str)
    def get_dirty_state(self, path) -> bool:
        '''Returns the dirty state of a tracked file.'''
        return self.open_files_data.get(path, {}).get("is_dirty", False)

    @Slot(str) # path_of_file_being_closed
    def file_closed_in_editor(self, path):
        '''Called by MainWindow when a tab associated with a path is closed.'''
        if path in self.open_files_data:
            del self.open_files_data[path]

    def get_all_open_files_data(self):
        '''Returns the raw dictionary of open files data. Used by SessionManager.'''
        return self.open_files_data

    def load_open_files_data(self, data):
        '''Called by MainWindow during session load to restore FileManager's state.'''
        self.open_files_data = data

    @Slot(str, str)
    def rename_path_tracking(self, old_path, new_path):
        if old_path in self.open_files_data:
            data = self.open_files_data.pop(old_path)
            self.open_files_data[new_path] = data
            # print(f"FileManager: Renamed tracking from {old_path} to {new_path}")
            # Optionally, emit a signal if MainWindow needs to react specifically to this internal rename.
            # For example: path_tracking_renamed = Signal(str, str) # old_path, new_path
            # self.path_tracking_renamed.emit(old_path, new_path)
        else:
            # print(f"FileManager: rename_path_tracking called for non-tracked path: {old_path}")
            pass
