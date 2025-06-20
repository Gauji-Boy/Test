import sys
import os
import logging
from logging_config import setup_logging
from PySide6.QtWidgets import QApplication

# Initialize logging as the first thing
setup_logging(level=logging.DEBUG, log_to_file=True) # Or logging.INFO

from main_window import MainWindow
from welcome_screen import WelcomeScreen
from editor_file_coordinator import EditorFileCoordinator
from user_session_coordinator import UserSessionCoordinator
from collaboration_service import CollaborationService
from execution_coordinator import ExecutionCoordinator

class AppController:
    def __init__(self):
        self.app = QApplication(sys.argv)

        # Create coordinator instances
        self.editor_file_coordinator = EditorFileCoordinator()
        self.user_session_coordinator = UserSessionCoordinator()
        self.collaboration_service = CollaborationService()
        self.execution_coordinator = ExecutionCoordinator()

        # Instantiate MainWindow and inject coordinators
        self.main_window = MainWindow(
            editor_file_coordinator=self.editor_file_coordinator,
            user_session_coordinator=self.user_session_coordinator,
            collaboration_service=self.collaboration_service,
            execution_coordinator=self.execution_coordinator
            # initial_path is handled by launch_main_window or similar methods
        )
        self.main_window.set_app_controller_update_callback(self.handle_final_recent_projects_update) # Added

        # Provide MainWindow reference to coordinators
        self.editor_file_coordinator.set_main_window_ref(self.main_window)
        # self.user_session_coordinator.set_main_window_ref(self.main_window) # Removed
        self.collaboration_service.set_main_window_ref(self.main_window)
        self.execution_coordinator.set_main_window_ref(self.main_window)

        # WelcomeScreen setup
        # Note: main_window.recent_projects is accessed after user_session_coordinator is set up in MainWindow
        # and its set_main_window_ref is called, which initializes recent_projects.
        # This assumes UserSessionCoordinator's recent_projects is initialized correctly after set_main_window_ref.
        # If UserSessionCoordinator.recent_projects is only valid *after* its set_main_window_ref,
        # then WelcomeScreen might need to be initialized after set_main_window_ref calls.
        # For now, assuming main_window.recent_projects (which is UserSessionCoordinator.recent_projects)
        # is valid for WelcomeScreen here.
        self.welcome_screen = WelcomeScreen(recent_projects=self.main_window.user_session_coordinator.recent_projects)
        self.main_window.welcome_page = self.welcome_screen

        # Connect signals
        self.welcome_screen.path_selected.connect(self.launch_main_window)
        # Connect WelcomeScreen signals to UserSessionCoordinator methods via main_window instance
        self.welcome_screen.recent_projects_changed.connect(self.main_window.user_session_coordinator.update_recent_projects_from_welcome)
        self.welcome_screen.clear_recents_requested.connect(self.main_window.user_session_coordinator.clear_recent_projects_from_welcome)
        self.welcome_screen.rename_recent_requested.connect(self.main_window.user_session_coordinator.handle_rename_recent_project)
        self.welcome_screen.remove_recent_requested.connect(self.main_window.user_session_coordinator.handle_remove_recent_project_with_confirmation)
        # Connect the join session requested signal
        self.welcome_screen.join_session_requested.connect(self.launch_for_join_session)

        # Connect the new signal for when recent projects are loaded from session
        # self.user_session_coordinator.recent_projects_loaded.connect(self.handle_recent_projects_loaded_from_session) # Removed

    def handle_final_recent_projects_update(self, recent_projects_list: list): # Renamed and modified
        # Ensure logging is available (it should be from main.py's setup)
        logging.info(f"AppController.handle_final_recent_projects_update called with: {recent_projects_list}")
        if hasattr(self, 'welcome_screen') and self.welcome_screen:
            logging.info("AppController: Updating welcome screen's recent projects list via handle_final_recent_projects_update.")
            self.welcome_screen.update_list(recent_projects_list)
        else:
            logging.warning("AppController: Welcome screen not available in handle_final_recent_projects_update, cannot update.")

    def run(self):
        self.welcome_screen.show()
        sys.exit(self.app.exec())

    def launch_main_window(self, path):
        self.main_window.initialize_project(path)
        self.main_window.show()
        self.welcome_screen.close()

    def launch_for_join_session(self):
        """Handles the request to join a session from the welcome screen."""
        self.main_window.join_session_from_welcome_page()
        self.main_window.show()
        self.welcome_screen.close()

if __name__ == "__main__":
    controller = AppController()
    controller.run()