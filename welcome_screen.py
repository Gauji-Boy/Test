from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QListWidget, QSizePolicy, QMessageBox, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
import os

class WelcomeScreen(QWidget):
    path_selected = Signal(str)
    recent_projects_changed = Signal(list) # New signal to notify MainWindow of changes
    clear_recents_requested = Signal()
    rename_recent_requested = Signal(str)
    remove_recent_requested = Signal(str)
    join_session_requested = Signal() # Added new signal

    def __init__(self, recent_projects=None):
        super().__init__()
        self.setWindowTitle("Welcome to Aether Editor")
        self.recent_projects = recent_projects if recent_projects is not None else []
        self.setup_ui()
        self._populate_recent_projects()

    def update_list(self, recent_folders: list):
        self.recent_projects = recent_folders
        self.recent_projects_list.clear() # Clear the QListWidget
        self._populate_recent_projects() # Re-populate with the new list

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)

        # Title
        title_label = QLabel("Welcome to Aether Editor")
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Spacer
        main_layout.addSpacing(50)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)

        open_folder_button = QPushButton("Open Folder...")
        open_folder_button.setFixedSize(150, 40)
        open_folder_button.clicked.connect(self._open_folder_dialog)
        button_layout.addWidget(open_folder_button)

        open_file_button = QPushButton("Open File...")
        open_file_button.setFixedSize(150, 40)
        open_file_button.clicked.connect(self._open_file_dialog)
        button_layout.addWidget(open_file_button)

        join_session_button = QPushButton("Join Session...")
        join_session_button.setFixedSize(150, 40) # Match styling
        join_session_button.clicked.connect(self.join_session_requested.emit) # Connect signal
        button_layout.addWidget(join_session_button) # Add to layout

        main_layout.addLayout(button_layout)

        # Spacer
        main_layout.addSpacing(30)

        # Recent Projects (Optional Placeholder)
        recent_projects_label = QLabel("Recent Projects:")
        recent_projects_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(recent_projects_label)

        self.recent_projects_list = QListWidget()
        self.recent_projects_list.setFixedSize(350, 150)
        self.recent_projects_list.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        main_layout.addWidget(self.recent_projects_list, alignment=Qt.AlignCenter)
        self.recent_projects_list.itemDoubleClicked.connect(self._open_recent_project)
        self.recent_projects_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent_projects_list.customContextMenuRequested.connect(self._show_context_menu)

        # Clear Recent Projects Button
        clear_button = QPushButton("Clear Recent Projects")
        clear_button.setFixedSize(200, 40)
        clear_button.clicked.connect(self.clear_recents_requested.emit)
        main_layout.addWidget(clear_button, alignment=Qt.AlignCenter)


        self.setLayout(main_layout)
        self.setFixedSize(600, 450) # Fixed size for the welcome screen

    def _populate_recent_projects(self):
        self.recent_projects_list.clear()
        if not self.recent_projects:
            self.recent_projects_list.addItem("No recent projects.")
            self.recent_projects_list.item(0).setFlags(Qt.NoItemFlags) # Make it non-selectable
        else:
            for project_path in self.recent_projects:
                self.recent_projects_list.addItem(project_path)

    def _open_recent_project(self, item):
        project_path = item.text()
        if project_path and os.path.exists(project_path):
            self.path_selected.emit(project_path)
        else:
            QMessageBox.warning(self, "Project Not Found", f"The path '{project_path}' does not exist or is invalid.")
            self.recent_projects.remove(project_path)
            self._populate_recent_projects()
            self.recent_projects_changed.emit(self.recent_projects) # Notify MainWindow



    def _show_context_menu(self, position):
        item = self.recent_projects_list.itemAt(position)
        if item:
            folder_path = item.text()
            menu = QMenu(self)

            rename_action = menu.addAction("Rename (Re-select Folder)")
            rename_action.triggered.connect(lambda: self.rename_recent_requested.emit(folder_path))

            remove_action = menu.addAction("Remove from List")
            remove_action.triggered.connect(lambda: self.remove_recent_requested.emit(folder_path))

            menu.exec(self.recent_projects_list.mapToGlobal(position))

    def _open_folder_dialog(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Open Folder")
        if folder_path:
            self.path_selected.emit(folder_path)

    def _open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File")
        if file_path:
            self.path_selected.emit(file_path)

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    welcome_screen = WelcomeScreen()
    welcome_screen.show()
    sys.exit(app.exec())