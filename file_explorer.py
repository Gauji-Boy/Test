import os
from PySide6.QtWidgets import (
    QWidget, QTreeView, QVBoxLayout, QFileSystemModel, QMenu, 
    QMessageBox, QInputDialog, QLineEdit, QApplication # QApplication for test block
)
from PySide6.QtGui import QAction, QIcon, QKeySequence # QKeySequence for future shortcuts
from PySide6.QtCore import Qt, Signal, Slot, QDir, QModelIndex, QPoint

class FileExplorer(QWidget):
    # Signals to MainWindow to request operations (handled by FileManager via MainWindow)
    file_open_requested = Signal(str)           # path
    create_new_file_requested = Signal(str)   # parent_dir_path
    create_new_folder_requested = Signal(str) # parent_dir_path
    rename_item_requested = Signal(str, str)    # old_path, new_name
    delete_item_requested = Signal(str)         # path_to_delete
    open_in_terminal_requested = Signal(str)  # path (directory)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FileExplorerTreeView") # For QSS (matches main_window.py's setObjectName)

        self.tree_view = QTreeView(self)
        self.model = QFileSystemModel(self)
        
        self.model.setFilter(QDir.AllEntries | QDir.Hidden | QDir.System) # Show all, including hidden
        self.model.setResolveSymlinks(True)

        self.tree_view.setModel(self.model)
        self.tree_view.setHeaderHidden(True)
        for i in range(1, self.model.columnCount()):
            self.tree_view.setColumnHidden(i, True)

        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._on_context_menu)
        self.tree_view.doubleClicked.connect(self._on_item_double_clicked)
        self.tree_view.setDragEnabled(False) # Disable drag and drop for now, can be enabled later
        self.tree_view.setAcceptDrops(False)
        self.tree_view.setDropIndicatorShown(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

        self.current_root_path = "" 
        self.set_root_path(QDir.homePath())

    @Slot(str)
    def set_root_path(self, path: str):
        valid_path = path
        if not path or not os.path.isdir(path):
            print(f"FileExplorer: Invalid root path '{path}', defaulting to home.")
            valid_path = QDir.homePath()
        
        self.current_root_path = os.path.normpath(valid_path)
        self.model.setRootPath(self.current_root_path) 
        root_index = self.model.index(self.current_root_path)
        self.tree_view.setRootIndex(root_index)
        self.tree_view.scrollTo(root_index, QTreeView.PositionAtTop)
        print(f"FileExplorer: Root path set to '{self.current_root_path}'")

    @Slot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex):
        if not index.isValid(): return
        path = self.model.filePath(index)
        if not self.model.isDir(index):
            self.file_open_requested.emit(path)
        # Default QTreeView behavior handles expanding/collapsing folders

    @Slot(QPoint)
    def _on_context_menu(self, point: QPoint):
        index = self.tree_view.indexAt(point)
        global_pos = self.tree_view.mapToGlobal(point)
        self._show_context_menu(index, global_pos)

    def _show_context_menu(self, index: QModelIndex | None, global_pos: QPoint):
        menu = QMenu(self)
        path = None
        is_dir = False
        target_path_for_new_item = self.current_root_path # Default to current root

        if index and index.isValid():
            path = self.model.filePath(index)
            is_dir = self.model.isDir(index)
            if is_dir:
                target_path_for_new_item = path
            else:
                target_path_for_new_item = os.path.dirname(path)
        
        if path and not is_dir: # Item is a file
            open_action = menu.addAction("Open File")
            open_action.triggered.connect(lambda: self.file_open_requested.emit(path))
        
        if path: # Actions for existing items (file or folder)
            menu.addSeparator()
            rename_action = menu.addAction("Rename...")
            rename_action.triggered.connect(lambda: self._request_rename_item(path))
            
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self._request_delete_item(path))
        
        menu.addSeparator() # Separator before create actions
        new_file_action = menu.addAction("New File...")
        new_file_action.triggered.connect(lambda: self._request_new_file(target_path_for_new_item))

        new_folder_action = menu.addAction("New Folder...")
        new_folder_action.triggered.connect(lambda: self._request_new_folder(target_path_for_new_item))
            
        if path and is_dir: # Only show 'Open in Terminal' if a directory is selected
            menu.addSeparator()
            open_terminal_action = menu.addAction("Open in Terminal")
            open_terminal_action.triggered.connect(lambda: self.open_in_terminal_requested.emit(path))
        
        if not menu.actions(): # Don't show empty menu (e.g. if path is None and no general actions)
            return
            
        menu.exec(global_pos)

    def _request_new_file(self, parent_dir_path: str):
        # MainWindow will handle the QInputDialog for filename via a slot connected to this signal
        self.create_new_file_requested.emit(parent_dir_path)

    def _request_new_folder(self, parent_dir_path: str):
        # MainWindow will handle the QInputDialog for folder name
        self.create_new_folder_requested.emit(parent_dir_path)

    def _request_rename_item(self, old_path: str):
        # MainWindow will handle QInputDialog for new name
        # Here, we just emit the old_path. MainWindow will get new_name and then emit to FileManager.
        # Or, FileExplorer can get new_name and emit (old_path, new_name).
        # Let's do the latter for consistency with delete's confirmation dialog.
        old_name = os.path.basename(old_path)
        new_name, ok = QInputDialog.getText(self, "Rename Item", 
                                            f"Enter new name for '{old_name}':", 
                                            QLineEdit.Normal, old_name)
        if ok and new_name and new_name != old_name:
            self.rename_item_requested.emit(old_path, new_name)

    def _request_delete_item(self, path_to_delete: str):
        item_name = os.path.basename(path_to_delete)
        reply = QMessageBox.question(self, "Confirm Delete", 
                                     f"Are you sure you want to delete '{item_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.delete_item_requested.emit(path_to_delete)

    @Slot() 
    def refresh_path(self, path: str):
        """Refreshes a specific path in the model, usually a directory after changes."""
        if not path or not os.path.exists(path): # Path might have been deleted
            # If path deleted, refresh its parent
            path = os.path.dirname(path)
            if not path or not os.path.exists(path):
                 path = self.current_root_path # Fallback to root

        index = self.model.index(path)
        if index.isValid():
            # QFileSystemModel doesn't have a public refresh(index) method.
            # Forcing directory reload can be done by resetting filters or root path tricks,
            # but that's heavy. QFileSystemModel should auto-update.
            # If external changes are not picked up, this is a deeper issue with QFileSystemWatcher.
            # For now, this is a placeholder if explicit refresh is needed.
            print(f"FileExplorer: Refresh requested for path '{path}'. (QFileSystemModel typically auto-updates)")
            # self.model.directoryLoaded.emit(path) # This is a signal, not a refresh method.
            # One way to try to force a refresh of a directory:
            # self.model.fetchMore(index)
            # self.tree_view.update(index) # Redraw that part
            pass


if __name__ == '__main__': 
    import sys
    app = QApplication(sys.argv)
    # Example: Load stylesheet for testing
    # try:
    #     with open("../styling.qss", "r") as f:
    #         app.setStyleSheet(f.read())
    # except FileNotFoundError:
    #     print("Styling.qss not found for FileExplorer test.")

    explorer = FileExplorer()
    explorer.setWindowTitle("File Explorer Test")
    explorer.setGeometry(100, 100, 350, 500)
    explorer.show()
    explorer.set_root_path(QDir.currentPath()) # Set to current dir for testing

    explorer.file_open_requested.connect(lambda p: print(f"MAIN_TEST: Open file: {p}"))
    explorer.create_new_file_requested.connect(lambda p_dir: print(f"MAIN_TEST: New file in: {p_dir}"))
    explorer.create_new_folder_requested.connect(lambda p_dir: print(f"MAIN_TEST: New folder in: {p_dir}"))
    explorer.rename_item_requested.connect(lambda old, new: print(f"MAIN_TEST: Rename: {old} to {new}"))
    explorer.delete_item_requested.connect(lambda p_del: print(f"MAIN_TEST: Delete: {p_del}"))
    explorer.open_in_terminal_requested.connect(lambda p_term: print(f"MAIN_TEST: Open terminal in: {p_term}"))

    sys.exit(app.exec())