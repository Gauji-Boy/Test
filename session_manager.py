import json
import os
from PySide6.QtCore import QObject, Signal, Slot, QStandardPaths

class SessionManager(QObject):
    # Signals
    # Emitted when session data is successfully loaded.
    # data: a dictionary containing the loaded session state
    session_data_loaded = Signal(dict)

    # Emitted when session data is successfully saved.
    session_data_saved = Signal()

    # Emitted when an error occurs during session loading or saving.
    # message: a string describing the error
    session_error = Signal(str)

    CONFIG_DIR_NAME = "AetherEditor" # Application-specific config directory name
    SESSION_FILE_NAME = "session.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session_file_path = self._get_session_file_path()

    def _get_session_file_path(self) -> str:
        """Determines the path for the session file."""
        try:
            app_data_path = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
            # QStandardPaths.AppConfigLocation can sometimes just be .config or AppData
            # So, we ensure our application-specific directory exists.
            if not app_data_path: # Fallback if somehow AppConfigLocation is empty
                app_data_path = QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation)

            # Ensure the app-specific directory is part of the path
            # This handles cases where AppConfigLocation might be too generic (e.g., just '~/.config')
            # or already specific (e.g., '~/.config/YourApp').
            # We want to ensure our CONFIG_DIR_NAME is the final component for the directory.
            base_config_path = app_data_path
            if os.path.basename(app_data_path).lower() != self.CONFIG_DIR_NAME.lower():
                 base_config_path = os.path.join(app_data_path, self.CONFIG_DIR_NAME)
            
            if not os.path.exists(base_config_path):
                os.makedirs(base_config_path, exist_ok=True)
            
            return os.path.join(base_config_path, self.SESSION_FILE_NAME)
        except Exception as e:
            print(f"SessionManager: Error determining session file path: {e}")
            # Fallback to current directory if all else fails (less ideal)
            return os.path.join(os.getcwd(), self.SESSION_FILE_NAME)


    @Slot(dict)
    def save_session_data(self, data_dict: dict):
        """Saves the provided session data to the session file."""
        if not self.session_file_path:
            self.session_error.emit("Session file path is not configured.")
            return

        try:
            # Ensure directory exists one last time
            session_dir = os.path.dirname(self.session_file_path)
            if not os.path.exists(session_dir):
                os.makedirs(session_dir, exist_ok=True)

            with open(self.session_file_path, 'w', encoding='utf-8') as f:
                json.dump(data_dict, f, indent=4)
            self.session_data_saved.emit()
            print(f"SessionManager: Session data saved to '{self.session_file_path}'")
        except Exception as e:
            error_msg = f"Could not save session data to '{self.session_file_path}':\n{e}"
            self.session_error.emit(error_msg)
            print(f"SessionManager: Error - {error_msg}")

    @Slot()
    def load_session_data(self) -> None:
        """Loads session data from the session file and emits session_data_loaded."""
        if not self.session_file_path:
            self.session_error.emit("Session file path is not configured for loading.")
            self.session_data_loaded.emit({}) # Emit empty dict if no path
            return

        if not os.path.exists(self.session_file_path):
            print(f"SessionManager: Session file '{self.session_file_path}' not found. Starting fresh.")
            self.session_data_loaded.emit({}) # Emit empty dict if file doesn't exist
            return

        try:
            with open(self.session_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.session_data_loaded.emit(data)
            print(f"SessionManager: Session data loaded from '{self.session_file_path}'")
        except json.JSONDecodeError as jde:
            error_msg = f"Could not parse session data from '{self.session_file_path}' (JSONDecodeError): {jde}.\nStarting with a fresh session."
            self.session_error.emit(error_msg)
            print(f"SessionManager: Error - {error_msg}")
            self.session_data_loaded.emit({}) # Emit empty on parse error
        except Exception as e:
            error_msg = f"Could not load session data from '{self.session_file_path}':\n{e}.\nStarting with a fresh session."
            self.session_error.emit(error_msg)
            print(f"SessionManager: Error - {error_msg}")
            self.session_data_loaded.emit({}) # Emit empty on other errors
