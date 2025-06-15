import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget
import black
# import subprocess # Should have been removed if not used

class FileManager(QObject):
    file_content_loaded = Signal(str, str)  # path, content
    # MODIFIED SIGNAL DEFINITION
    file_saved = Signal(QWidget, str, str)  # widget, new_path, new_content
    error_occurred = Signal(str)            # error_message

    def __init__(self):
        super().__init__()
        # {widget_instance: {"path": "abs/path/to/file.py", "is_dirty": False}}
        self.open_files_state = {}

    def open_file(self, path: str):
        try:
            p = Path(str(path)) # Ensure path is a string
            if not p.is_file():
                self.error_occurred.emit(f"Error opening file: '{path}' is not a file or is inaccessible.")
                return

            abs_path_str = str(p.resolve()) # Store and emit absolute path

            with open(abs_path_str, 'r', encoding='utf-8') as f:
                content = f.read()
            self.file_content_loaded.emit(abs_path_str, content)
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

        # Content retrieval from widget (assuming widget has toPlainText)
        content_to_save = ""
        if hasattr(widget, 'toPlainText'):
            content_to_save = widget.toPlainText()
        else:
            self.error_occurred.emit(f"Cannot retrieve content from widget to save.")
            return

        save_path_obj = Path(final_save_path_str)
        formatted_content = content_to_save # Initialize with original content

        if save_path_obj.suffix == ".py":
            try:
                mode = black.FileMode(line_length=88)
                # Use black.format_str to get the formatted string
                formatted_content = black.format_str(content_to_save, mode=mode)
            except black.NothingChanged:
                # formatted_content remains content_to_save
                pass
            except black.InvalidInput as e:
                # Save original content if black fails due to syntax errors
                print(f"Black formatting error for {save_path_obj.name}: Invalid Python syntax. {e}. Saving original content.")
                self.error_occurred.emit(f"Syntax error in {save_path_obj.name}, saved without formatting.")
                # formatted_content is already content_to_save
            except Exception as e:
                print(f"Could not format {save_path_obj.name} with black: {e}. Saving original content.")
                # formatted_content is already content_to_save

        # content_to_save now holds the (potentially formatted) content
        # In this version, formatted_content will be written to disk.

        try:
            with open(save_path_obj, 'w', encoding='utf-8') as f:
                f.write(formatted_content) # Write the formatted (or original if formatting failed/skipped) content

            abs_save_path = str(save_path_obj.resolve())

            # Update internal state
            if widget in self.open_files_state: # Check if widget is tracked
                 self.open_files_state[widget]["path"] = abs_save_path
                 self.open_files_state[widget]["is_dirty"] = False
            else:
                  self.open_files_state[widget] = {"path": abs_save_path, "is_dirty": False}

            # MODIFIED EMIT CALL
            self.file_saved.emit(widget, abs_save_path, formatted_content) # Emit the content that was written
            # print(f"File saved successfully to {abs_save_path}")

        except PermissionError:
            self.error_occurred.emit(f"Error saving file: Permission denied for '{save_path_obj.name}'.")
        except Exception as e:
            self.error_occurred.emit(f"An unexpected error occurred while saving '{save_path_obj.name}': {str(e)}")


    def track_new_tab(self, widget: QWidget, path: str | None):
        abs_path = str(Path(path).resolve()) if path else None
        self.open_files_state[widget] = {"path": abs_path, "is_dirty": False}


    def update_dirty_status(self, widget: QWidget, is_dirty: bool):
        if widget in self.open_files_state:
            if self.open_files_state[widget]["is_dirty"] != is_dirty:
                self.open_files_state[widget]["is_dirty"] = is_dirty
        # else:
            # print(f"Warning: Attempted to update dirty status for untracked widget: {widget}")

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
        # else:
            # print(f"Warning: Attempted to untrack a widget that was not being tracked: {widget}")
