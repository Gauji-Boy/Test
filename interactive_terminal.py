from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtCore import Qt, Signal, Slot, QProcess
import os
import platform

class InteractiveTerminal(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.shell_process = None
        self._input_start_position = 0

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Text Edit for Input/Output
        self.text_edit = QPlainTextEdit()
        self.text_edit.setStyleSheet("background-color: #282c34; color: #abb2bf;")
        font = QFont("Cascadia Code", 10)
        self.text_edit.setFont(font)
        self.text_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.text_edit)

        # Connect keyPressEvent for the text_edit
        self.text_edit.keyPressEvent = self.keyPressEvent

        # Initial prompt
        self._append_prompt()

    def _append_prompt(self):
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText("\n>>> ")
        self._input_start_position = self.text_edit.textCursor().position()
        self.text_edit.moveCursor(QTextCursor.End)


    def start_shell(self, working_dir: str):
        if self.shell_process and self.shell_process.state() == QProcess.Running:
            self.shell_process.kill()
            self.shell_process.waitForFinished()

        self.shell_process = QProcess()
        self.shell_process.setWorkingDirectory(working_dir)

        system = platform.system()
        if system == "Windows":
            shell_path = "cmd.exe"
        elif system == "Linux" or system == "Darwin":
            shell_path = "/bin/bash" # or "/bin/zsh" etc.
        else:
            self.text_edit.appendPlainText("Unsupported OS for shell.\n")
            return

        self.shell_process.readyReadStandardOutput.connect(self._handle_output)
        self.shell_process.finished.connect(self._handle_finished)

        # Set environment variables for a non-interactive shell to behave more like an interactive one
        env = QProcess.systemEnvironment()
        # You might need to customize these further depending on the shell and desired behavior
        if system == "Linux" or system == "Darwin":
            env.append("TERM=xterm-256color") # Emulate a terminal
            env.append("PS1=\\u@\\h:\\w\\$ ") # Basic prompt for bash/zsh
        self.shell_process.setProcessEnvironment(env)

        self.shell_process.start(shell_path)
        self.text_edit.appendPlainText(f"Shell started in {working_dir}\n")
        self._append_prompt()


    def keyPressEvent(self, event):
        cursor = self.text_edit.textCursor()

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if cursor.position() >= self._input_start_position:
                command = self.text_edit.toPlainText()[self._input_start_position:]
                if self.shell_process and self.shell_process.state() == QProcess.Running:
                    self.shell_process.write(command.encode() + b'\n')
                else:
                    self.text_edit.appendPlainText("\nShell not running.")
                self._append_prompt()
            return # Consume the event

        if event.key() == Qt.Key_Backspace:
            if cursor.position() > self._input_start_position:
                # Allow backspace within the editable area
                QPlainTextEdit.keyPressEvent(self.text_edit, event)
            else:
                # Prevent backspacing into the prompt or previous output
                event.accept()
            return

        if cursor.position() < self._input_start_position:
            # If somehow the cursor is before the input start, move it to the end
            if event.text().isprintable() and not event.modifiers(): # only for printable chars
                self.text_edit.moveCursor(QTextCursor.End)
            # Do not allow editing of the read-only part
            if event.key() not in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End): # Allow navigation
                if not (event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_C): # Allow Ctrl+C
                    event.accept()
                    return


        QPlainTextEdit.keyPressEvent(self.text_edit, event)


    def run_code_command(self, command: str):
        self.text_edit.moveCursor(QTextCursor.End)
        # Ensure previous command output is separated if any
        if self.text_edit.toPlainText().endswith(">>> "):
             self.text_edit.insertPlainText(command)
        else:
            self.text_edit.insertPlainText(f"\n{command}") # Start on new line if not at prompt

        if self.shell_process and self.shell_process.state() == QProcess.Running:
            self.shell_process.write(command.encode() + b'\n')
        else:
            self.text_edit.appendPlainText("\nShell not running.")
        self._append_prompt()


    @Slot()
    def _handle_output(self):
        if self.shell_process:
            data = self.shell_process.readAllStandardOutput().data().decode(errors='ignore')
            self.text_edit.moveCursor(QTextCursor.End)
            # Remove the input command from the output if the shell echoes it
            # This is a simple check and might need to be more robust
            current_line_text = self.text_edit.toPlainText()[self._input_start_position:].strip()
            if data.strip().startswith(current_line_text):
                data = data[len(current_line_text):].lstrip()

            self.text_edit.insertPlainText(data)
            self.text_edit.moveCursor(QTextCursor.End)

    @Slot()
    def _handle_finished(self):
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText("\nShell process finished.\n")
        self.shell_process = None # Reset shell_process
        self._append_prompt() # Show a new prompt

    def clear_all(self): # Keep this method if it's used elsewhere
        self.text_edit.clear()
        self._append_prompt()

    # Add a method to gracefully close the shell when the widget is closed
    def closeEvent(self, event):
        if self.shell_process and self.shell_process.state() == QProcess.Running:
            self.text_edit.appendPlainText("\nClosing shell...")
            self.shell_process.kill()
            self.shell_process.waitForFinished(1000) # Wait up to 1 second
        super().closeEvent(event)