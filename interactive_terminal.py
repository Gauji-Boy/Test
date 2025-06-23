from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PySide6.QtCore import QProcess, Signal, Slot, Qt
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QKeyEvent
import sys
import os

class InteractiveTerminal(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.setup_ui()
        self.start_shell()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.terminal_output = QPlainTextEdit(self)
        self.terminal_output.setReadOnly(False) # Allow typing
        self.terminal_output.setStyleSheet("background-color: black; color: white; font-family: 'Consolas', 'Monospace';")
        self.layout.addWidget(self.terminal_output)

        self.setLayout(self.layout)

        self.terminal_output.installEventFilter(self) # Capture key events
        self.terminal_output.textChanged.connect(self._on_text_changed)

        self.current_prompt_start = 0

    def start_shell(self):
        if self.process is not None and self.process.state() == QProcess.Running:
            self.process.kill()
            self.process.waitForFinished()

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels) # Merge stdout and stderr

        if sys.platform.startswith('win'):
            self.shell = ["cmd.exe"]
        else:
            self.shell = ["bash"]

        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._process_finished)

        try:
            self.process.start(self.shell[0], self.shell[1:])
            if not self.process.waitForStarted(5000):
                self.append_output(f"Error: Could not start shell: {self.process.errorString()}\n", color="red")
            else:
                self.append_output(f"--- Started {self.shell[0]} ---\n", color="green")
                self.terminal_output.moveCursor(QTextCursor.End)
                self.current_prompt_start = self.terminal_output.textCursor().position()
        except Exception as e:
            self.append_output(f"Exception starting shell: {e}\n", color="red")

    @Slot()
    def _read_output(self):
        data = self.process.readAllStandardOutput().data()
        text = data.decode(sys.getdefaultencoding(), errors='replace')
        
        # Save current cursor position
        cursor = self.terminal_output.textCursor()
        old_pos = cursor.position()

        # Append text at the end
        self.terminal_output.moveCursor(QTextCursor.End)
        self.terminal_output.insertPlainText(text)
        
        # Update prompt start position
        self.current_prompt_start = self.terminal_output.textCursor().position()

        # Restore cursor position if it was before the new output
        if old_pos < self.current_prompt_start:
            cursor.setPosition(old_pos)
            self.terminal_output.setTextCursor(cursor)

    def append_output(self, text, color=None):
        cursor = self.terminal_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        if color:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.insertText(text, fmt)
        else:
            cursor.insertText(text)
        
        self.terminal_output.setTextCursor(cursor)
        self.terminal_output.ensureCursorVisible()
        self.current_prompt_start = self.terminal_output.textCursor().position()


    def eventFilter(self, obj, event):
        if obj is self.terminal_output and event.type() == QKeyEvent.KeyPress:
            key_event = event
            if key_event.key() == Qt.Key.Key_Return or key_event.key() == Qt.Key.Key_Enter:
                self._handle_enter_key()
                return True # Event handled
            elif key_event.key() == Qt.Key.Key_Backspace:
                cursor = self.terminal_output.textCursor()
                if cursor.position() <= self.current_prompt_start:
                    return True # Prevent deleting prompt
            elif key_event.key() == Qt.Key.Key_Left:
                cursor = self.terminal_output.textCursor()
                if cursor.position() <= self.current_prompt_start:
                    return True # Prevent moving left past prompt
            elif key_event.key() == Qt.Key.Key_Up:
                # Implement history navigation if desired
                return True # Prevent default behavior for now
            elif key_event.key() == Qt.Key.Key_Down:
                # Implement history navigation if desired
                return True # Prevent default behavior for now
            
            # Allow other keys to be processed by the QPlainTextEdit
            # Ensure cursor is at the end for typing
            cursor = self.terminal_output.textCursor()
            if cursor.position() < self.terminal_output.document().characterCount() - 1:
                self.terminal_output.moveCursor(QTextCursor.End)
                self.terminal_output.setTextCursor(self.terminal_output.textCursor()) # Force update
        return super().eventFilter(obj, event)

    def _on_text_changed(self):
        # Ensure text before prompt is not modified
        cursor = self.terminal_output.textCursor()
        if cursor.position() < self.current_prompt_start:
            cursor.setPosition(self.current_prompt_start)
            self.terminal_output.setTextCursor(cursor)

    def _handle_enter_key(self):
        cursor = self.terminal_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        command_line = self.terminal_output.toPlainText()[self.current_prompt_start:].strip()
        
        self.append_output("\n") # Add newline for visual separation

        if command_line:
            self.run_command(command_line)
        
        self.current_prompt_start = self.terminal_output.textCursor().position()


    def run_command(self, command):
        """
        Executes a command directly in the running shell.
        """
        if self.process and self.process.state() == QProcess.Running:
            self.process.write((command + '\n').encode(sys.getdefaultencoding()))
        else:
            self.append_output("Shell not running. Attempting to restart and run command...\n", color="red")
            self.start_shell()
            if self.process and self.process.state() == QProcess.Running:
                self.process.write((command + '\n').encode(sys.getdefaultencoding()))

    @Slot(int, QProcess.ExitStatus)
    def _process_finished(self, exit_code, exit_status):
        self.append_output(f"\nShell exited with code {exit_code} ({exit_status}).\n", color="red")
        self.append_output("Type a command to restart the shell.\n", color="yellow")
        self.current_prompt_start = self.terminal_output.textCursor().position()