import sys
from PySide6.QtWidgets import QApplication
from main_window_refactored import MainWindow # Ensure this imports the correct MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Optional: Load and apply a global stylesheet here if you have one.
    # Example:
    # try:
    #     with open("styling.qss", "r") as f:
    #         app.setStyleSheet(f.read())
    # except FileNotFoundError:
    #     print("Stylesheet 'styling.qss' not found. Using default style.")
    # except Exception as e:
    #     print(f"Error loading stylesheet: {e}")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
