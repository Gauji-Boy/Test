from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PySide6.QtGui import QFont, QColor, QTextCursor, QKeyEvent
from PySide6.QtCore import Qt, QProcess
import platform
import os

class CustomPlainTextEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.prompt_end_position = 0

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.KeepAnchor)
            command = cursor.selectedText().strip()
            
            # Emit a signal or call a method in the parent to handle the command
            if hasattr(self.parent(), 'send_command_to_shell'):
                self.parent().send_command_to_shell(command)
            
            self.appendPlainText("") # Move to a new line for the next prompt/input
            self.prompt_end_position = self.textCursor().position()
            event.accept()
        elif event.key() == Qt.Key.Key_Backspace:
            if self.textCursor().position() <= self.prompt_end_position:
                event.ignore() # Prevent deleting the prompt
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

class InteractiveTerminal(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interactive Terminal")

        # Process management
        self.shell_process = None

        # Set up the main layout
        self.main_layout = QVBoxLayout(self)
        self.setLayout(self.main_layout)

        # Create the QPlainTextEdit for terminal display
        self.terminal_display = CustomPlainTextEdit(self) # Use our custom class
        self.main_layout.addWidget(self.terminal_display)

        # Styling
        self.terminal_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #282c34; /* Dark grey/black */
                color: #abb2bf; /* Light grey/white */
                border: 1px solid #3e4452;
                padding: 5px;
            }
        """)
        font = QFont("Consolas", 10) # Using Consolas as a standard monospaced font
        self.terminal_display.setFont(font)

        # Initial State: Make it editable
        self.terminal_display.setReadOnly(False)

    def start_shell(self, working_dir: str):
        if self.shell_process and self.shell_process.state() != QProcess.NotRunning:
            self.shell_process.kill()
            self.shell_process.waitForFinished() # Ensure the process is terminated

        self.shell_process = QProcess(self)

        if platform.system() == "Windows":
            shell_executable = "cmd.exe"
        else:
            shell_executable = "/bin/bash" # Common for Linux/macOS

        self.shell_process.setWorkingDirectory(working_dir)
        self.shell_process.readyReadStandardOutput.connect(self._handle_output)
        self.shell_process.readyReadStandardError.connect(self._handle_output) # Also handle stderr

        self.shell_process.start(shell_executable)

    def _handle_output(self):
        data = self.shell_process.readAllStandardOutput()
        if data:
            self.terminal_display.insertPlainText(data.data().decode())
            self.terminal_display.verticalScrollBar().setValue(self.terminal_display.verticalScrollBar().maximum())
            self.terminal_display.prompt_end_position = self.terminal_display.textCursor().position()

        error_data = self.shell_process.readAllStandardError()
        if error_data:
            self.terminal_display.insertPlainText(error_data.data().decode())
            self.terminal_display.verticalScrollBar().setValue(self.terminal_display.verticalScrollBar().maximum())
            self.terminal_display.prompt_end_position = self.terminal_display.textCursor().position()

    def send_command_to_shell(self, command: str):
        if self.shell_process and self.shell_process.state() == QProcess.ProcessState.Running:
            self.shell_process.write((command + "\n").encode())

    def run_code_command(self, command: str):
        """Sends a command to the shell process for execution."""
        self.send_command_to_shell(command)

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    terminal = InteractiveTerminal()
    terminal.resize(800, 600)
    terminal.show()
    
    # Automatically start the shell when the widget is shown
    terminal.start_shell(os.getcwd())
    
    sys.exit(app.exec())