import os
import socket
import json
import threading
import time
from PySide6.QtCore import QObject, Signal, Slot, QProcess, QTimer

class DebugManagerRefactored(QObject):
    # Signals for MainWindow
    session_started = Signal()
    session_stopped = Signal()
    # thread_id, reason (e.g. 'breakpoint', 'step'), call_stack_data (list of dicts), variables_data (list of dicts)
    paused = Signal(int, str, list, list)
    resumed = Signal()
    # category (e.g., 'stdout', 'stderr', 'console', 'adapter_info', 'adapter_warn', 'adapter_raw', 'dap_send', 'dap_recv'), message
    output_received = Signal(str, str)
    # For errors specific to DAP communication or debugger setup that should be shown to user
    dap_error = Signal(str)
    # Signal to update UI about current execution point, even if not paused (e.g., for highlighting)
    # file_path, line_number (currently not used, but good for future)
    # execution_location_changed = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dap_process = None  # QProcess for the debug adapter
        self.dap_client_socket = None # Socket for DAP communication
        self.dap_thread = None # Thread for _dap_recv_loop
        self.dap_seq = 1 # DAP message sequence number

        self.is_session_active = False # Overall state: user has requested a debug session
        self.is_adapter_running = False # State of the DAP QProcess
        self.is_socket_connected = False # State of the DAP socket connection
        self.is_adapter_initialized = False # DAP 'initialize' sequence completed
        self.is_target_launched = False # DAP 'launch' or 'attach' completed, target program running

        self.current_program_path = None # Path to the program being debugged
        self.current_breakpoints = {} # {norm_path: {line_numbers}} internal cache of breakpoints set by user
        self._dap_buffer = bytearray() # Buffer for incoming DAP socket data
        self._dap_request_pending_response = {} # req_seq: {type, data...} for multi-step DAP responses

        self._connect_retry_timer = QTimer(self) # For retrying socket connection
        self._connect_retry_timer.setSingleShot(True)
        self._connect_retry_timer.timeout.connect(self._attempt_dap_socket_connect)
        self._dap_port = None # Port reported by the debug adapter
        self._current_thread_id_for_stepping = None # Stores threadId when target is paused

    # --- DAP Process Management ---
    def _start_debug_adapter(self, adapter_command: list):
        if self.dap_process and self.dap_process.state() != QProcess.NotRunning:
            self.dap_error.emit("Debug adapter process is already running.")
            # self.output_received.emit("adapter_warn", "Debug adapter process is already running.\n") # Alternative to error
            return False

        # Reset relevant flags before starting a new adapter process
        self._cleanup_dap_process_state() # Ensures old process is gone
        self._reset_socket_state()      # Ensures old socket is gone
        self.is_adapter_initialized = False
        self.is_target_launched = False
        self._dap_port = None
        self._dap_buffer.clear()
        self._dap_request_pending_response.clear()
        self.dap_seq = 1 # Reset sequence number

        self.dap_process = QProcess(self)
        self.dap_process.setProcessChannelMode(QProcess.MergedChannels)

        # Connect signals for the new process instance
        self.dap_process.readyReadStandardOutput.connect(self._on_dap_process_output)
        self.dap_process.errorOccurred.connect(self._on_dap_process_error_occurred)
        self.dap_process.finished.connect(self._on_dap_process_finished)

        if not adapter_command:
            self.dap_error.emit("No adapter command provided.")
            self._cleanup_dap_process_state() # Clean up the created QProcess
            return False

        program = adapter_command[0]
        args = adapter_command[1:]

        self.output_received.emit("adapter_info", f"Starting debug adapter: {program} {' '.join(args)}\n")
        try:
            self.dap_process.start(program, args)
            self.is_adapter_running = True # Tentatively set, waitForStarted will confirm
        except Exception as e: # Catch potential errors from QProcess.start itself (though rare)
            self.dap_error.emit(f"Exception starting debug adapter '{program}': {e}")
            self._cleanup_dap_process_state()
            return False

        if not self.dap_process.waitForStarted(5000): # Increased timeout to 5s
            error_str = self.dap_process.errorString()
            self.dap_error.emit(f"Failed to start debug adapter: {program}. Error: {error_str}")
            self._cleanup_dap_process_state()
            return False

        self.output_received.emit("adapter_info", f"Debug adapter process started (PID: {self.dap_process.processId()}). Waiting for port...\n")
        return True

    @Slot()
    def _on_dap_process_output(self):
        if not self.dap_process or self.dap_process.state() == QProcess.NotRunning:
            # self.output_received.emit("adapter_warn", "DAP process output received but process not valid.\n")
            return

        output_bytes = self.dap_process.readAllStandardOutput()
        output_str = ""
        try:
            output_str = output_bytes.data().decode('utf-8', errors='surrogateescape')
        except AttributeError: # If .data() is not needed (e.g., older Qt versions or direct bytes)
            output_str = output_bytes.decode('utf-8', errors='surrogateescape')

        # Emit raw output for logging/debugging if needed
        self.output_received.emit("adapter_raw", output_str)

        # Look for DAP port if not connected yet and no specific port was set to connect to.
        # This is a common pattern for adapters like debugpy that print the port they started on.
        if not self._dap_port and (not self.dap_client_socket or not self.is_socket_connected):
            # Example parsing for debugpy: "Debug adapter listening on port 5678"
            # This parsing logic is specific to the debug adapter's output format.
            search_str = "listening on port"
            if search_str in output_str.lower():
                try:
                    # Extract the port number that follows "listening on port "
                    port_str = output_str.lower().split(search_str)[-1].strip().split()[0]
                    # Remove any trailing non-numeric characters if any (e.g. periods, newlines)
                    cleaned_port_str = "".join(filter(str.isdigit, port_str))
                    if cleaned_port_str:
                        self._dap_port = int(cleaned_port_str)
                        self.output_received.emit("adapter_info", f"Debug adapter reported port: {self._dap_port}. Attempting connection...\n")
                        self._attempt_dap_socket_connect() # Try to connect now that we have a port
                    else:
                        self.output_received.emit("adapter_warn", f"Could not parse valid port number from: {port_str}\n")
                except Exception as e:
                    self.dap_error.emit(f"Could not parse port from adapter output: {e}. Raw output: '{output_str}'")

    @Slot(int, QProcess.ExitStatus)
    def _on_dap_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        status_str = "normally" if exit_status == QProcess.ExitStatus.NormalExit else "unexpectedly"
        msg = f"Debug adapter process finished {status_str} (code: {exit_code}).\n"
        self.output_received.emit("adapter_info", msg)
        print(f"DebugManager: {msg.strip()}") # Also print to console for clarity

        self._handle_dap_disconnect() # Ensure socket and DAP session state are cleaned up
        self._cleanup_dap_process_state() # Clean up QProcess object and related flags
        # If the session was considered active, session_stopped would have been emitted by _handle_dap_disconnect
        # If it wasn't (e.g. adapter failed before DAP init), ensure session_stopped is emitted if user tried to start.
        if self.is_session_active: # If a session start was attempted by user
             if not self.is_target_launched: # And if it never fully launched
                  self.session_stopped.emit() # Let UI know it stopped
             self.is_session_active = False # Reset this flag too

    @Slot(QProcess.ProcessError)
    def _on_dap_process_error_occurred(self, error: QProcess.ProcessError):
        error_string = "Unknown DAP process error"
        if self.dap_process: # Check if dap_process still exists
            error_string = self.dap_process.errorString() # Get more detailed error

        # Map QProcess.ProcessError enum to a human-readable string if needed,
        # but errorString() is usually comprehensive.
        # error_map = { QProcess.FailedToStart: "Failed to start", ... }
        # mapped_error_str = error_map.get(error, "Unknown error code")

        full_error_message = f"Debug adapter process error: {error_string} (Error Code: {error}).\n"
        self.dap_error.emit(full_error_message.strip()) # Emit a signal MainWindow can show to user
        self.output_received.emit("adapter_error", full_error_message) # Log it to debug output too
        print(f"DebugManager: {full_error_message.strip()}")

        self._handle_dap_disconnect() # Clean up DAP communication state
        self._cleanup_dap_process_state() # Clean up QProcess object and flags
        if self.is_session_active: # If a session start was attempted
            if not self.is_target_launched:
                self.session_stopped.emit()
            self.is_session_active = False

    def _cleanup_dap_process_state(self):
        if self.dap_process:
            if self.dap_process.state() != QProcess.NotRunning:
                # print("DebugManager: Terminating existing DAP process before cleanup.") # Debug log
                self.dap_process.kill() # Ensure it's stopped
                if not self.dap_process.waitForFinished(1000): # Brief wait
                    self.output_received.emit("adapter_warn", "DAP process did not terminate gracefully during cleanup.\n")

            # Disconnect signals to prevent calls on a potentially partially destructed object
            # or calls after the context of this DAP session is no longer valid.
            try: self.dap_process.readyReadStandardOutput.disconnect(self._on_dap_process_output)
            except RuntimeError: pass
            try: self.dap_process.errorOccurred.disconnect(self._on_dap_process_error_occurred)
            except RuntimeError: pass
            try: self.dap_process.finished.disconnect(self._on_dap_process_finished)
            except RuntimeError: pass

            self.dap_process.deleteLater() # Schedule for deletion by Qt event loop
            self.dap_process = None

        self.is_adapter_running = False
        # print("DebugManager: DAP process state cleaned up.") # Debug log

    # --- DAP Socket Communication ---
    @Slot()
    def _attempt_dap_socket_connect(self, host="127.0.0.1"):
        if not self._dap_port:
            # This might be noisy if adapter takes time to print port.
            # self.dap_error.emit("No DAP port available to connect.")
            # print("DebugManager: _attempt_dap_socket_connect called but no _dap_port yet.")
            return

        if self.dap_client_socket and self.is_socket_connected: # Check is_socket_connected flag
            # print("DebugManager: Socket already connected or attempting.")
            return

        # Ensure previous socket resources are fully cleaned if any attempt failed partially
        self._reset_socket_state()

        try:
            self.output_received.emit("adapter_info", f"Attempting DAP socket connection to {host}:{self._dap_port}...\n")
            self.dap_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.dap_client_socket.settimeout(3.0) # Timeout for the connect operation itself
            self.dap_client_socket.connect((host, self._dap_port))
            self.dap_client_socket.setblocking(False) # Set to non-blocking for the recv loop

            self.is_socket_connected = True # Mark as connected
            self.dap_thread = threading.Thread(target=self._dap_recv_loop, daemon=True)
            self.dap_thread.start()
            self.output_received.emit("adapter_info", f"Successfully connected to DAP server on port {self._dap_port}.\n")
            self._initialize_dap_session() # Start DAP initialization now that socket is up
        except socket.error as e:
            error_msg = f"DAP socket connection to {host}:{self._dap_port} failed: {e}"
            self.dap_error.emit(error_msg) # This is a more critical error for user
            self.output_received.emit("adapter_warn", error_msg + "\n")
            self._reset_socket_state() # Clean up failed socket attempt

            # Retry connection after a short delay, adapter might not be ready immediately
            # Or the port was parsed but adapter wasn't fully listening yet.
            if self.is_adapter_running and not self._connect_retry_timer.isActive():
                 self.output_received.emit("adapter_info", "Will retry DAP socket connection shortly...\n")
                 self._connect_retry_timer.start(1500) # Retry in 1.5 seconds
        except Exception as ex:
            # Catch any other unexpected errors during socket setup
            error_msg = f"Unexpected error during DAP socket connection: {ex}"
            self.dap_error.emit(error_msg)
            self.output_received.emit("adapter_error", error_msg + "\n")
            self._reset_socket_state()

    def _dap_recv_loop(self):
        print("DebugManager: DAP receive loop started.")
        # Ensure socket exists and is valid before entering loop
        while self.dap_client_socket and self.is_socket_connected and self.dap_client_socket.fileno() != -1:
            try:
                # Non-blocking recv; will raise error if no data
                data = self.dap_client_socket.recv(8192) # Increased buffer size
                if not data: # Orderly shutdown by remote peer
                    self.output_received.emit("adapter_info", "DAP connection closed by server (recv returned empty).\n")
                    self._handle_dap_disconnect() # Graceful disconnect procedure
                    break
                self._dap_buffer.extend(data)
                self._process_dap_buffer()
            except socket.timeout: # Should not happen with non-blocking, but as safeguard
                continue # Just means no data was available
            except socket.error as e:
                # For non-blocking sockets, EWOULDBLOCK or EAGAIN means no data currently available
                if e.errno != socket.errno.EWOULDBLOCK and e.errno != socket.errno.EAGAIN:
                    self.output_received.emit("adapter_warn", f"DAP receive loop socket error: {e}\n")
                    self._handle_dap_disconnect() # Critical error, treat as disconnect
                    break
                # If EWOULDBLOCK/EAGAIN, it's fine, just means no data. Loop will continue.
            except Exception as ex:
                # Catch any other unexpected error in the loop
                self.output_received.emit("adapter_error", f"Unexpected error in DAP receive loop: {ex}\n")
                self._handle_dap_disconnect()
                break
            time.sleep(0.01) # Small sleep to yield execution and prevent tight loop if no data

        # If loop exits, ensure is_socket_connected is false if not already handled by _handle_dap_disconnect
        self.is_socket_connected = False
        print("DebugManager: DAP receive loop ended.")

    def _process_dap_buffer(self):
        while True:
            # DAP messages are Content-Length delimited with \r\n\r\n separator
            header_separator_pos = self._dap_buffer.find(b'\r\n\r\n')
            if header_separator_pos == -1:
                break # Incomplete header, wait for more data

            header_part_str = self._dap_buffer[:header_separator_pos].decode('ascii', errors='ignore')
            content_length = -1
            for header_line in header_part_str.split('\r\n'):
                if header_line.lower().startswith('content-length:'):
                    try:
                        content_length = int(header_line.split(':')[1].strip())
                        break
                    except ValueError:
                        self.dap_error.emit(f"Invalid Content-Length value: {header_line.split(':')[1].strip()}")
                        self._dap_buffer.clear() # Clear buffer to prevent error loop
                        return # Error in parsing header

            if content_length == -1:
                # This can happen if the buffer contains partial data or malformed headers
                # For robustness, check if what we have looks like a start of a JSON (e.g. '{')
                # If not, and it's small, it might be noise. If it's large, it's an error.
                if self._dap_buffer.strip().startswith(b'{'):
                    self.dap_error.emit("DAP message seems to be JSON but missing Content-Length header.")
                else:
                    # Unrecognized data, might be partial. If it grows too large without valid header, clear it.
                    if len(self._dap_buffer) > 16384: # Arbitrary limit to prevent memory bloat from bad data
                        self.dap_error.emit("DAP buffer grew too large with unrecognized data, clearing.")
                        self._dap_buffer.clear()
                        return
                break # Wait for more data to form a valid header

            message_content_start_pos = header_separator_pos + 4 # Length of '\r\n\r\n'
            if len(self._dap_buffer) < message_content_start_pos + content_length:
                break # Incomplete message body, wait for more data

            message_body_bytes = self._dap_buffer[message_content_start_pos : message_content_start_pos + content_length]
            # Consume the processed message from the buffer
            self._dap_buffer = self._dap_buffer[message_content_start_pos + content_length:]

            try:
                decoded_message_body = message_body_bytes.decode('utf-8')
                dap_message = json.loads(decoded_message_body)
                # For verbose DAP message logging (can be enabled for debugging):
                # self.output_received.emit("dap_recv", f"{json.dumps(dap_message, indent=1)}\n")
                self._handle_dap_message(dap_message) # Dispatch the parsed message
            except json.JSONDecodeError as e:
                self.dap_error.emit(f"Error decoding DAP JSON: {e}. Message body: '{message_body_bytes.decode('utf-8', errors='replace')}'")
            except UnicodeDecodeError as ude:
                self.dap_error.emit(f"Error decoding DAP message (UTF-8): {ude}. Raw bytes: {message_body_bytes!r}")
            except Exception as ex:
                self.dap_error.emit(f"Unexpected error processing DAP message: {ex}")

    def _reset_socket_state(self):
        if self.dap_client_socket:
            try:
                self.dap_client_socket.shutdown(socket.SHUT_RDWR) # Gracefully shutdown
            except socket.error: pass # Ignore errors if already closed or not connected
            try:
                self.dap_client_socket.close()
            except socket.error: pass
            self.dap_client_socket = None

        if self.dap_thread and self.dap_thread.is_alive():
            # The loop should exit due to socket closure. Give it a moment.
            self.dap_thread.join(0.2) # Wait for up to 0.2 seconds
            if self.dap_thread.is_alive():
                 self.output_received.emit("adapter_warn", "DAP receive thread did not join cleanly.\n")
        self.dap_thread = None

        self._dap_buffer.clear()
        self.is_socket_connected = False # Explicitly set flag
        # print("DebugManager: Socket state reset.") # Debug log

    # --- DAP Message Handling ---
    def _send_dap_request(self, command: str, arguments: dict = None, request_id:int = None) -> int | None:
        pass # Sends a DAP request, returns sequence number or None on failure

    def _handle_dap_message(self, message: dict):
        pass # Main dispatcher for incoming DAP messages (responses/events)

    def _handle_dap_response(self, response: dict):
        pass # Handles DAP responses

    def _handle_dap_event(self, event: dict):
        pass # Handles DAP events (like 'stopped', 'output', 'terminated')

    # --- DAP Specific Sequences ---
    def _initialize_dap_session(self):
        pass # Sends DAP 'initialize' request

    def _launch_target_program(self): # New method to separate launch logic
        pass # Sends DAP 'launch' request

    def _send_breakpoints_to_adapter_after_init(self):
        pass # Sends all current_breakpoints after 'initialize' response

    def _send_configuration_done(self): # New method
        pass # Sends DAP 'configurationDone' request

    # --- Paused State Processing ---
    def _try_process_paused_state(self, base_request_seq: int):
        pass # Complex logic to gather stack, scopes, vars and emit 'paused'

    def _request_stack_trace(self, thread_id: int, base_request_seq: int):
        pass

    def _request_scopes(self, frame_id: int, base_request_seq: int):
        pass

    def _request_variables(self, variables_reference: int, base_request_seq: int):
        pass

    # --- Public API Methods (Slots for MainWindow) ---
    @Slot(str)
    def start_session(self, program_path: str):
        pass

    @Slot()
    def stop_session(self):
        pass

    def _handle_dap_disconnect(self): # Centralized disconnect logic
        pass

    def _send_step_command(self, dap_command: str):
        pass # Helper for stepping commands

    @Slot()
    def continue_execution(self):
        pass

    @Slot()
    def step_over(self):
        pass

    @Slot()
    def step_into(self):
        pass

    @Slot()
    def step_out(self):
        pass

    @Slot(str, object) # Path (str), lines (set of int)
    def update_internal_breakpoints(self, file_path: str, lines_set: set):
        pass # Updates self.current_breakpoints and sends to adapter if session active

    @Slot(str, list) # Path (str), lines (list of int)
    def set_breakpoints_on_adapter(self, file_path: str, lines_list: list):
        pass # Sends DAP 'setBreakpoints' request

    # --- Cleanup ---
    def __del__(self):
        # Ensure resources are cleaned up when the manager is deleted
        self.stop_session()
