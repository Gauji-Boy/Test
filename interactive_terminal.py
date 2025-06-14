import os
import sys
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PySide6.QtGui import QFont, QTextCursor, QPalette, QColor, QKeyEvent
from PySide6.QtCore import QProcess, Signal, Slot, Qt

class InteractiveTerminal(QWidget):
    shell_terminated = Signal()
    # Signal to send data to the shell process (e.g., user input)
    send_data_to_shell_process = Signal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InteractiveTerminalWidget")

        self.output_display = QPlainTextEdit(self)
        self.output_display.setReadOnly(True)
        self.output_display.setFont(QFont("Fira Code", 10)) # Default size 10, consistent with old terminal

        # Apply some basic colors from the QSS palette if possible
        # QSS will be the primary way to style this.
        # pal = self.output_display.palette()
        # pal.setColor(QPalette.Base, QColor("#0F172A")) # Example: --editor-bg
        # pal.setColor(QPalette.Text, QColor("#CBD5E1")) # Example: --text-primary
        # self.output_display.setPalette(pal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_display)
        self.setLayout(layout)

        self.shell_process = None
        self.current_working_directory = os.path.expanduser("~") # Default to home

        # Connect internal signal for writing to process
        self.send_data_to_shell_process.connect(self._write_to_shell_process)

    def _determine_shell(self):
        if sys.platform == "win32":
            return "cmd.exe"
        else:
            return os.environ.get("SHELL", "/bin/sh")

    @Slot(str)
    def start_shell(self, directory: str = None):
        if self.shell_process and self.shell_process.state() != QProcess.NotRunning:
            # print("InteractiveTerminal: Shell already running. Stopping and restarting.")
            self.shell_process.kill()
            if not self.shell_process.waitForFinished(1000):
                print("InteractiveTerminal: Existing shell did not terminate gracefully.")

        self.shell_process = QProcess(self)
        self.shell_process.setProcessChannelMode(QProcess.MergedChannels)

        if directory and os.path.isdir(directory):
            self.current_working_directory = directory
        self.shell_process.setWorkingDirectory(self.current_working_directory)

        self.shell_process.readyReadStandardOutput.connect(self._on_shell_output)
        self.shell_process.finished.connect(self._on_shell_finished)
        self.shell_process.errorOccurred.connect(self._on_shell_error)

        program = self._determine_shell()
        self.append_output(f"Starting shell: {program} in {self.current_working_directory}...\n")
        self.shell_process.start(program)
        if sys.platform == "win32" and program == "cmd.exe":
             # Send an initial newline to show prompt for cmd.exe if it doesn't appear
            self.shell_process.waitForStarted(1000)
            # self.send_data_to_shell_process.emit(b'\r\n') # Or self.shell_process.write(b'\r\n') directly

    @Slot()
    def _on_shell_output(self):
        if self.shell_process:
            output_bytes = self.shell_process.readAllStandardOutput()
            try:
                # Try common encodings, utf-8 first, then system's locale for shell output
                output_str = output_bytes.data().decode('utf-8', errors='surrogateescape')
            except UnicodeDecodeError:
                try:
                    output_str = output_bytes.data().decode(sys.getdefaultencoding(), errors='replace')
                except Exception:
                    output_str = output_bytes.data().decode('latin-1', errors='replace') # Fallback
            except AttributeError: # If .data() is not needed (older Qt?)
                 output_str = output_bytes.decode('utf-8', errors='surrogateescape')

            self.append_output(output_str)

    @Slot(int, QProcess.ExitStatus)
    def _on_shell_finished(self, exit_code, exit_status):
        status = "normally" if exit_status == QProcess.NormalExit else "unexpectedly"
        self.append_output(f"\n--- Shell process {status} finished (code: {exit_code}) ---\n")
        self.shell_process = None
        self.shell_terminated.emit()

    @Slot(QProcess.ProcessError)
    def _on_shell_error(self, error):
        error_map = {
            QProcess.FailedToStart: "Failed to start", QProcess.Crashed: "Crashed",
            QProcess.Timedout: "Timed out", QProcess.ReadError: "Read error",
            QProcess.WriteError: "Write error", QProcess.UnknownError: "Unknown error"
        }
        err_str = error_map.get(error, "Unknown error")
        if self.shell_process:
            err_str += f": {self.shell_process.errorString()}"
        self.append_output(f"\n--- Shell process error: {err_str} ---\n")
        self.shell_process = None
        self.shell_terminated.emit()

    @Slot(str)
    def append_output(self, text: str):
        self.output_display.moveCursor(QTextCursor.End)
        self.output_display.insertPlainText(text)
        self.output_display.moveCursor(QTextCursor.End)

    @Slot()
    def clear_output(self):
        self.output_display.clear()

    @Slot(bytes) # Slot to write to the shell process
    def _write_to_shell_process(self, data: bytes):
        if self.shell_process and self.shell_process.state() == QProcess.Running:
            self.shell_process.write(data)
            self.shell_process.waitForBytesWritten(-1)
        else:
            self.append_output("\n--- Shell not running. Cannot send data. ---\n")

    def send_command_to_shell(self, command: str):
        """Public method to send a command string to the shell."""
        if not command.endswith('\n'):
            command += '\n'
        self.send_data_to_shell_process.emit(command.encode()) # Encode to bytes

    # Basic input handling if QPlainTextEdit is used for input
    def keyPressEvent(self, event: QKeyEvent):
        # This is a very simplified way to handle interactive input.
        # A full terminal emulator would handle cursor position, history, special keys, etc.
        if self.shell_process and self.shell_process.state() == QProcess.Running:
            # Pass key presses directly to the shell process
            # This is still too simplistic for a proper terminal (e.g. arrow keys, backspace)
            # but handles basic character input and Enter for commands.
            key_text = event.text()
            if key_text:
                if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    self.send_data_to_shell_process.emit(b'\n') # Or os.linesep.encode()
                elif event.key() == Qt.Key_Backspace:
                    # QProcess doesn't directly understand 'backspace character' from stdin for cmd.exe easily
                    # A proper terminal sends control codes or manages line buffer.
                    # For now, let Backspace be handled by QPlainTextEdit locally if it's not read-only.
                    # If it IS read-only (as it should be for pure output), Backspace does nothing here.
                    # We could emit a special signal or handle it if we had a dedicated input line.
                    super().keyPressEvent(event) # Allow QPlainTextEdit to handle it locally if not ReadOnly
                else:
                    self.send_data_to_shell_process.emit(key_text.encode())
                self.append_output(key_text) # Echo typed key (optional, shell might do it)
                event.accept()
                return
        super().keyPressEvent(event)

    def stop_shell(self):
        if self.shell_process and self.shell_process.state() != QProcess.NotRunning:
            self.shell_process.kill()
            # self.append_output("\n--- Shell terminated by user ---\n") # Avoid writing if already closing
            print("InteractiveTerminal: User requested shell termination.")

    def closeEvent(self, event):
        self.stop_shell()
        super().closeEvent(event)