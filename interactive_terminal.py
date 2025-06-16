import sys
import platform # For OS detection

# PySide6 imports
from PySide6.QtCore import QProcess, Qt, QByteArray
from PySide6.QtGui import QKeyEvent, QTextCursor, QFont
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QVBoxLayout
# QApplication and QPushButton are used only in the __main__ block for testing.

class InteractiveTerminal(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.shell_process = None
        self.shell_ready = False # Flag to indicate if shell is ready for input

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0) # Use full space

        self.display_area = QPlainTextEdit(self)
        self.display_area.setReadOnly(True)
        self.display_area.setFont(QFont("monospace", 10)) # Use a monospaced font
        # self.display_area.setStyleSheet("background-color: black; color: white;") # Optional styling

        self.layout.addWidget(self.display_area)
        self.setLayout(self.layout)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.display_area.appendPlainText("[Terminal initialized. Starting shell...]")


    def start_shell(self, working_dir: str):
        if self.shell_process and self.shell_process.state() != QProcess.ProcessState.NotRunning:
            self.display_area.appendPlainText(f"[Shell already running. State: {self.shell_process.state()}]")
            return

        self.shell_process = QProcess(self)
        self.shell_process.setWorkingDirectory(working_dir)

        # Connect signals
        self.shell_process.readyReadStandardOutput.connect(self._handle_shell_output)
        self.shell_process.readyReadStandardError.connect(self._handle_shell_error)
        self.shell_process.finished.connect(self._handle_shell_finished)
        self.shell_process.errorOccurred.connect(self._handle_shell_process_error)
        self.shell_process.started.connect(self._handle_shell_started)

        shell_command = ""
        shell_args = []

        if platform.system() == "Windows":
            shell_command = "cmd.exe"
        elif platform.system() == "Linux" or platform.system() == "Darwin": # Darwin is macOS
            shell_command = next((s for s in ["bash", "sh"] if QProcess.findExecutable(s)), None)
            if shell_command:
                shell_args = ["-i"] # Interactive mode
            else:
                self.display_area.appendPlainText("[No suitable shell (bash or sh) found!]")
                self.shell_process = None; return
        else:
            self.display_area.appendPlainText(f"[Unsupported OS: {platform.system()}]")
            self.shell_process = None; return

        self.display_area.appendPlainText(f"[Starting {shell_command} in {working_dir}...]")
        self.shell_process.start(shell_command, shell_args)

    def keyPressEvent(self, event: QKeyEvent):
        if not self.shell_process or not self.shell_ready or self.shell_process.state() != QProcess.ProcessState.Running:
            event.ignore(); return

        key = event.key()
        text_to_send = ""

        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            text_to_send = "\r\n" if platform.system() == "Windows" else "\n"
            self.display_area.insertPlainText("\n")
            self.display_area.moveCursor(QTextCursor.MoveOperation.End)
        elif key == Qt.Key.Key_Backspace:
            text_to_send = "\x08"
        elif event.text(): # Regular character
            text_to_send = event.text()
        else: # Ignore other special keys
            event.ignore(); return

        if text_to_send:
            self.shell_process.write(text_to_send.encode('utf-8', errors='ignore'))
        event.accept()

    def run_command_from_ide(self, command_str: str):
        if self.shell_process and self.shell_ready and self.shell_process.state() == QProcess.ProcessState.Running:
            self.display_area.insertPlainText(command_str + "\n")
            self.display_area.moveCursor(QTextCursor.MoveOperation.End)
            full_command = command_str if command_str.endswith(("\n", "\r\n")) else command_str + ("\r\n" if platform.system() == "Windows" else "\n")
            self.shell_process.write(full_command.encode('utf-8', errors='ignore'))
            self.setFocus() # Keep focus on terminal
        else:
            self.display_area.appendPlainText(f"\n[Shell not ready. Cannot run command: {command_str}]")
            self.display_area.moveCursor(QTextCursor.MoveOperation.End)

    # --- Slots for QProcess ---
    def _handle_shell_output(self):
        if self.shell_process:
            data = self.shell_process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            self.display_area.insertPlainText(data)
            self.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _handle_shell_error(self):
        if self.shell_process:
            data = self.shell_process.readAllStandardError().data().decode('utf-8', errors='replace')
            self.display_area.insertPlainText(data)
            self.display_area.moveCursor(QTextCursor.MoveOperation.End)

    def _handle_shell_finished(self, exit_code, exit_status):
        status_msg = "normally" if exit_status == QProcess.ExitStatus.NormalExit else "by crashing"
        self.display_area.appendPlainText(f"\n[Shell process finished {status_msg} with code {exit_code}]")
        if self.shell_process: self.shell_process.close()
        self.shell_process = None
        self.shell_ready = False

    def _handle_shell_process_error(self, error: QProcess.ProcessError):
        err_str = self.shell_process.errorString() if self.shell_process and self.shell_process.errorString() else "Unknown QProcess Error"
        self.display_area.appendPlainText(f"\n[Shell process error: {error} ({err_str})]")
        if self.shell_process: self.shell_process.close()
        self.shell_process = None
        self.shell_ready = False

    def _handle_shell_started(self):
        self.display_area.appendPlainText("[Shell started successfully.]\n")
        self.shell_ready = True
        self.display_area.moveCursor(QTextCursor.MoveOperation.End)
        self.setFocus()

# Main block for testing
if __name__ == '__main__':
    # Imports specific to the test block
    import os
    from PySide6.QtWidgets import QApplication, QPushButton

    app = QApplication(sys.argv)
    main_window = QWidget()
    main_layout = QVBoxLayout(main_window)
    terminal = InteractiveTerminal(main_window)
    test_button = QPushButton("Run 'echo Hello from IDE'", main_window)
    def on_test_button_clicked():
        terminal.run_command_from_ide("echo Hello from IDE")
    test_button.clicked.connect(on_test_button_clicked)
    main_layout.addWidget(terminal)
    main_layout.addWidget(test_button)
    main_window.setWindowTitle("Interactive Terminal Test")
    main_window.resize(800, 650)
    main_window.show()
    current_working_dir = os.getcwd()
    try:
        pass
    except OSError as e:
        current_working_dir = os.path.expanduser("~")
        terminal.display_area.appendPlainText(f"[Warning: Could not get CWD, using home: {e}]")
    terminal.start_shell(current_working_dir)
    terminal.setFocus()
    sys.exit(app.exec())
