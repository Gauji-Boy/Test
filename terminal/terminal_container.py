from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QToolButton, QInputDialog, QLineEdit
from PySide6.QtCore import Slot, Signal, Qt
from PySide6.QtGui import QIcon
from terminal.interactive_terminal import TerminalInstance # Renamed class

class TerminalContainer(QWidget):
    run_command_signal = Signal(str) # Signal to delegate commands to active tab

    def __init__(self, parent=None):
        super().__init__(parent)
        self.terminal_count = 0
        self.setup_ui()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True) # Allow tabs to be moved and double-clicked for rename
        self.tabs.tabCloseRequested.connect(self.close_terminal_tab)
        self.tabs.tabBarDoubleClicked.connect(self._handle_tab_double_click)

        # Add "New Terminal" button
        self.new_terminal_button = QToolButton(self)
        self.new_terminal_button.setIcon(QIcon.fromTheme("list-add")) # Or a custom icon
        self.new_terminal_button.setText("New Terminal")
        self.new_terminal_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.new_terminal_button.clicked.connect(self.create_new_terminal)
        
        # Set the button as a corner widget
        self.tabs.setCornerWidget(self.new_terminal_button, Qt.TopRightCorner)

        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)

        # Create initial terminal tab
        self.create_new_terminal()

    @Slot()
    def create_new_terminal(self):
        self.terminal_count += 1
        terminal_instance = TerminalInstance(self)
        tab_name = f"Terminal {self.terminal_count}"
        tab_index = self.tabs.addTab(terminal_instance, tab_name)
        self.tabs.setCurrentIndex(tab_index)
        # Connect the run_command_signal to the new terminal instance's run_command slot
        self.run_command_signal.connect(terminal_instance.run_command)
        # Connect the process_changed signal for tab renaming
        terminal_instance.process_changed.connect(
            lambda new_name: self.rename_tab(terminal_instance, new_name)
        )

    @Slot(int)
    def close_terminal_tab(self, index):
        widget_to_remove = self.tabs.widget(index)
        if isinstance(widget_to_remove, TerminalInstance):
            # Disconnect the signal before shutting down
            self.run_command_signal.disconnect(widget_to_remove.run_command)
            widget_to_remove.process.kill()
            widget_to_remove.process.waitForFinished(1000) # Wait for process to finish
            widget_to_remove.deleteLater() # Properly delete the widget
        self.tabs.removeTab(index)

    @Slot(str)
    def run_command(self, command: str):
        current_terminal = self.tabs.currentWidget()
        if isinstance(current_terminal, TerminalInstance):
            current_terminal.run_command(command)

    @Slot(QWidget, str)
    def rename_tab(self, terminal_instance, new_name):
        """
        Renames the tab associated with the given terminal_instance.
        """
        index = self.tabs.indexOf(terminal_instance)
        if index != -1:
            self.tabs.setTabText(index, new_name)

    @Slot(int)
    def _handle_tab_double_click(self, index):
        """
        Handles double-clicking on a tab to allow manual renaming.
        """
        # This is a placeholder. A real implementation would involve
        # a QInputDialog or similar to get the new name from the user.
        # For now, we'll just print a message.
        print(f"Double-clicked tab {index}. Implement manual rename here.")
        # Example of how you might get a new name (requires QInputDialog import)
        # from PySide6.QtWidgets import QInputDialog
        # new_name, ok = QInputDialog.getText(self, "Rename Tab", "New tab name:",
        #                                      QLineEdit.Normal, self.tabs.tabText(index))
        # if ok and new_name:
        #     self.tabs.setTabText(index, new_name)