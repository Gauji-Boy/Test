from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QHBoxLayout, QListWidget
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

class WelcomeScreen(QWidget):
    # Signal to emit the selected path (file or folder)
    path_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome - Aether Editor")
        self.setFixedSize(500, 350) # Give it a decent fixed size

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setSpacing(20)

        # Title Label
        title_label = QLabel("Welcome to Aether Editor")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Buttons Layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)

        # Open Folder Button
        self.open_folder_button = QPushButton("Open Folder...")
        self.open_folder_button.setMinimumHeight(40) # Make buttons a bit taller
        font = self.open_folder_button.font()
        font.setPointSize(10)
        self.open_folder_button.setFont(font)
        buttons_layout.addWidget(self.open_folder_button)

        # Open File Button
        self.open_file_button = QPushButton("Open File...")
        self.open_file_button.setMinimumHeight(40)
        self.open_file_button.setFont(font) # Use the same font size
        buttons_layout.addWidget(self.open_file_button)

        main_layout.addLayout(buttons_layout)

        # Placeholder for Recent Projects (Optional)
        recent_projects_label = QLabel("Recent Projects (Placeholder):")
        recent_projects_label.setAlignment(Qt.AlignCenter)
        # main_layout.addWidget(recent_projects_label) # Uncomment if you want the label

        self.recent_projects_list = QListWidget()
        self.recent_projects_list.setEnabled(False) # Disabled for now as it's a placeholder
        # main_layout.addWidget(self.recent_projects_list) # Uncomment if you want the list widget visible

        # Connect signals
        self.open_folder_button.clicked.connect(self._open_folder_dialog)
        self.open_file_button.clicked.connect(self._open_file_dialog)

    @Slot()
    def _open_folder_dialog(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Open Folder",
            "", # Start directory (can be QStandardPaths.HomeLocation)
            QFileDialog.ShowDirsOnly
        )
        if folder_path:
            self.path_selected.emit(folder_path)

    @Slot()
    def _open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "", # Start directory
            "All Files (*.*);;Python Files (*.py);;Text Files (*.txt)" # Filter
        )
        if file_path:
            self.path_selected.emit(file_path)

if __name__ == '__main__':
    # Example usage for testing the WelcomeScreen independently
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    welcome_screen = WelcomeScreen()
    welcome_screen.show()

    def handle_path(path):
        print(f"Path selected: {path}")
        # welcome_screen.close() # Optionally close after selection for testing

    welcome_screen.path_selected.connect(handle_path)
    sys.exit(app.exec())
