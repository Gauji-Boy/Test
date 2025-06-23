from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

class WelcomePage(QWidget):
    new_file_requested = Signal()
    open_file_requested = Signal()
    open_folder_requested = Signal()
    join_session_requested = Signal()  # Added new signal
    recent_path_selected = Signal(str)

    def __init__(self, recent_folders, parent=None):
        super().__init__(parent)
        self.recent_folders = recent_folders

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

        # Join Session Button
        self.join_session_button = QPushButton("Join Session...") # Added new button
        self.join_session_button.setMinimumHeight(45)
        self.join_session_button.setMinimumWidth(250)
        self.join_session_button.setFont(font)

        buttons_v_layout.addWidget(self.new_file_button)
        buttons_v_layout.addWidget(self.open_file_button)
        buttons_v_layout.addWidget(self.open_folder_button)
        buttons_v_layout.addWidget(self.join_session_button) # Added new button to layout

        main_layout.addLayout(buttons_v_layout)

        # Recent Projects Label
        recent_title_label = QLabel("Recent Projects:")
        recent_title_label.setAlignment(Qt.AlignCenter)
        # Optionally set font for this label, e.g., using the same 'font' as buttons or a new one
        # title_font = QFont()
        # title_font.setPointSize(12) # Example size
        # recent_title_label.setFont(title_font)
        main_layout.addWidget(recent_title_label)

        # Recent Projects List
        self.recent_list_widget = QListWidget()
        self.recent_list_widget.setMaximumHeight(150) # Example height
        for folder_path in self.recent_folders:
            self.recent_list_widget.addItem(QListWidgetItem(folder_path))
        main_layout.addWidget(self.recent_list_widget)

        main_layout.addStretch(1) # Adjust stretch as needed

        # Connect signals
        self.new_file_button.clicked.connect(self.new_file_requested.emit)
        self.open_file_button.clicked.connect(self.open_file_requested.emit)
        self.open_folder_button.clicked.connect(self.open_folder_requested.emit)
        self.join_session_button.clicked.connect(self.join_session_requested.emit) # Connected new signal
        self.recent_list_widget.itemDoubleClicked.connect(self._on_recent_item_doubled_clicked)

    @Slot(QListWidgetItem)
    def _on_recent_item_doubled_clicked(self, item):
        self.recent_path_selected.emit(item.text())

if __name__ == '__main__':
    # Example usage for testing WelcomePage independently
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow
    app = QApplication(sys.argv)

    # To test it in a tab-like environment
    test_window = QMainWindow()
    test_window.setWindowTitle("Welcome Page Test")
    welcome_widget = WelcomePage([]) # Pass empty list for recent_folders
    test_window.setCentralWidget(welcome_widget) # Just for testing, not in a tab
    test_window.resize(600, 400)
    test_window.show()

    welcome_widget.new_file_requested.connect(lambda: print("New File Requested"))
    welcome_widget.open_file_requested.connect(lambda: print("Open File Requested"))
    welcome_widget.open_folder_requested.connect(lambda: print("Open Folder Requested"))
    welcome_widget.join_session_requested.connect(lambda: print("Join Session Requested")) # Added for testing
    welcome_widget.recent_path_selected.connect(lambda path: print(f"Recent Path Selected: {path}"))

    sys.exit(app.exec())
