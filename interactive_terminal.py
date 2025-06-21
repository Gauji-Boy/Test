from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PySide6.QtGui import QFont, QTextCursor, QKeyEvent
from PySide6.QtCore import Qt, QProcess, QProcessEnvironment
import platform
import os

from config_manager import ConfigManager
from config import DEFAULT_TERMINAL_FONT_FAMILY, DEFAULT_TERMINAL_FONT_SIZE

class TerminalInputWidget(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_terminal = parent # Store a reference to the HighFidelityTerminal

    def keyPressEvent(self, event: QKeyEvent):
        if not self.parent_terminal or not self.parent_terminal.shell_process or \
           self.parent_terminal.shell_process.state() != QProcess.ProcessState.Running:
            super().keyPressEvent(event)
            return

        key = event.key()
        text_to_send = ""

        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            text_to_send = "\n"
        elif key == Qt.Key.Key_Backspace:
            text_to_send = "\x08"
        elif key == Qt.Key.Key_Tab:
            text_to_send = "\t"
        elif event.text():
            text_to_send = event.text()

        if text_to_send:
            self.parent_terminal.shell_process.write(text_to_send.encode('utf-8'))
            event.accept() # Consume the event, text will appear when shell echoes it
        else:
            super().keyPressEvent(event) # Let QPlainTextEdit handle other keys if needed (e.g., Ctrl+C if not handled by shell)

    def insertFromMimeData(self, source): # Handle paste
        if source.hasText() and self.parent_terminal and self.parent_terminal.shell_process and \
           self.parent_terminal.shell_process.state() == QProcess.ProcessState.Running:
            text_to_paste = source.text()
            # Sanitize pasted text a bit: replace CR LF with LF, and CR with LF
            text_to_paste = text_to_paste.replace('\r\n', '\n').replace('\r', '\n')
            self.parent_terminal.shell_process.write(text_to_paste.encode('utf-8'))
            return # Explicitly return to prevent superclass call if text sent to shell
        else:
            super().insertFromMimeData(source)


class HighFidelityTerminal(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("High Fidelity Terminal")

        self.shell_process = None

        self.main_layout = QVBoxLayout(self)
        self.setLayout(self.main_layout)

        self.terminal_input_widget = TerminalInputWidget(self) # Use new class, pass self
        self.main_layout.addWidget(self.terminal_input_widget)

        self.terminal_input_widget.setStyleSheet("""
            QPlainTextEdit {
                background-color: #282c34;
                color: #abb2bf;
                border: 1px solid #3e4452;
                padding: 5px;
            }
        """)

        config_mgr = ConfigManager()
        term_font_family = config_mgr.load_setting('terminal_font_family', DEFAULT_TERMINAL_FONT_FAMILY)
        term_font_size = config_mgr.load_setting('terminal_font_size', DEFAULT_TERMINAL_FONT_SIZE)
        font = QFont(term_font_family, term_font_size)
        self.terminal_input_widget.setFont(font)
        self.terminal_input_widget.setReadOnly(False) # It's not directly editable, but receives focus for key events

    def start_shell(self, working_dir: str):
        if self.shell_process and self.shell_process.state() != QProcess.NotRunning:
            self.shell_process.kill()
            self.shell_process.waitForFinished()

        self.shell_process = QProcess(self)
        self.shell_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.shell_process.setWorkingDirectory(working_dir)

        # Setup environment for interactive mode (especially for Unix-like shells)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "xterm-256color") # Emulate a common terminal type
        # PS1 might be useful for bash/zsh to ensure a prompt, but shells usually provide one in interactive mode.
        # env.insert("PS1", "\\[\\033[01;32m\\]\\u@\\h\\[\\033[00m\\]:\\[\\033[01;34m\\]\\w\\[\\033[00m\\]\\$ ")
        self.shell_process.setProcessEnvironment(env)

        self.shell_process.readyReadStandardOutput.connect(self._on_shell_output_received)
        # self.shell_process.finished.connect(self._on_shell_finished) # Optional: handle shell termination

        shell_executable = ""
        args = []

        if platform.system() == "Windows":
            powershell_path = QProcess.findExecutable("powershell.exe")
            if powershell_path:
                shell_executable = powershell_path
                args = ["-NoLogo", "-NoExit"] # Changed: Removed -Command -
            else:
                cmd_path = QProcess.findExecutable("cmd.exe")
                if cmd_path:
                    shell_executable = cmd_path
                    args = ["/K"]
                else:
                    error_msg = "Error: Neither powershell.exe nor cmd.exe found on this Windows system.\n"
                    self.append_output(error_msg)
                    return
        else:
            default_shell = os.environ.get("SHELL")
            if default_shell and QProcess.findExecutable(default_shell):
                shell_executable = default_shell
            elif QProcess.findExecutable("bash"): # Fallback to bash
                shell_executable = "bash"
            elif QProcess.findExecutable("sh"): # Fallback to sh
                shell_executable = "sh"
            else:
                # Specific error if no common Unix shell is found
                error_msg = "Error: No suitable shell (bash, sh, or $SHELL) found on this system.\n"
                self.append_output(error_msg)
                print(f"DEBUG: {error_msg}")
                return # Explicitly return
            args = ["-i"] # Start in interactive mode

        if shell_executable: # This check is now more of a safeguard
            if args:
                self.shell_process.start(shell_executable, args)
            else:
                self.shell_process.start(shell_executable)

            if not self.shell_process.waitForStarted(5000): # 5 sec timeout
                error_message = f"Error starting shell '{shell_executable}': {self.shell_process.errorString()}\n"
                self.append_output(error_message)
            else:
                # For PowerShell with "-Command -", it might need an initial newline to show prompt
                if platform.system() == "Windows" and "powershell" in shell_executable.lower():
                    self.shell_process.write("\n".encode('utf-8'))
                # On non-Windows, -i should be enough.
                # For cmd.exe with /K, it should show a prompt automatically.
        else:
             # This case should ideally be caught by earlier checks that return if shell_executable is not set.
             # If it's reached, it means shell_executable was empty.
             error_message = "Shell executable path could not be determined (should have been caught earlier).\n"
             self.append_output(error_message)


    def _on_shell_output_received(self):
        if not self.shell_process:
            return

        data = self.shell_process.readAllStandardOutput()
        if data:
            try:
                # Try UTF-8 first, then system's default, then replace errors
                text = data.data().decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text = data.data().decode(errors='replace') # System default or fallback
                except Exception as e:
                    text = f"[Decoding Error: {e}]"

            self.append_output(text)

    def execute_ide_command(self, command: str):
        """Executes a command originating from an IDE action (e.g., Run button)."""
        if self.shell_process and self.shell_process.state() == QProcess.ProcessState.Running:
            full_command = command + "\n"
            self.shell_process.write(full_command.encode('utf-8'))
            # The command itself will be echoed by the shell if the shell is configured to do so.
            # We don't manually append it to the display here.
        else:
            self.append_output(f"Shell not running. Cannot execute: {command}\n")

    def append_output(self, text: str):
        """Appends text (from shell stdout/stderr) to the terminal display."""
        self.terminal_input_widget.moveCursor(QTextCursor.MoveOperation.End)
        self.terminal_input_widget.insertPlainText(text)
        self.terminal_input_widget.moveCursor(QTextCursor.MoveOperation.End)
        self.terminal_input_widget.ensureCursorVisible()

    def setFocus(self):
        """Sets focus to the terminal input widget."""
        self.terminal_input_widget.setFocus()

    def clear_output(self):
        """Clears the terminal display."""
        self.terminal_input_widget.clear()
        # If shell is running, it might be good to send a Ctrl+L or similar to ask shell to redraw prompt,
        # but this is complex and shell-dependent. For now, just clears the display.

    # Optional: Handler for when the shell process itself finishes/crashes
    # def _on_shell_finished(self, exit_code, exit_status):
    #     status_message = f"Shell process finished. Exit code: {exit_code}, Status: {exit_status}\n"
    #     if exit_status == QProcess.ExitStatus.CrashExit:
    #         status_message = f"Shell process crashed. Exit code: {exit_code}\n"
    #     self.append_output(status_message)
    #     # Optionally, try to restart the shell or disable input.

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    terminal = HighFidelityTerminal()
    terminal.resize(800, 600)
    terminal.show()
    
    # Automatically start the shell when the widget is shown
    terminal.start_shell(os.getcwd()) # Use current working directory
    
    sys.exit(app.exec())