import sys
import os
import logging
from logging_config import setup_logging
from PySide6.QtWidgets import QApplication

# Initialize logging as the first thing
setup_logging(level=logging.DEBUG, log_to_file=True) # Or logging.INFO

from main_window import MainWindow
from welcome_screen import WelcomeScreen

class AppController:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.main_window = MainWindow() # Do not show yet
        self.welcome_screen = WelcomeScreen(recent_projects=self.main_window.recent_projects)
        self.main_window.welcome_page = self.welcome_screen # Pass the welcome_screen instance to main_window

        # Connect signals
        self.welcome_screen.path_selected.connect(self.launch_main_window)
        # Connect WelcomeScreen signals to UserSessionCoordinator methods via main_window instance
        self.welcome_screen.recent_projects_changed.connect(self.main_window.user_session_coordinator.update_recent_projects_from_welcome)
        self.welcome_screen.clear_recents_requested.connect(self.main_window.user_session_coordinator.clear_recent_projects_from_welcome)
        self.welcome_screen.rename_recent_requested.connect(self.main_window.user_session_coordinator.handle_rename_recent_project)
        self.welcome_screen.remove_recent_requested.connect(self.main_window.user_session_coordinator.handle_remove_recent_project_with_confirmation)
        # Connect the join session requested signal
        self.welcome_screen.join_session_requested.connect(self.launch_for_join_session)

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