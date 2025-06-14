import os
import black
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QUndoStack # For managing undo/redo if handled here

class FileManager(QObject):
    # Signals
    # Emitted when a file is successfully opened and its content is read.
    # path: absolute path to the file
    # content: content of the file
    # is_dirty: initial dirty state (usually False for existing files, True for new)
    file_opened = Signal(str, str, bool)

    # Emitted when a file is successfully saved.
    # path: absolute path to the saved file
    # new_content: the content that was saved (potentially formatted)
    file_saved = Signal(str, str)

    # Emitted when a file tab is intended to be closed in the UI.
    # path: absolute path of the file being closed
    file_closed_in_editor = Signal(str) # Renamed from file_closed for clarity

    # Emitted when an error occurs during file operations.
    # title: title for an error message box
    # message: detailed error message
    error_occurred = Signal(str, str)

    # Emitted when the dirty status of a file changes.
    # path: absolute path to the file
    # is_dirty: boolean indicating the new dirty state
    dirty_status_changed = Signal(str, bool)

    item_created = Signal(str, bool)    # path, is_directory
    item_renamed = Signal(str, str)     # old_path, new_path
    item_deleted = Signal(str)          # path_deleted

    def __init__(self, parent=None):
        super().__init__(parent)
        # {path: {"content_on_disk": str, "is_dirty": bool}}
        # "content_on_disk" is the content as it was last read or saved.
        self.open_files_data = {}

    @Slot(str)
    def open_file(self, path: str):
        if not os.path.isfile(path):
            self.error_occurred.emit("File Error", f"File not found or is not a file: {path}")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.open_files_data[path] = {
                "content_on_disk": content, # Store what was read from disk
                "is_dirty": False
            }
            self.file_opened.emit(path, content, False)
            print(f"FileManager: Opened '{path}'")
        except Exception as e:
            self.error_occurred.emit("File Open Error", f"Could not open file '{path}':\n{e}")

    @Slot(str, str, str) # current_path, new_content_from_editor, new_path_for_save_as=None
    def save_file(self, current_path: str, content_to_save: str, new_path_for_save_as: str = None):
        path_to_save_to = new_path_for_save_as if new_path_for_save_as else current_path
        final_content_to_save = content_to_save

        if not path_to_save_to: # Should not happen if logic is correct
            self.error_occurred.emit("Save Error", "No file path specified for saving.")
            return False # Indicate failure

        # Apply Black formatting for Python files
        if path_to_save_to.lower().endswith(".py"):
            try:
                mode = black.FileMode()
                formatted_content = black.format_str(content_to_save, mode=mode)
                final_content_to_save = formatted_content
            except black.NothingChanged:
                final_content_to_save = content_to_save
            except black.InvalidInput as iie:
                self.error_occurred.emit("Formatting Error", f"Syntax error in Python code. Cannot format and save '{os.path.basename(path_to_save_to)}':\n{iie}")
                return False
            except Exception as e:
                print(f"Warning: Black formatting failed for '{path_to_save_to}', saving unformatted: {e}")

        try:
            with open(path_to_save_to, 'w', encoding='utf-8') as f:
                f.write(final_content_to_save)

            if current_path != path_to_save_to and current_path in self.open_files_data:
                del self.open_files_data[current_path]

            self.open_files_data[path_to_save_to] = {
                "content_on_disk": final_content_to_save,
                "is_dirty": False
            }

            self.file_saved.emit(path_to_save_to, final_content_to_save)
            self.dirty_status_changed.emit(path_to_save_to, False)
            print(f"FileManager: Saved '{path_to_save_to}'")
            return True
        except Exception as e:
            self.error_occurred.emit("File Save Error", f"Could not save file '{path_to_save_to}':\n{e}")
            return False

    @Slot(str)
    def close_file_requested(self, path: str):
        if path in self.open_files_data:
            self.file_closed_in_editor.emit(path)
            print(f"FileManager: Close requested for '{path}', UI can proceed to remove tab.")
        else:
            print(f"FileManager: Warning - close_file_requested for path not in open_files_data: {path}")
            self.file_closed_in_editor.emit(path)

    @Slot(str)
    def confirm_file_close(self, path: str):
        if path in self.open_files_data:
            del self.open_files_data[path]
            print(f"FileManager: Confirmed close and removed '{path}' from tracking.")
        else:
            print(f"FileManager: Warning - confirm_file_close for path not in open_files_data: {path}")

    @Slot(str)
    def get_file_content_on_disk(self, path: str) -> str | None:
        return self.open_files_data.get(path, {}).get("content_on_disk")

    @Slot(str, bool)
    def update_dirty_status(self, path: str, is_dirty: bool):
        if path in self.open_files_data:
            if self.open_files_data[path]["is_dirty"] != is_dirty:
                self.open_files_data[path]["is_dirty"] = is_dirty
                self.dirty_status_changed.emit(path, is_dirty)
                print(f"FileManager: Dirty status for '{path}' changed to {is_dirty}")
        elif is_dirty:
            self.dirty_status_changed.emit(path, is_dirty) # For new/untitled files not yet in open_files_data
            print(f"FileManager: Dirty status for (potentially new) '{path}' changed to {is_dirty}")

    @Slot(str)
    def is_file_dirty(self, path: str) -> bool:
        # For new (untitled) files, path might not be in open_files_data yet.
        # In this case, if MainWindow is tracking it as dirty, this method might not be called for it,
        # or MainWindow knows it's dirty because it's new and has no on-disk content.
        # This method is primarily for files known to FileManager.
        return self.open_files_data.get(path, {}).get("is_dirty", False)

    def get_open_file_paths_for_session(self) -> list:
        """Returns a list of paths of currently open files for session saving."""
        return list(self.open_files_data.keys())

    def load_open_files_from_session(self, files_to_open_paths: list):
        for path in files_to_open_paths:
            if os.path.exists(path):
                self.open_file(path)
            else:
                self.error_occurred.emit("Session Load Warning", f"File from last session not found: {path}")

    @Slot(str) # path should be the full path to the new file
    def create_new_file(self, file_path: str):
        if os.path.exists(file_path):
            self.error_occurred.emit("Create File Error", f"File or folder already exists at '{file_path}'.")
            return False
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('') # Create empty file
            print(f"FileManager: Created new file '{file_path}'")
            self.item_created.emit(file_path, False) # False for is_directory
            # QFileSystemModel should pick this up. No need to open it here.
            return True
        except Exception as e:
            self.error_occurred.emit("Create File Error", f"Could not create file '{file_path}':\n{e}")
            return False

    @Slot(str) # path should be the full path to the new folder
    def create_new_folder(self, folder_path: str):
        if os.path.exists(folder_path):
            self.error_occurred.emit("Create Folder Error", f"File or folder already exists at '{folder_path}'.")
            return False
        try:
            os.makedirs(folder_path, exist_ok=True) # exist_ok=True is fine, though we check os.path.exists first
            print(f"FileManager: Created new folder '{folder_path}'")
            self.item_created.emit(folder_path, True) # True for is_directory
            return True
        except Exception as e:
            self.error_occurred.emit("Create Folder Error", f"Could not create folder '{folder_path}':\n{e}")
            return False

    @Slot(str, str) # old_full_path, new_full_path (MainWindow will construct new_full_path)
    def rename_item(self, old_path: str, new_path: str):
        if not os.path.exists(old_path):
            self.error_occurred.emit("Rename Error", f"Item to rename not found: '{old_path}'.")
            return False
        if os.path.exists(new_path):
            self.error_occurred.emit("Rename Error", f"An item with the new name already exists: '{new_path}'.")
            return False
        try:
            os.rename(old_path, new_path)
            print(f"FileManager: Renamed '{old_path}' to '{new_path}'")

            # If the renamed item was an open file, update its tracking in open_files_data
            if old_path in self.open_files_data:
                file_data = self.open_files_data.pop(old_path)
                self.open_files_data[new_path] = file_data
                # Also need to inform MainWindow to update tab if it's open

            self.item_renamed.emit(old_path, new_path)
            return True
        except Exception as e:
            self.error_occurred.emit("Rename Error", f"Could not rename '{os.path.basename(old_path)}':\n{e}")
            return False

    @Slot(str)
    def delete_item(self, path_to_delete: str):
        if not os.path.exists(path_to_delete):
            self.error_occurred.emit("Delete Error", f"Item to delete not found: '{path_to_delete}'.")
            return False
        try:
            if os.path.isdir(path_to_delete):
                # Need to decide if we allow non-empty dir deletion or use shutil.rmtree
                # For safety, os.rmdir only removes empty dirs. shutil.rmtree is destructive.
                # Let's use os.rmdir for now and error if not empty.
                # If it's an open file's directory, this could be problematic.
                # Closing files within a directory before deleting the directory is MainWindow's job.
                os.rmdir(path_to_delete) # This will fail if directory is not empty
            else: # It's a file
                os.remove(path_to_delete)

            print(f"FileManager: Deleted '{path_to_delete}'")

            # If the deleted item was an open file, clean up its tracking
            if path_to_delete in self.open_files_data:
                # This implies the file was deleted from disk while open in editor.
                # MainWindow should handle closing the tab for this.
                del self.open_files_data[path_to_delete]
                # No need to call confirm_file_close as it's already gone from disk.

            self.item_deleted.emit(path_to_delete)
            return True
        except OSError as oe:
             if "Directory not empty" in str(oe):
                 self.error_occurred.emit("Delete Error", f"Could not delete folder '{os.path.basename(path_to_delete)}': It is not empty.")
             else:
                 self.error_occurred.emit("Delete Error", f"Could not delete '{os.path.basename(path_to_delete)}':\n{oe}")
             return False
        except Exception as e:
            self.error_occurred.emit("Delete Error", f"Could not delete '{os.path.basename(path_to_delete)}':\n{e}")
            return False
