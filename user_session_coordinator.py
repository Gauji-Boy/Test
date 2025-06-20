import os
import logging
from PySide6.QtCore import QObject, Slot # Signal removed if no longer needed by other parts
from PySide6.QtWidgets import QMessageBox, QInputDialog, QLineEdit
from typing import Any, TYPE_CHECKING, Optional

from config_manager import ConfigManager # Added
from config import DEFAULT_RECENT_PROJECTS_LIMIT # Added

if TYPE_CHECKING:
    from main_window import MainWindow # Assuming main_window.py

logger = logging.getLogger(__name__)

class UserSessionCoordinator(QObject):
    # recent_projects_loaded = Signal(list) # Removed
    main_win: Optional['MainWindow']
    recent_projects: list[str]
    recent_projects_limit: int # Added

    def __init__(self) -> None:
        super().__init__()
        logger.info("UserSessionCoordinator INSTANCE CREATED") # Added
        self.main_win = None
        self.recent_projects = []

        config_mgr = ConfigManager() # Added
        self.recent_projects_limit: int = config_mgr.load_setting('recent_projects_limit', DEFAULT_RECENT_PROJECTS_LIMIT) # Added

    def set_main_window_ref(self, main_window: 'MainWindow') -> None:
        self.main_win = main_window
        # Initialize attributes that depend on main_window
        # The recent_projects list will be populated by _handle_session_loaded
        # after the session is loaded by SessionManager.
        # No need to initialize from main_win.recent_projects as it's now removed.


    def save_session(self) -> None:
        if not self.main_win or not self.main_win.session_manager:
            logger.warning("UserSessionCoordinator: Cannot save session, MainWindow or SessionManager not available.")
            return

        open_files_data: dict[str, dict[str, Any]] = self.main_win.file_manager.get_all_open_files_data()
        active_file_path: str | None = self.main_win.editor_file_coordinator.get_active_file_path()
        root_path_to_save: str | None = None

        if hasattr(self.main_win.file_explorer, 'model') and self.main_win.file_explorer.model is not None:
            root_path_to_save = self.main_win.file_explorer.model.rootPath()
        elif active_file_path and os.path.exists(active_file_path):
             root_path_to_save = os.path.dirname(active_file_path)

        self.main_win.session_manager.save_session(
            open_files_data, self.recent_projects, root_path_to_save, active_file_path)

    @Slot(dict)
    def _handle_session_loaded(self, session_data: dict[str, Any]) -> None:
        print("DEBUG PRINT: UserSessionCoordinator._handle_session_loaded: Method ENTERED.", flush=True) # Added
        logger.info("UserSessionCoordinator._handle_session_loaded: Method ENTERED.") # Added as first line
        logger.info(f"UserSessionCoordinator._handle_session_loaded: Received raw session_data (type: {type(session_data)}): {session_data}") # Added as second line
        if not self.main_win: return
        logger.info(f"UserSessionCoordinator._handle_session_loaded CALLED. session_data recent_projects: {session_data.get('recent_projects')}") # Existing, to remain

        self.recent_projects.clear()
        self.recent_projects.extend(session_data.get("recent_projects", []))
        logger.info(f"UserSessionCoordinator._handle_session_loaded: self.recent_projects list AFTER extend is now: {self.recent_projects}") # Modified
        # self.recent_projects_loaded.emit(self.recent_projects) # Removed
        self.main_win._update_recent_menu()
        if self.main_win: # Added
            logger.info(f"UserSessionCoordinator._handle_session_loaded: About to notify AppController with list: {self.recent_projects}") # Added
            self.main_win.notify_app_controller_of_recent_projects_update(self.recent_projects) # Added

        root_path_from_session: str | None = session_data.get("root_path")
        open_files_data_from_session: dict[str, Any] = session_data.get("open_files_data", {})
        active_file_path_to_restore: str | None = session_data.get("active_file_path")

        self.main_win.file_manager.load_open_files_data(open_files_data_from_session)

        if root_path_from_session:
            self.main_win.initialize_project(root_path_from_session, add_to_recents=False)

        paths_to_open: list[str] = sorted(list(open_files_data_from_session.keys()))
        for path in paths_to_open:
            if os.path.exists(path):
                self.main_win.editor_file_coordinator.open_new_tab(path)
            else:
                logger.warning(f"Session file not found, skipping: {path}")


        if active_file_path_to_restore and active_file_path_to_restore in self.main_win.editor_file_coordinator.path_to_editor:
            editor_to_activate: Any = self.main_win.editor_file_coordinator.path_to_editor[active_file_path_to_restore]
            idx: int = self.main_win.tab_widget.indexOf(editor_to_activate)
            if idx != -1:
                self.main_win.tab_widget.setCurrentIndex(idx)
        elif self.main_win.tab_widget.count() > 0:
            self.main_win.tab_widget.setCurrentIndex(0)

        self.main_win.status_bar.showMessage("Session loaded.", 2000)

    @Slot()
    def _handle_session_saved_confirmation(self) -> None:
        if not self.main_win: return
        logger.info("Session saved successfully.")
        self.main_win.status_bar.showMessage("Session saved.", 2000)

    @Slot(str)
    def _handle_session_error(self, error_message: str) -> None:
        if not self.main_win: return
        logger.error(f"Session error: {error_message}")
        QMessageBox.warning(self.main_win, "Session Error", error_message)
        self.main_win.status_bar.showMessage(f"Session error: {error_message}", 5000)

    def add_recent_project(self, path: str) -> None:
        if not self.main_win: return
        logger.info(f"UserSessionCoordinator.add_recent_project CALLED with path: {path}") # Modified
        logger.info(f"UserSessionCoordinator.add_recent_project: self.recent_projects BEFORE modification is: {self.recent_projects}") # Modified
        logger.info(f"add_recent_project: self.recent_projects_limit: {self.recent_projects_limit}")

        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        logger.info(f"add_recent_project: self.recent_projects after insertion, before trimming: {self.recent_projects}")

        self.recent_projects = self.recent_projects[:self.recent_projects_limit] # Modified
        logger.info(f"UserSessionCoordinator.add_recent_project: self.recent_projects AFTER trimming is: {self.recent_projects}") # Modified

        self.main_win._update_recent_menu()
        logger.info("add_recent_project: About to call save_session()")
        self.save_session()

    def perform_clear_recent_projects_action(self) -> None:
        if not self.main_win: return
        logger.info("Performing clear recent projects action.")
        self.recent_projects.clear()
        self.main_win._update_recent_menu()
        if hasattr(self.main_win, 'welcome_page') and self.main_win.welcome_page:
            self.main_win.welcome_page.update_list(self.recent_projects)
        self.main_win.status_bar.showMessage("Recent projects list cleared.", 3000)
        self.save_session()

    @Slot()
    def clear_recent_projects_from_welcome(self) -> None:
        if not self.main_win: return
        logger.info("Clearing recent projects triggered from welcome screen.")
        self.perform_clear_recent_projects_action()

    @Slot(str)
    def handle_rename_recent_project(self, old_path: str) -> None:
        if not self.main_win: return
        logger.info(f"Handling rename recent project request for: {old_path}")
        new_path_tuple: tuple[str, bool] = QInputDialog.getText(self.main_win, "Rename Recent Project Path",
                                            f"Enter new path for '{old_path}':", QLineEdit.Normal, old_path)
        new_path: str = new_path_tuple[0]
        ok: bool = new_path_tuple[1]

        if ok and new_path and new_path != old_path:
            logger.info(f"Renaming recent project from '{old_path}' to '{new_path}'")
            if old_path in self.recent_projects:
                idx: int = self.recent_projects.index(old_path)
                self.recent_projects[idx] = new_path
            else:
                logger.warning(f"Old path '{old_path}' not found in recent projects during rename. Adding new path '{new_path}'.")
                self.recent_projects.insert(0, new_path)
            # Ensure limit is respected even when adding a new path after old one not found
            self.recent_projects = self.recent_projects[:self.recent_projects_limit] # Modified
            self.main_win._update_recent_menu()
            self.save_session()
            if hasattr(self.main_win, 'welcome_page') and self.main_win.welcome_page:
                self.main_win.welcome_page.update_list(self.recent_projects)
        elif ok:
            logger.info("Rename recent project: No change in path.")

    @Slot(str)
    def handle_remove_recent_project_with_confirmation(self, path_to_remove: str) -> None:
        if not self.main_win: return
        logger.info(f"Handling remove recent project request for: {path_to_remove}")
        if path_to_remove in self.recent_projects:
            logger.info(f"Removing '{path_to_remove}' from recent projects.")
            self.recent_projects.remove(path_to_remove)
            self.main_win._update_recent_menu()
            self.save_session()
            if hasattr(self.main_win, 'welcome_page') and self.main_win.welcome_page:
                self.main_win.welcome_page.update_list(self.recent_projects)
        else:
            logger.warning(f"Path '{path_to_remove}' not found in recent projects during remove attempt.")

    @Slot(list)
    def update_recent_projects_from_welcome(self, updated_list: list[str]) -> None:
        if not self.main_win: return
        logger.info(f"Updating recent projects from welcome screen with list: {updated_list}")
        self.recent_projects[:] = updated_list[:self.recent_projects_limit] # Modified
        self.main_win._update_recent_menu()
        self.save_session()

# Ensure a newline at the end of the file
