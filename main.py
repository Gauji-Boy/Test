import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Slot # QObject and Slot for launch_main_window
from welcome_screen import WelcomeScreen # Assuming welcome_screen.py is in the same directory
from main_window import MainWindow     # Assuming main_window.py is in the same directory

class AppController(QObject):
    def __init__(self):
        super().__init__() # Initialize QObject
        # QApplication must be created before any QWidgets
        # It's common to create it once here.
        if QApplication.instance():
            self.app = QApplication.instance()
        else:
            self.app = QApplication(sys.argv)

        self.welcome_screen = WelcomeScreen()
        # MainWindow will be created when a path is selected,
        # or if needed for a "no path" scenario (though current flow avoids this).
        self.main_window = None

        # Connect the signal from WelcomeScreen to a slot in AppController
        self.welcome_screen.path_selected.connect(self.launch_main_window)

    def run(self):
        self.welcome_screen.show()
        sys.exit(self.app.exec()) # Start the application event loop

    @Slot(str) # Decorate as a slot
    def launch_main_window(self, path: str):
        if path: # Ensure path is not empty
            # Create or re-initialize MainWindow instance here
            if self.main_window is None:
                self.main_window = MainWindow(initial_path=path)
            else:
                # If main_window instance already exists (e.g., if user could go back to welcome screen)
                # we should re-initialize it with the new path.
                # This assumes MainWindow can handle being re-initialized or has a method like initialize_project
                self.main_window.initialize_project(path) # Ensure this method exists and works as expected

            self.main_window.show()
            self.welcome_screen.close() # Close the welcome screen
        else:
            # Handle case where path might be empty, though WelcomeScreen should prevent this
            print("LOG: No valid path received from welcome screen. Re-showing welcome screen.")
            # If path is empty, it implies an issue or a desire to go back/stay on welcome.
            # For robustness, ensure welcome screen is visible if main window isn't shown.
            if not (self.main_window and self.main_window.isVisible()):
                 self.welcome_screen.show()


if __name__ == "__main__":
    # Ensure PySide6 is correctly initialized for fonts, styles etc.
    # QApplication.setAttribute(Qt.AA_EnableHighDpiScaling) # Optional, for HiDPI
    # QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)  # Optional, for HiDPI

    controller = AppController()
    controller.run()