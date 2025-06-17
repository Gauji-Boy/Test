import os
import logging
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox, QInputDialog, QLineEdit
from typing import Any, TYPE_CHECKING, Optional # Added TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from main_window import MainWindow # Assuming main_window.py

logger = logging.getLogger(__name__)

class UserSessionCoordinator(QObject):
    main_win: Optional['MainWindow'] # Forward reference for MainWindow, now Optional
    recent_projects: list[str]

    def __init__(self) -> None: # Removed main_window parameter
        super().__init__()
        self.main_win = None # Initialize as None
        self.recent_projects = [] # Initialize as empty list

    def set_main_window_ref(self, main_window: 'MainWindow') -> None:
        self.main_win = main_window
        # Initialize attributes that depend on main_window
        if self.main_win: # Ensure main_win is set
            self.recent_projects = self.main_win.recent_projects
        else: # Should not happen
            self.recent_projects = []


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
        if not self.main_win: return

        self.recent_projects.clear()
        self.recent_projects.extend(session_data.get("recent_projects", []))
        self.main_win._update_recent_menu()

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

        self.main_win._handle_pending_initial_path_after_session_load(session_data)

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
        logger.info(f"Adding recent project: {path}")
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        self.recent_projects = self.recent_projects[:10]
        self.main_win._update_recent_menu()
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
            self.recent_projects = self.recent_projects[:10]
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
        self.recent_projects[:] = updated_list[:10]
        self.main_win._update_recent_menu()
        self.save_session()

# Ensure a newline at the end of the file
