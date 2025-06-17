from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QPushButton
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
# Removed: QProcess, Signal, Slot, Qt from PySide6.QtCore
# Removed: sys, os

class CommandOutputViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # self.process = None # Removed
        self.setup_ui()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        
        self.output_display = QPlainTextEdit(self)
        self.output_display.setReadOnly(True)
        self.output_display.setStyleSheet("background-color: black; color: white; font-family: 'Consolas', 'Monospace';")
        self.layout.addWidget(self.output_display)

        self.clear_button = QPushButton("Clear Output", self)
        self.clear_button.clicked.connect(self.clear_output) # Changed to self.clear_output
        self.layout.addWidget(self.clear_button)

        self.setLayout(self.layout)

    def append_output(self, text, color=None):
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End) # Using fully qualified enum
        
        if color:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.insertText(text, fmt)
        else:
            cursor.insertText(text)
        
        self.output_display.setTextCursor(cursor)
        self.output_display.ensureCursorVisible()

    def clear_output(self):
        """Clears the output display."""
        self.output_display.clear()

    # Removed methods:
    # - execute_command
    # - _on_output_ready
    # - _on_finished
    # - _on_error