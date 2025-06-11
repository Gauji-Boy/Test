from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

class WelcomePage(QWidget):
    new_file_requested = Signal()
    open_file_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setSpacing(30) # Increased spacing

        # Title Label
        title_label = QLabel("Aether Editor")
        title_font = QFont()
        title_font.setPointSize(28) # Larger title font
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addStretch(1) # Add stretch before title
        main_layout.addWidget(title_label)

        # Buttons Layout - Vertical for this style
        buttons_v_layout = QVBoxLayout()
        buttons_v_layout.setSpacing(15)
        buttons_v_layout.setAlignment(Qt.AlignCenter) # Center buttons horizontally

        # New File Button
        self.new_file_button = QPushButton("New File...")
        self.new_file_button.setMinimumHeight(45)
        self.new_file_button.setMinimumWidth(250) # Set a min width for buttons
        font = self.new_file_button.font()
        font.setPointSize(11)
        self.new_file_button.setFont(font)

        # Open File Button
        self.open_file_button = QPushButton("Open File...")
        self.open_file_button.setMinimumHeight(45)
        self.open_file_button.setMinimumWidth(250)
        self.open_file_button.setFont(font)

        # Open Folder Button
        self.open_folder_button = QPushButton("Open Folder...")
        self.open_folder_button.setMinimumHeight(45)
        self.open_folder_button.setMinimumWidth(250)
        self.open_folder_button.setFont(font)

        buttons_v_layout.addWidget(self.new_file_button)
        buttons_v_layout.addWidget(self.open_file_button)
        buttons_v_layout.addWidget(self.open_folder_button)

        main_layout.addLayout(buttons_v_layout)
        main_layout.addStretch(2) # Add more stretch after buttons

        # Connect signals
        self.new_file_button.clicked.connect(self.new_file_requested.emit)
        self.open_file_button.clicked.connect(self.open_file_requested.emit)
        self.open_folder_button.clicked.connect(self.open_folder_requested.emit)

if __name__ == '__main__':
    # Example usage for testing WelcomePage independently
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow
    app = QApplication(sys.argv)

    # To test it in a tab-like environment
    test_window = QMainWindow()
    test_window.setWindowTitle("Welcome Page Test")
    welcome_widget = WelcomePage()
    test_window.setCentralWidget(welcome_widget) # Just for testing, not in a tab
    test_window.resize(600, 400)
    test_window.show()

    welcome_widget.new_file_requested.connect(lambda: print("New File Requested"))
    welcome_widget.open_file_requested.connect(lambda: print("Open File Requested"))
    welcome_widget.open_folder_requested.connect(lambda: print("Open Folder Requested"))

    sys.exit(app.exec())
