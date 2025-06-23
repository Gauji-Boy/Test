from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PySide6.QtGui import QFont, QColor, QTextCursor, QKeyEvent
from PySide6.QtCore import Qt, QProcess
import platform
import os

class CustomPlainTextEdit(QPlainTextEdit): # Renamed from output_display to make it clear this is the custom widget
    def __init__(self, parent=None):
        super().__init__(parent)
        self.prompt_end_position = 0

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            # Correct way to get the current line's text for command execution
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
            command_text = cursor.selectedText() # This gets the full line up to the cursor
            
            # We need to extract the command entered after the last prompt.
            # Assuming prompt_end_position marks the start of the editable command area.
            # This logic might need refinement based on how prompts are displayed.
            # For now, let's assume the command is what's after the prompt_end_position on the current line.
            # This CustomPlainTextEdit is primarily for the *interactive shell*, not general output.
            # So, the command logic here is for the shell.

            # The command extraction needs to be relative to the prompt.
            # Let's simplify: the text from prompt_end_position to current cursor position on the line is the command.
            # However, the original code implies the whole line after prompt is the command.
            # For an interactive shell, this is typical.

            # The parent (InteractiveTerminal) should manage sending the command.
            if hasattr(self.parent(), 'send_command_to_shell'): # Check if parent is InteractiveTerminal
                 # Get text from prompt_end_position to current cursor end of line
                current_line_text = self.toPlainText().splitlines()[-1] # Get current line
                # This logic for command extraction is tricky.
                # A simpler way for CustomPlainTextEdit: just emit signal with the line.
                # Let InteractiveTerminal handle prompt logic if needed.
                # For now, stick to the original intent:
                self.parent().send_command_to_shell(command_text.strip()) # Send the stripped selected text
            
            self.appendPlainText("") # Move to a new line
            self.prompt_end_position = self.textCursor().position() # Update for the new line's prompt
            event.accept()
        elif event.key() == Qt.Key.Key_Backspace:
            if self.textCursor().position() <= self.prompt_end_position:
                event.ignore()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)


class InteractiveTerminal(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interactive Terminal")

        self.shell_process = None # For the interactive user shell

        self.main_layout = QVBoxLayout(self)
        self.setLayout(self.main_layout)

        # QPlainTextEdit for terminal display and interaction (for the shell)
        self.output_display = CustomPlainTextEdit(self) # Use custom class
        self.main_layout.addWidget(self.output_display)

        self.output_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #282c34;
                color: #abb2bf;
                border: 1px solid #3e4452;
                padding: 5px;
            }
        """)
        font = QFont("Consolas", 10)
        self.output_display.setFont(font)
        self.output_display.setReadOnly(False) # Shell input is through this

    def start_shell(self, working_dir: str):
        if self.shell_process and self.shell_process.state() != QProcess.NotRunning:
            self.shell_process.kill()
            self.shell_process.waitForFinished()

        self.shell_process = QProcess(self)
        self.shell_process.setWorkingDirectory(working_dir)
        self.shell_process.readyReadStandardOutput.connect(self._on_shell_output)
        self.shell_process.readyReadStandardError.connect(self._on_shell_error) # Separate handler for clarity

        if platform.system() == "Windows":
            self.shell_process.start("cmd.exe")
        else:
            self.shell_process.start("/bin/bash")

        # Initial prompt might need to be written if shell doesn't provide one immediately
        # or if we want a custom prompt format.
        # For now, rely on shell's own prompt. After shell starts, _on_shell_output will handle its output.

    def _on_shell_output(self): # Renamed from _handle_output
        if not self.shell_process: return
        data = self.shell_process.readAllStandardOutput()
        if data:
            self.append_output(data.data().decode(errors='replace')) # Use append_output

    def _on_shell_error(self): # New handler for stderr of the shell
        if not self.shell_process: return
        error_data = self.shell_process.readAllStandardError()
        if error_data:
            self.append_output(error_data.data().decode(errors='replace')) # Use append_output, maybe different color later

    def send_command_to_shell(self, command: str):
        if self.shell_process and self.shell_process.state() == QProcess.ProcessState.Running:
            self.output_display.appendPlainText(command) # Echo command
            self.shell_process.write((command + "\n").encode())
            # The prompt handling in CustomPlainTextEdit might need adjustment after command echo.
            # For now, let the next output from shell create the new prompt line.
            # self.output_display.prompt_end_position = self.output_display.textCursor().position()


    # Methods for ProcessManager output handling (not for interactive shell commands)
    def append_output(self, text: str):
        """Appends text (e.g., from ProcessManager) to the terminal display."""
        self.output_display.moveCursor(QTextCursor.MoveOperation.End)
        self.output_display.insertPlainText(text)
        self.output_display.moveCursor(QTextCursor.MoveOperation.End)
        # Update prompt_end_position if this output is considered part of the "prompt" area for backspace protection.
        # This might need care if mixing shell output and ProcessManager output.
        # For ProcessManager output, it's typically read-only, so prompt_end_position update might not be desired here
        # or should be handled differently.
        # If append_output is *only* for non-interactive output, then self.output_display.prompt_end_position should not be updated here.
        # Let's assume ProcessManager output does not change the interactive prompt position.

    def clear_output(self):
        """Clears the terminal display (e.g., before running a new command via ProcessManager)."""
        self.output_display.clear()
        # After clearing, if there's an active shell, we might want to re-display its prompt.
        # This is complex. For now, clear simply clears. The shell might re-prompt on next interaction or output.
        # Or, MainWindow could explicitly re-prompt if needed after clearing for a command run.
        # For ProcessManager runs, clearing is usually for the *output of that run*, not the interactive shell.
        # So, the interactive shell's prompt should ideally be preserved or restored.
        # This indicates that perhaps ProcessManager output should go to a *different* display
        # or be visually distinct and not interfere with CustomPlainTextEdit's prompt logic.
        # For now, this will clear everything.

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