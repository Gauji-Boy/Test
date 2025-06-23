from PySide6.QtWidgets import QTreeView, QFileSystemModel, QMenu, QInputDialog, QMessageBox, QVBoxLayout, QWidget, QPushButton
from PySide6.QtCore import QDir, Signal, Slot, QModelIndex, QPoint, Qt
from PySide6.QtGui import QAction
import os
import shutil

class FileExplorer(QWidget): # Changed to QWidget to contain the tree view and button
    file_opened = Signal(str)
    back_to_welcome_requested = Signal() # New signal for welcome screen navigation

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self) # Main layout for the widget
        self.layout.setContentsMargins(0, 0, 0, 0) # Remove margins

        # Back to Welcome Button
        self.back_button = QPushButton("Back to Welcome Screen")
        self.back_button.clicked.connect(self.back_to_welcome_requested.emit)
        self.layout.addWidget(self.back_button)

        # Tree View for File System
        self.tree_view = QTreeView(self)
        self.model = QFileSystemModel()
        self.tree_view.setModel(self.model)

        # Hide unnecessary columns
        self.tree_view.setHeaderHidden(True)
        self.tree_view.hideColumn(1) # Size
        self.tree_view.hideColumn(2) # Type
        self.tree_view.hideColumn(3) # Date Modified

        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(20)
        self.tree_view.setSortingEnabled(True)

        self.set_root_path(QDir.currentPath()) # Set initial path to current directory
        self.tree_view.doubleClicked.connect(self.on_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu) # Enable custom context menu
        self.tree_view.customContextMenuRequested.connect(self.contextMenuEvent) # Connect to contextMenuEvent

        self.layout.addWidget(self.tree_view) # Add the tree view to the layout

    def set_root_path(self, path):
        self.model.setRootPath(path)
        self.tree_view.setRootIndex(self.model.index(path))

    @Slot(QModelIndex)
    def on_double_clicked(self, index):
        if not self.model.isDir(index):
            file_path = self.model.filePath(index)
            self.file_opened.emit(file_path)

    def contextMenuEvent(self, event):
        # Use the tree_view's indexAt for context menu
        index = self.tree_view.indexAt(event.pos()) # Use event.pos()
        menu = QMenu(self)
        add_file_action = QAction("Add New File", self)
        add_file_action.triggered.connect(lambda: self.add_new_file(event.pos())) # Pass event.pos()
        menu.addAction(add_file_action)
        menu.exec(self.tree_view.mapToGlobal(event.pos())) # Use tree_view's mapToGlobal and event.pos()

    @Slot(QPoint)
    def add_new_file(self, pos): # Changed event to pos
        index = self.tree_view.indexAt(pos) # Use pos
        if index.isValid():
            if self.model.isDir(index):
                target_dir = self.model.filePath(index)
            else:
                target_dir = self.model.filePath(index.parent())
        else:
            # If no item is clicked, use the current root path
            target_dir = self.model.rootPath()

        file_name, ok = QInputDialog.getText(self, "New File", "Enter new file name:")
        if ok and file_name:
            new_file_path = os.path.join(target_dir, file_name)
            try:
                with open(new_file_path, 'w') as f:
                    f.write("") # Create an empty file
                # Get the index of the parent directory to refresh its view
                parent_dir_index = self.model.index(target_dir)
                # Collapse and then expand the parent directory to force a refresh of its contents
                self.tree_view.collapse(parent_dir_index) # Use tree_view
                self.tree_view.expand(parent_dir_index) # Use tree_view
                self.file_opened.emit(new_file_path) # Open the new file in editor
            except PermissionError:
                QMessageBox.critical(self, "Error", f"Permission denied to create file: '{new_file_path}'")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An unexpected error occurred while creating file: {e}")