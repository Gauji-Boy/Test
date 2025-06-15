from PySide6.QtCore import QObject, Signal, QProcess
# sys and QApplication are used only in the __main__ block for testing.

class ProcessManager(QObject):
    output_received = Signal(str)
    process_finished = Signal(int)
    process_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.process = None

    def execute_command(self, command_list: list, working_dir: str):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            # If a process is already running, emit an error and return.
            # Or, alternatively, queue the command or kill the existing process.
            # For now, we prevent concurrent execution.
            self.process_error.emit("ProcessManager: Another process is already running.")
            return

        self.process = QProcess(self) # Parent self for auto-cleanup if ProcessManager is deleted
        self.process.setWorkingDirectory(working_dir)

        # Connect signals to slots
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

        if not command_list:
            self.process_error.emit("ProcessManager: No command provided.")
            # self.process was just created, ensure it's cleaned up if we return early.
            if self.process:
                self.process.deleteLater()
                self.process = None
            return

        command = command_list[0]
        args = command_list[1:]

        # print(f"Executing: {command} {args} in {working_dir}") # For debugging
        self.process.start(command, args)
        # Note: QProcess.start() is non-blocking. Execution happens in the event loop.

    # --- Private Slots ---
    def _on_output(self):
        if not self.process: # Should not happen if slots are connected only when process exists
            return
        output_bytes = self.process.readAllStandardOutput()
        try:
            # Attempt to decode as UTF-8, replace errors to avoid crashing on weird bytes
            output_string = output_bytes.data().decode('utf-8', errors='replace').strip()
            if output_string: # Emit only if there's actual (stripped) output
                self.output_received.emit(output_string)
        except Exception as e: # Catch any decoding or other unexpected errors
            self.process_error.emit(f"ProcessManager: Error decoding/processing process output: {e}")

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        # This slot is called when the process finishes, either normally or by crashing.
        # exit_status indicates QProcess.NormalExit or QProcess.CrashExit.

        # Ensure all output is processed
        if self.process: # Check if self.process still exists (it should)
            self._on_output() # Process remaining stdout

            error_bytes = self.process.readAllStandardError()
            if error_bytes:
                try:
                    error_string = error_bytes.data().decode('utf-8', errors='replace').strip()
                    if error_string:
                        # Emit stderr. If exit_code is non-zero, it's likely an error message.
                        # Otherwise, it might be informational (e.g. git progress).
                        if exit_code != 0:
                             self.process_error.emit(f"Process stderr: {error_string}")
                        else:
                             self.output_received.emit(f"Process stderr (info): {error_string}")
                except Exception as e:
                    self.process_error.emit(f"ProcessManager: Error decoding process stderr: {e}")

        self.process_finished.emit(exit_code) # Emit the original exit code

        # Clean up the QProcess instance
        if self.process:
            self.process.deleteLater() # Schedule for safe deletion
            self.process = None # Allow a new process to be started

    def _on_error(self, error: QProcess.ProcessError):
        # This slot is called when QProcess encounters an error, e.g., failing to start.
        error_map = {
            QProcess.ProcessError.FailedToStart: "Process failed to start. Check command, path, and permissions.",
            QProcess.ProcessError.Crashed: "Process crashed.",
            QProcess.ProcessError.Timedout: "Process timed out.", # Not typically used unless timeout is set
            QProcess.ProcessError.ReadError: "Error reading from process.",
            QProcess.ProcessError.WriteError: "Error writing to process.",
            QProcess.ProcessError.UnknownError: "An unknown process error occurred."
        }
        error_message = error_map.get(error, "An unspecified process error occurred.")

        qprocess_error_string = ""
        if self.process: # self.process might be None if error occurred before full setup
             qprocess_error_string = self.process.errorString() # Get specific error from QProcess

        if qprocess_error_string:
            error_message += f" Details: {qprocess_error_string}"

        self.process_error.emit(error_message)

        # If the error means the process definitely won't run or has died, ensure cleanup.
        # The 'finished' signal is supposed to always be emitted, but for FailedToStart,
        # the process never really "ran".
        if error == QProcess.ProcessError.FailedToStart:
            if self.process:
                self.process.deleteLater()
                self.process = None
        # For Crashed, _on_finished will also be called, which handles cleanup.

# Main block for testing (optional, can be removed or kept for utility)
if __name__ == '__main__':
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv) # Event loop is necessary for QProcess
    manager = ProcessManager()

    # Connect signals to simple print handlers
    manager.output_received.connect(lambda output: print(f"STDOUT: {output}"))
    manager.process_finished.connect(
        lambda code: (
            print(f"FINISHED: Exit Code {code}"),
            app.quit() # Quit the application once the process is done
        )
    )
    manager.process_error.connect(
        lambda err_msg: (
            print(f"ERROR: {err_msg}"),
            app.quit() # Quit on error too
        )
    )

    # --- Test Cases ---
    # 1. Successful command with output
    # print("\n--- Test Case 1: Python Version ---")
    # manager.execute_command(["python", "--version"], ".")

    # 2. Command producing stderr (and non-zero exit code)
    # print("\n--- Test Case 2: Git Nonexistent Command ---")
    # manager.execute_command(["git", "nonexistentcommand"], ".")

    # 3. Command that fails to start
    print("\n--- Test Case 3: Nonexistent Command ---")
    manager.execute_command(["nonexistent_command_fjasdfklj_123"], ".")

    # 4. Command with mixed stdout/stderr (example, might vary by OS/shell)
    # if sys.platform == "win32":
    #    manager.execute_command(["cmd", "/c", "echo Normal Output && ver && dir Z:\nonexistent"], ".")
    # else:
    #    manager.execute_command(["sh", "-c", "echo Normal Output; uname -a; ls /nonexistent_dir_blah"], ".")

    sys.exit(app.exec())
