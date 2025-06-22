from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QDockWidget
from PySide6.QtCore import QProcess, Signal, Slot, Qt, QEvent
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
import sys
import os

class TerminalWidget(QWidget):
    output_received = Signal(str, object) # Add color object to signal

    def __init__(self, parent=None):
        super().__init__(parent)
        self.shell_process = QProcess(self)
        self.input_start_position = 0
        self.command_history = []
        self.history_index = 0 # Initialize to 0, points to the next command to be added
        self.setup_ui()
        self._start_shell_process()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.output_display = QPlainTextEdit(self)
        self.output_display.setStyleSheet("background-color: black; color: white; font-family: 'Consolas', 'Monospace';")
        self.output_display.installEventFilter(self)
        self.layout.addWidget(self.output_display)
        self.setLayout(self.layout)
        self.output_received.connect(self.append_output)

    def _start_shell_process(self):
        if self.shell_process.state() == QProcess.Running:
            return

        shell_command = "powershell.exe" if sys.platform == "win32" else "/bin/bash"
        self.shell_process.setProcessChannelMode(QProcess.MergedChannels)
        
        # Disconnect any old connections cleanly
        if self.shell_process and self.shell_process.state() != QProcess.NotRunning:
            try: self.shell_process.readyReadStandardOutput.disconnect()
            except TypeError: pass
            try: self.shell_process.finished.disconnect()
            except TypeError: pass

        self.shell_process.readyReadStandardOutput.connect(self.read_output)
        self.shell_process.finished.connect(self.process_finished)
        self.shell_process.start(shell_command)
        self.output_display.setFocus() # Ensure the terminal has focus

    @Slot()
    def read_output(self):
        data = self.shell_process.readAll().data()
        try:
            # Try decoding with utf-8 first, which is common
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            # Fallback to system default if utf-8 fails
            text = data.decode(sys.getdefaultencoding(), errors='replace')
            
        self.output_received.emit(text, None)
        self.input_start_position = self.output_display.document().characterCount()
        self.output_display.verticalScrollBar().setValue(self.output_display.verticalScrollBar().maximum())

    @Slot(str, object)
    def append_output(self, text, color=None):
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        else:
            # Use default text color from stylesheet if no color is specified
            # This part can be enhanced by reading from a theme file
            fmt.setForeground(QColor("white"))

        cursor.insertText(text, fmt)
        self.output_display.setTextCursor(cursor)
        self.output_display.ensureCursorVisible()

    def eventFilter(self, obj, event):
        if obj is self.output_display and event.type() == QEvent.KeyPress:
            cursor = self.output_display.textCursor()

            # --- Handle special key combinations first ---
            if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
                if self.shell_process and self.shell_process.state() == QProcess.Running:
                    self.shell_process.kill()
                    self.append_output("^C\n", "yellow")
                return True

            if event.key() == Qt.Key_Up:
                if self.command_history and self.history_index > 0:
                    self.history_index -= 1
                    self._display_history_command(self.command_history[self.history_index])
                return True

            if event.key() == Qt.Key_Down:
                if self.history_index < len(self.command_history):
                    self.history_index += 1
                    command = self.command_history[self.history_index] if self.history_index < len(self.command_history) else ""
                    self._display_history_command(command)
                return True

            # --- Enforce cursor position protection ---
            if cursor.position() < self.input_start_position:
                if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                     return super().eventFilter(obj, event)
                return True

            if event.key() == Qt.Key_Backspace and cursor.position() <= self.input_start_position:
                return True

            # --- Handle Enter key separately ---
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                history_cursor = self.output_display.textCursor()
                history_cursor.setPosition(self.input_start_position)
                history_cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
                command = history_cursor.selectedText().strip()

                if command and (not self.command_history or self.command_history[-1] != command):
                    self.command_history.append(command)
                self.history_index = len(self.command_history)

                # Explicitly add a newline to the display
                self.append_output("\n")

                if self.shell_process and self.shell_process.state() == QProcess.Running:
                    self.shell_process.write((command + '\n').encode('utf-8')) # Send the command + newline
                return True

            # --- Handle all other general text input ---
            # --- Handle all other general text input ---
            key_text = event.text()
            if key_text:
                # Only allow typing if cursor is at or after input_start_position
                if cursor.position() >= self.input_start_position:
                    if self.shell_process and self.shell_process.state() == QProcess.Running:
                        self.shell_process.write(key_text.encode('utf-8'))
                    else:
                        self.append_output("Shell process not running.\n", "red")
                    # Let the QPlainTextEdit handle the character display
                    return super().eventFilter(obj, event)
                else:
                    # If cursor is in read-only area, consume the event
                    return True
            
        return super().eventFilter(obj, event)

    def _display_history_command(self, command: str):
        cursor = self.output_display.textCursor()
        cursor.setPosition(self.input_start_position)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(command)
        self.output_display.setTextCursor(cursor)
        self.output_display.ensureCursorVisible()

    @Slot(int, QProcess.ExitStatus)
    def process_finished(self, exit_code, exit_status):
        self.append_output(f"\nShell process exited. Restarting...\n", "yellow")
        self._start_shell_process()

    def send_command_to_shell(self, command: str):
        if self.shell_process and self.shell_process.state() == QProcess.Running:
            # Echo the command to the terminal for user visibility
            self.append_output(command + "\n", "cyan") 
            self.shell_process.write((command + '\n').encode('utf-8'))
        else:
            self.append_output("Shell process not running. Cannot send command.\n", "red")
            
    def clear_output(self):
        self.output_display.clear()

    @Slot(str, str, str)
    def start_interactive_process(self, command: str, cwd: str = None, description: str = None):
        """
        Starts an interactive process. This is a placeholder implementation.
        Actual implementation would involve managing a QProcess for the given command.
        """
        self.append_output(f"Starting interactive process: {command} (CWD: {cwd or 'current'}) - {description or ''}\n", "blue")
        # In a real scenario, you would start a new QProcess here
        # For now, we just simulate the output.
        # self.shell_process.start(command) # This would be the actual call

    @Slot(list)
    def run_command_sequence(self, commands: list):
        """
        Runs a sequence of commands. This is a placeholder implementation.
        Actual implementation would involve iterating through commands and sending them.
        """
        self.append_output(f"Running command sequence: {commands}\n", "blue")
        for cmd in commands:
            self.send_command_to_shell(cmd)