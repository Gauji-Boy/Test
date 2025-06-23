import os
import json
from PySide6.QtCore import QObject, Slot, QStandardPaths, Signal

class SessionManager(QObject):
    # Signal to inform about errors during session loading or saving
    session_error = Signal(str)
    session_loaded = Signal(dict) # Emits loaded session data
    session_saved = Signal()      # Confirms session was saved

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session_file_name = "session.json"
        self.app_config_dir_name = ".aether_editor" # Same as in MainWindow

    def _get_session_file_path(self):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        session_dir = os.path.join(config_dir, self.app_config_dir_name)
        os.makedirs(session_dir, exist_ok=True)
        return os.path.join(session_dir, self.session_file_name)

    @Slot(dict, list, str, str)
    def save_session(self, open_files_data, recent_projects, root_path, active_file_path: str):
        """
        Saves the session data to session.json.
        open_files_data: Data from FileManager.get_all_open_files_data()
                         It's a dict like {path: {"is_dirty": bool, "content_hash": int}}
        recent_projects: List of recent project paths.
        root_path: Current root path of the file explorer.
        active_file_path: Path of the currently active file/tab.
        """
        session_data_to_save = {
            "open_files_data": open_files_data, # This now stores hashes and dirty flags
            "recent_projects": recent_projects,
            "root_path": root_path,
            "active_file_path": active_file_path
        }

        session_file_path = self._get_session_file_path()
        try:
            with open(session_file_path, 'w', encoding='utf-8') as f:
                json.dump(session_data_to_save, f, indent=4)
            # print(f"SessionManager: Session saved to {session_file_path}. Content: {session_data_to_save}")
            self.session_saved.emit()
        except IOError as e:
            error_msg = f"Error saving session to {session_file_path}: {e}"
            # print(f"SessionManager: {error_msg}")
            self.session_error.emit(error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred while saving session: {e}"
            # print(f"SessionManager: {error_msg}")
            self.session_error.emit(error_msg)

    @Slot()
    def load_session(self):
        """
        Loads session data from session.json.
        Returns the loaded data as a dictionary.
        Emits session_loaded signal on success, or session_error on failure.
        """
        session_file_path = self._get_session_file_path()
        default_session_data = {
            "open_files_data": {},
            "recent_projects": [],
            "root_path": None,
            "active_file_path": None # Changed from active_file_index: 0
        }

        if os.path.exists(session_file_path):
            try:
                with open(session_file_path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)

                # Ensure active_file_path is part of the loaded_data, default to None if not.
                # If old "active_file_index" exists, it's ignored in favor of "active_file_path".
                if "active_file_path" not in loaded_data:
                    loaded_data["active_file_path"] = None

                # print(f"SessionManager: Session loaded from {session_file_path}. Content: {loaded_data}")
                self.session_loaded.emit(loaded_data)
                return loaded_data
            except json.JSONDecodeError as e:
                error_msg = f"Error decoding session file {session_file_path}: {e}. Using default session."
                # print(f"SessionManager: {error_msg}")
                self.session_error.emit(error_msg)
                self.session_loaded.emit(default_session_data) # Emit default data on error
                return default_session_data
            except Exception as e:
                error_msg = f"An unexpected error occurred while loading session: {e}. Using default session."
                # print(f"SessionManager: {error_msg}")
                self.session_error.emit(error_msg)
                self.session_loaded.emit(default_session_data) # Emit default data on error
                return default_session_data
        else:
            # print(f"SessionManager: Session file {session_file_path} not found. Using default session.")
            # No error signal here, it's normal for first run
            self.session_loaded.emit(default_session_data)
            return default_session_data
