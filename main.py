import sys
from PySide6.QtWidgets import QApplication
# Assuming main_window.py is in the same directory and contains MainWindow
from main_window import MainWindow 

# Optional: Setup for high DPI displays if needed
# try:
#     from PySide6.QtGui import QGuiApplication
#     QGuiApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
#     QGuiApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
# except ImportError:
#     pass # Qt might be older, or not all attributes available

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # You can load and apply a global stylesheet here if you have one
    # For example:
    # try:
    #     with open("styling.qss", "r") as f:
    #         app.setStyleSheet(f.read())
    # except FileNotFoundError:
    #     print("LOG: Stylesheet 'styling.qss' not found. Using default styles.")
    # except Exception as e:
    #     print(f"LOG: Error loading stylesheet: {e}")


    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec())