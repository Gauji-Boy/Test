import os
from PySide6.QtCore import QObject, Signal, Slot, QProcess

class ProcessManager(QObject):
    # Signals
    output_received = Signal(str)
    process_started = Signal()
    process_finished = Signal(int, QProcess.ExitStatus) # exitCode, exitStatus
    process_error = Signal(str) # For errors like command not found, etc.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None

    @Slot(list, str)
    def execute(self, command_parts: list, working_dir: str):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process_error.emit("A process is already running.")
            # Optionally, queue the command or notify user. For now, just error out.
            return

        if not command_parts:
            self.process_error.emit("No command provided to execute.")
            return

        self.process = QProcess()
        self.process.setProcessChannelMode(QProcess.MergedChannels) # Combine stdout and stderr

        # Connect signals from QProcess
        self.process.readyReadStandardOutput.connect(self._on_ready_read_standard_output)
        self.process.started.connect(self._on_process_started)
        # QProcess.finished is overloaded, specify arguments to connect to the correct one
        self.process.finished.connect(self._on_process_finished)
        self.process.errorOccurred.connect(self._on_process_error_occurred)

        program = command_parts[0]
        arguments = command_parts[1:]

        if working_dir and os.path.isdir(working_dir):
            self.process.setWorkingDirectory(working_dir)
        else:
            # If working_dir is invalid, emit warning or error, or use default.
            # For now, QProcess will use the current working directory of the main application.
            print(f"ProcessManager: Warning - Invalid or no working directory specified: {working_dir}. Using default.")


        print(f"ProcessManager: Executing '{program}' with arguments {arguments} in '{self.process.workingDirectory()}'")
        self.process.start(program, arguments)
        # Note: process.start() is non-blocking. Signals will notify of events.

    def _on_ready_read_standard_output(self):
        if self.process:
            output_bytes = self.process.readAllStandardOutput()
            try:
                # Try decoding with UTF-8, fallback to system locale or others if needed
                output_str = output_bytes.data().decode('utf-8', errors='replace')
            except Exception as e:
                output_str = f"[Decode Error: {e}]\n{output_bytes.data().decode('latin-1', errors='replace')}" # Fallback
            self.output_received.emit(output_str)

    def _on_process_started(self):
        self.process_started.emit()
        print("ProcessManager: Process started.")

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        # Read any remaining output
        self._on_ready_read_standard_output()
        
        self.process_finished.emit(exit_code, exit_status)
        status_str = "normally" if exit_status == QProcess.NormalExit else "crashed"
        print(f"ProcessManager: Process finished {status_str} with exit code {exit_code}.")
        self.process = None # Allow new process execution

    def _on_process_error_occurred(self, error: QProcess.ProcessError):
        error_map = {
            QProcess.FailedToStart: "Failed to start",
            QProcess.Crashed: "Crashed",
            QProcess.Timedout: "Timed out",
            QProcess.ReadError: "Read error",
            QProcess.WriteError: "Write error",
            QProcess.UnknownError: "Unknown error"
        }
        error_string = error_map.get(error, "An unspecified error occurred")
        
        # Try to get more details from the process if available
        if self.process:
            native_error_details = self.process.errorString()
            if native_error_details:
                error_string += f": {native_error_details}"
        
        self.process_error.emit(error_string)
        print(f"ProcessManager: Process error - {error_string}")
        self.process = None # Allow new process execution

    @Slot()
    def kill_process(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            print("ProcessManager: Sent kill signal to running process.")
            # Note: _on_process_finished will be called eventually if kill is successful.
        else:
            print("ProcessManager: No process running to kill.")
