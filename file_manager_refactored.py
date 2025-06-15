import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget
import black # For formatting Python files

class FileManager(QObject):
    file_content_loaded = Signal(str, str)  # path, content
    file_saved = Signal(QWidget, str)       # widget, new_path
    error_occurred = Signal(str)            # error_message

    def __init__(self):
        super().__init__()
        self.open_files_state = {}

    def open_file(self, path: str):
        try:
            # Ensure path is a string, as Path() expects str or bytes-like object
            p = Path(str(path))
            if not p.is_file():
                self.error_occurred.emit(f"Error opening file: '{path}' is not a file or is inaccessible.")
                return
            with open(p, 'r', encoding='utf-8') as f:
                content = f.read()
            self.file_content_loaded.emit(str(p.resolve()), content) # Emit resolved string path
        except FileNotFoundError:
            self.error_occurred.emit(f"Error opening file: File not found at '{path}'.")
        except PermissionError:
            self.error_occurred.emit(f"Error opening file: Permission denied for '{path}'.")
        except UnicodeDecodeError:
            self.error_occurred.emit(f"Error opening file: Could not decode file '{path}'. It might not be a text file or uses an unsupported encoding.")
        except Exception as e:
            self.error_occurred.emit(f"An unexpected error occurred while opening '{path}': {str(e)}")

    def save_file(self, widget: QWidget, path: str | None = None):
        final_save_path_str = path if path is not None else self.get_file_path(widget)

        if final_save_path_str is None:
            self.error_occurred.emit("Save operation failed: No path specified for the file.")
            return

        content_to_save = ""
        if hasattr(widget, 'toPlainText'):
            content_to_save = widget.toPlainText()
        else:
            self.error_occurred.emit(f"Cannot retrieve content from widget to save.")
            return

        save_path_obj = Path(final_save_path_str)

        if save_path_obj.suffix == ".py":
            try:
                mode = black.FileMode(line_length=88)
                formatted_content = black.format_str(content_to_save, mode=mode)
                content_to_save = formatted_content
            except black.NothingChanged:
                pass
            except black.InvalidInput as e:
                print(f"Black formatting error for {save_path_obj.name}: Invalid Python syntax. {e}. Saving original content.")
                self.error_occurred.emit(f"Syntax error in {save_path_obj.name}, saved without formatting.") # Inform user
            except Exception as e:
                print(f"Could not format {save_path_obj.name} with black: {e}. Saving original content.")

        try:
            with open(save_path_obj, 'w', encoding='utf-8') as f:
                f.write(content_to_save)

            abs_save_path = str(save_path_obj.resolve())
            self.open_files_state[widget] = {"path": abs_save_path, "is_dirty": False}
            self.file_saved.emit(widget, abs_save_path)
            # print(f"File saved successfully to {abs_save_path}")

        except PermissionError:
            self.error_occurred.emit(f"Error saving file: Permission denied for '{save_path_obj.name}'.")
        except Exception as e:
            self.error_occurred.emit(f"An unexpected error occurred while saving '{save_path_obj.name}': {str(e)}")

    def track_new_tab(self, widget: QWidget, path: str | None):
        abs_path = str(Path(path).resolve()) if path else None
        self.open_files_state[widget] = {"path": abs_path, "is_dirty": False if abs_path else True}

    def update_dirty_status(self, widget: QWidget, is_dirty: bool):
        if widget in self.open_files_state:
            self.open_files_state[widget]["is_dirty"] = is_dirty

    def get_file_path(self, widget: QWidget) -> str | None:
        if widget in self.open_files_state:
            return self.open_files_state[widget]["path"]
        return None

    def is_dirty(self, widget: QWidget) -> bool:
        if widget in self.open_files_state:
            return self.open_files_state[widget]["is_dirty"]
        return False

    def untrack_tab(self, widget: QWidget):
        if widget in self.open_files_state:
            del self.open_files_state[widget]
