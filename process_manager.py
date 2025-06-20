import os
from PySide6.QtCore import QObject, Signal, Slot, QProcess, QIODevice

class ProcessManager(QObject):
    # Signals
    output_received = Signal(str)  # Emits lines of output (stdout or stderr)
    process_started = Signal()     # Emits when a process successfully starts
    process_finished = Signal(int, QProcess.ExitStatus)  # exit_code, exit_status
    process_error = Signal(str)    # Emits error messages (e.g., if process cannot start)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None

    @Slot(list, str)
    def execute(self, command_parts, working_dir):
        if self.is_running():
            self.process_error.emit("A process is already running.")
            return

        if not command_parts:
            self.process_error.emit("Command cannot be empty.")
            return

        program = command_parts[0]
        arguments = command_parts[1:]

        self.process = QProcess(self)
        self.process.setWorkingDirectory(working_dir)

        # Connect signals from QProcess
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._handle_finished)
        self.process.errorOccurred.connect(self._handle_error_occurred)
        self.process.started.connect(self.process_started) # Emit signal when started

        try:
            # PySide6 recommends startCommand for simplicity if you have the full command string.
            # However, using setProgram and then start() gives more control if needed.
            # Let's assume `command_parts` is `[executable, arg1, arg2, ...] LFS
            # `start` is fine for this.

            # Ensure the program exists and is executable, especially on non-Windows
            # This is a basic check; QProcess might have more robust ways.
            if not QProcess.findExecutable(program):
                 if os.path.isfile(program) and os.access(program, os.X_OK):
                     # Full path to executable might be provided
                     pass # QProcess will try to run it
                 else:
                    self.process_error.emit(f"Executable '{program}' not found or not executable.")
                    self.process = None
                    return

            self.process.setProgram(program)
            self.process.setArguments(arguments)

            # Set unified channels for easier output handling if desired, or handle separately.
            # self.process.setProcessChannelMode(QProcess.MergedChannels)

            self.process.start()
            # QProcess.start() is non-blocking.
            # process_started signal will be emitted if it starts successfully.

        except Exception as e:
            self.process_error.emit(f"Failed to start process: {e}")
            self.process = None # Ensure process is cleared on error

    @Slot()
    def _handle_stdout(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput()
        self.output_received.emit(data.data().decode(errors='replace'))

    @Slot()
    def _handle_stderr(self):
        if not self.process:
            return
        data = self.process.readAllStandardError()
        self.output_received.emit(data.data().decode(errors='replace')) # Emit stderr on same signal

    @Slot(int, QProcess.ExitStatus)
    def _handle_finished(self, exit_code, exit_status):
        # print(f"ProcessManager: Process finished. Exit code: {exit_code}, Status: {exit_status}")
        self.process_finished.emit(exit_code, exit_status)
        # Clean up the QProcess object once it's finished and signals are handled.
        # self.process.deleteLater() # Causes issues if we want to check is_running later or restart
        self.process = None # Allow a new process to be started

    @Slot(QProcess.ProcessError)
    def _handle_error_occurred(self, error):
        # This signal is emitted when the process fails to start, crashes, or times out.
        if self.process: # Check if process exists, as it might be None if start failed early
            error_string = self.process.errorString()
        else:
            error_string = f"QProcess.ProcessError code: {error} (process object was None)"

        # print(f"ProcessManager: Process error occurred: {error_string} (Error code: {error})")
        self.process_error.emit(error_string)
        # self.process.deleteLater() # Clean up if an error occurs that implies it won't finish normally
        self.process = None # Allow a new process to be started

    @Slot()
    def is_running(self) -> bool:
        if self.process:
            return self.process.state() != QProcess.NotRunning
        return False

    @Slot()
    def kill_process(self):
        if self.is_running():
            self.process.terminate() # Try to terminate gracefully first
            # Optionally, wait for a bit and then kill if still running
            if not self.process.waitForFinished(1000): # Wait 1 sec
                self.process.kill()
            # print("ProcessManager: Attempted to kill process.")
        # else:
            # print("ProcessManager: No process running to kill.")
