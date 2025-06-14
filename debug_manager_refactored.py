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
        if not self.dap_client_socket or not self.is_socket_connected or self.dap_client_socket.fileno() == -1:
            self.dap_error.emit(f"Cannot send DAP request '{command}': Not connected.")
            # print(f"DebugManager: Cannot send DAP request '{command}': Not connected or socket invalid.")
            return None

        seq_to_use = request_id if request_id is not None else self.dap_seq
        if request_id is None:
            self.dap_seq += 1

        message = {
            "seq": seq_to_use,
            "type": "request",
            "command": command,
        }
        if arguments is not None:
            message["arguments"] = arguments

        # For verbose DAP message logging (can be enabled for debugging):
        # self.output_received.emit("dap_send", f"{json.dumps(message, indent=1)}\n")

        json_message = json.dumps(message)
        # Ensure ends with \r\n for headers, then body
        raw_message = f"Content-Length: {len(json_message)}\r\n\r\n{json_message}".encode('utf-8')

        try:
            # print(f"DAP SEND ({seq_to_use}): {command}") # Debug print
            self.dap_client_socket.sendall(raw_message)
            return seq_to_use # Return sequence number of the request
        except socket.error as e:
            self.dap_error.emit(f"DAP send error for command '{command}': {e}")
            self.output_received.emit("adapter_error", f"DAP send error for command '{command}': {e}\n")
            self._handle_dap_disconnect() # Assume connection is lost on send error
            return None
        except Exception as ex:
            self.dap_error.emit(f"Unexpected error sending DAP command '{command}': {ex}")
            self.output_received.emit("adapter_error", f"Unexpected error sending DAP command '{command}': {ex}\n")
            self._handle_dap_disconnect()
            return None

    def _handle_dap_message(self, message: dict):
        msg_type = message.get("type")
        # For verbose logging of all messages:
        # self.output_received.emit("dap_recv", f"{json.dumps(message, indent=1)}\n")

        if msg_type == "response":
            self._handle_dap_response(message)
        elif msg_type == "event":
            self._handle_dap_event(message)
        else:
            warn_msg = f"Received unknown DAP message type: {msg_type}. Full message: {json.dumps(message)}"
            self.output_received.emit("adapter_warn", warn_msg + "\n")
            # self.dap_error.emit(warn_msg) # This might be too noisy for user errors

    def _handle_dap_response(self, response: dict):
        command = response.get("command")
        request_seq = response.get("request_seq")
        success = response.get("success", False)
        body = response.get("body", {})

        # print(f"DAP RECV RESPONSE ({request_seq}) for {command}, success: {success}") # Debug print

        if not success:
            error_message_from_dap = response.get("message", "Unknown error in DAP response.")
            body_error_info = body.get("error", {})
            if body_error_info and isinstance(body_error_info, dict):
                 error_details = body_error_info.get('format', '')
                 # Some adapters put variables in format string, e.g. {variable}
                 # For now, just append. A more robust solution would substitute if needed.
                 if error_details: error_message_from_dap += f" Details: {error_details}"

            self.dap_error.emit(f"DAP Error on '{command}' (request seq {request_seq}): {error_message_from_dap}")
            if command == "initialize":
                self._handle_dap_disconnect() # Critical failure, stop session attempt

            # Clean up pending response if it exists
            if request_seq in self._dap_request_pending_response:
                del self._dap_request_pending_response[request_seq]
            return

        # --- Successful Responses ---
        if command == "initialize":
            self.is_adapter_initialized = True
            self.output_received.emit("adapter_info", "Debug adapter initialized successfully.\n")
            # Adapter capabilities are in body if needed (e.g., body.get('supportsConfigurationDoneRequest'))
            self._send_breakpoints_to_adapter_after_init() # Send any cached breakpoints
            self._send_configuration_done() # Tell adapter we're ready for launch/attach

        elif command == "launch" or command == "attach":
            self.is_target_launched = True
            self.session_started.emit() # Notify MainWindow session is fully active and target is running
            self.output_received.emit("adapter_info", "Debug target launched/attached successfully.\n")

        elif command == "setBreakpoints":
            # Breakpoints confirmed by adapter. Body may contain actual source/line if different.
            # For now, we assume our requested BPs were accepted as is.
            # self.output_received.emit("adapter_info", f"Breakpoints set/confirmed by adapter.\n")
            pass

        elif command == "configurationDone":
            # This means adapter is now fully ready to start the debuggee if it was a launch request
            # or ready for further commands if attach.
            # Some adapters send 'initialized' event after this, then we launch.
            # Others expect launch before this. Handled by is_target_launched flag.
            self.output_received.emit("adapter_info", "Configuration done sent to adapter.\n")
            if not self.is_target_launched and self.current_program_path:
                 self._launch_target_program()

        elif command == "stackTrace":
            if request_seq in self._dap_request_pending_response and \
               self._dap_request_pending_response[request_seq].get("type") == "paused_state":
                self._dap_request_pending_response[request_seq]["stack_trace_response"] = response
                self._try_process_paused_state(request_seq) # Try to gather more data or emit 'paused'
            # else: print(f"DAP: Received stackTrace for unknown/unsolicited request_seq {request_seq}")

        elif command == "scopes":
            if request_seq in self._dap_request_pending_response and \
               self._dap_request_pending_response[request_seq].get("type") == "paused_state":
                if "scopes_responses" not in self._dap_request_pending_response[request_seq]:
                    self._dap_request_pending_response[request_seq]["scopes_responses"] = []
                self._dap_request_pending_response[request_seq]["scopes_responses"].append(response)
                self._try_process_paused_state(request_seq)
            # else: print(f"DAP: Received scopes for unknown/unsolicited request_seq {request_seq}")

        elif command == "variables":
            if request_seq in self._dap_request_pending_response and \
               self._dap_request_pending_response[request_seq].get("type") == "paused_state":
                if "variables_responses" not in self._dap_request_pending_response[request_seq]:
                    self._dap_request_pending_response[request_seq]["variables_responses"] = []
                self._dap_request_pending_response[request_seq]["variables_responses"].append(response)
                self._try_process_paused_state(request_seq)
            # else: print(f"DAP: Received variables for unknown/unsolicited request_seq {request_seq}")

        # For simple commands like continue, next, stepIn, stepOut, disconnect
        # their success is noted, and state changes usually come via events ('continued', 'stopped', 'terminated').
        # So, we might just clear the pending response if it's not part of a multi-step data gathering like 'paused'.
        if request_seq in self._dap_request_pending_response and \
           self._dap_request_pending_response[request_seq].get("type") != "paused_state":
             del self._dap_request_pending_response[request_seq]

    def _handle_dap_event(self, event: dict):
        event_name = event.get("event")
        body = event.get("body", {})

        # print(f"DAP RECV EVENT: {event_name}") # Debug print

        if event_name == "output":
            category = body.get("category", "console") # stdout, stderr, console, telemetry
            output_text = body.get("output", "")
            # Variables can be complex; for now, just emit their string representation if any
            # if body.get("variablesReference", 0) > 0:
            #     output_text += f" (Variables: Ref {body.get('variablesReference')})"
            self.output_received.emit(category, output_text)

        elif event_name == "initialized":
            # This event means adapter is ready for configuration (breakpoints, launch/attach).
            # This is an important event. Some adapters send this *after* 'initialize' response.
            self.output_received.emit("adapter_info", "Debug adapter sent 'initialized' event.\n")
            self.is_adapter_initialized = True # Can also be set here
            # If we haven't launched/attached yet and program path is known, do it now.
            if not self.is_target_launched and self.current_program_path:
                 self._send_breakpoints_to_adapter_after_init() # Send BPs before launch if adapter prefers
                 self._send_configuration_done() # Then config done
                 # self._launch_target_program() # Launch might be triggered after configDone response
            # The exact sequence can vary slightly by adapter (e.g. when to send launch).
            # Current logic: initialize -> (response) -> send BPs -> send configDone -> (response) -> launch if not already.
            # If 'initialized' event comes, and we haven't launched, it's a good time to ensure launch is next.

        elif event_name == "stopped":
            self._current_thread_id_for_stepping = body.get("threadId", 1) # Store for stepping commands
            reason = body.get("reason", "unknown") # e.g., 'breakpoint', 'step', 'exception'
            # preserveAllThreadsStopped = body.get("preserveFocusHint", False)
            self.output_received.emit("adapter_info", f"Target stopped (thread {self._current_thread_id_for_stepping}, reason: {reason}). Fetching details...\n")

            # Start the process of fetching stack trace, scopes, and variables.
            # Use the sequence number of the first request (stackTrace) as a key for pending responses.
            base_request_seq = self._send_dap_request("stackTrace", {"threadId": self._current_thread_id_for_stepping})
            if base_request_seq:
                 self._dap_request_pending_response[base_request_seq] = {
                     "type": "paused_state",
                     "thread_id": self._current_thread_id_for_stepping,
                     "reason": reason,
                     "expected_scopes_for_frames": {}, # To track scope requests per frame
                     "expected_variables_for_scopes": {}, # To track variable requests per scope ref
                     "scopes_responses": [], # Store all scope responses for this pause event
                     "variables_responses": [] # Store all variable responses for this pause event
                 }
            else:
                self.dap_error.emit("Failed to send stackTrace request on stopped event.")

        elif event_name == "continued":
            thread_id = body.get("threadId") # Can be specific or all threads
            # all_threads_continued = body.get("allThreadsContinued", True)
            self.output_received.emit("adapter_info", f"Target continued (thread {thread_id}).\n")
            self.resumed.emit()
            self._current_thread_id_for_stepping = None # Clear stored thread ID

        elif event_name == "terminated":
            # Debuggee terminated. Session should effectively end.
            self.output_received.emit("adapter_info", "Debug target terminated event received.\n")
            self.stop_session() # Trigger full session stop and cleanup

        elif event_name == "thread": # Thread started or exited
            reason = body.get("reason") # 'started', 'exited'
            thread_id = body.get("threadId")
            self.output_received.emit("adapter_info", f"Thread event: {reason}, ID: {thread_id}\n")
            # Can update UI if displaying threads, or manage stepping thread if it changes.

        elif event_name == "breakpoint": # Breakpoint event (e.g. modified by adapter, or hit)
            reason = body.get("reason") # 'changed', 'new', 'removed', 'verified'
            breakpoint_data = body.get("breakpoint") # Contains breakpoint details
            # self.output_received.emit("adapter_info", f"Breakpoint event: {reason} - {breakpoint_data}\n")
            # This can be used to update internal breakpoint state or UI if adapter changes them.
            pass

        # Other possible events: module, loadedSource, process, capabilities, etc.
        # These can be implemented if needed for richer UI feedback.

    # --- DAP Specific Sequences ---
    def _initialize_dap_session(self):
        if not self.is_socket_connected:
            self.dap_error.emit("Cannot initialize DAP session: Socket not connected.")
            return

        self.output_received.emit("adapter_info", "Sending DAP initialize request...\n")
        self._send_dap_request("initialize", {
            "clientID": "AetherEditor",
            "clientName": "Aether Editor",
            "adapterID": "python", # This is often 'python' for debugpy, may vary for other adapters
            "linesStartAt1": True,
            "columnsStartAt1": True,
            "supportsVariableType": True,
            "supportsVariablePaging": True, # For fetching variables in chunks
            "supportsRunInTerminalRequest": True, # If we want to support 'runInTerminal'
            "locale": "en-US"
            # Can also send pathFormat: 'path' or 'uri'
        })
        # The response to 'initialize' will trigger sending breakpoints and configurationDone.

    def _launch_target_program(self): # New method to separate launch logic
        if not self.is_adapter_initialized:
            self.dap_error.emit("Cannot launch target: DAP adapter not initialized.")
            return
        if not self.current_program_path:
            self.dap_error.emit("Cannot launch target: No program path specified.")
            return
        if self.is_target_launched: # Already launched
            # self.output_received.emit("adapter_info", "Target already launched.")
            return

        self.output_received.emit("adapter_info", f"Sending DAP launch request for: {self.current_program_path}\n")
        launch_args = {
            "program": os.path.abspath(self.current_program_path),
            "console": "internalConsole", # Output will be sent via DAP 'output' events
            # "cwd": os.path.dirname(self.current_program_path), # Optional: set working directory
            # "noDebug": False, # Ensure we are debugging, not just running
            # "stopOnEntry": False, # Optional: stop at the first line of the program
            # Add other necessary launch arguments here, e.g. "args": []
        }
        self._send_dap_request("launch", launch_args)
        # The response to 'launch' will confirm if target started, and then session_started is emitted.

    def _send_breakpoints_to_adapter_after_init(self):
        # This is typically called after 'initialize' response and before 'configurationDone'.
        # Some adapters might prefer breakpoints after 'configurationDone' or even after 'launch'.
        # For debugpy, sending before 'configurationDone' is common.
        if not self.is_adapter_initialized:
            # self.output_received.emit("adapter_warn", "Cannot send initial BPs: Adapter not initialized.\n")
            return

        self.output_received.emit("adapter_info", "Sending initial breakpoints to adapter...\n")
        for file_path, lines_set in self.current_breakpoints.items():
            if lines_set:
                # This call will internally use _send_dap_request
                self.set_breakpoints_on_adapter(file_path, list(lines_set))

    def _send_configuration_done(self): # New method
        if not self.is_adapter_initialized:
            self.dap_error.emit("Cannot send 'configurationDone': Adapter not initialized.")
            return

        self.output_received.emit("adapter_info", "Sending DAP configurationDone request...\n")
        self._send_dap_request("configurationDone", {})
        # Response to this, or an 'initialized' event, might trigger program launch.

    # --- Paused State Processing ---
    def _try_process_paused_state(self, base_request_seq: int):
        paused_info = self._dap_request_pending_response.get(base_request_seq)
        if not paused_info or paused_info.get("type") != "paused_state":
            # print(f"DebugManager: _try_process_paused_state called for invalid or non-paused request seq {base_request_seq}")
            return

        if "stack_trace_response" not in paused_info:
            # print(f"DebugManager: Waiting for stack_trace_response for seq {base_request_seq}")
            return # Still waiting for the initial stack trace response

        stack_frames_body = paused_info["stack_trace_response"].get("body", {})
        stack_frames_dap = stack_frames_body.get("stackFrames", [])

        parsed_call_stack = []
        all_scopes_for_all_frames_received = True # Assume true initially

        for frame_dap in stack_frames_dap:
            frame_id = frame_dap.get("id")
            source_dap = frame_dap.get("source", {})
            parsed_call_stack.append({
                "id": frame_id,
                "name": frame_dap.get("name", "<unknown_frame>"),
                "file": source_dap.get("path", source_dap.get("name", "<unknown_source>")),
                "line": frame_dap.get("line", 0)
            })

            # Check if scopes for this frame_id have been requested and received
            # A frame's scopes are considered received if there's at least one entry in scopes_responses
            # that matches this frame_id in its request arguments.
            frame_scopes_received = any(
                sr.get("request", {}).get("arguments", {}).get("frameId") == frame_id
                for sr in paused_info.get("scopes_responses", [])
            )

            if not frame_scopes_received:
                if frame_id not in paused_info["expected_scopes_for_frames"]:
                    # print(f"DebugManager: Requesting scopes for frame {frame_id} (base_seq {base_request_seq})")
                    self._request_scopes(frame_id, base_request_seq)
                    paused_info["expected_scopes_for_frames"][frame_id] = "requested"
                all_scopes_for_all_frames_received = False

        if not all_scopes_for_all_frames_received:
            # print(f"DebugManager: Waiting for some scope responses for seq {base_request_seq}")
            return # Still waiting for some scope responses

        # All scopes for all stack frames are now in paused_info["scopes_responses"]
        # Now, for each scope, check if its variables have been requested and received.
        parsed_variables_data = [] # This will be a list of variable dicts
        all_variables_for_all_scopes_received = True # Assume true

        for scope_response_msg in paused_info.get("scopes_responses", []):
            scopes_body = scope_response_msg.get("body", {})
            for scope_dap in scopes_body.get("scopes", []):
                variables_reference = scope_dap.get("variablesReference")
                scope_name = scope_dap.get("name", "<unknown_scope>")

                if variables_reference > 0: # This scope has variables that can be fetched
                    scope_variables_received = any(
                        vr.get("request", {}).get("arguments", {}).get("variablesReference") == variables_reference
                        for vr in paused_info.get("variables_responses", [])
                    )

                    if not scope_variables_received:
                        if variables_reference not in paused_info["expected_variables_for_scopes"]:
                            # print(f"DebugManager: Requesting variables for scope_ref {variables_reference} (base_seq {base_request_seq})")
                            self._request_variables(variables_reference, base_request_seq)
                            paused_info["expected_variables_for_scopes"][variables_reference] = "requested"
                        all_variables_for_all_scopes_received = False
                    else:
                        # Variables for this scope have been received, find the corresponding response
                        var_response_msg = next((
                            vr for vr in paused_info["variables_responses"]
                            if vr.get("request", {}).get("arguments", {}).get("variablesReference") == variables_reference
                        ), None)
                        if var_response_msg:
                            variables_body = var_response_msg.get("body", {})
                            for var_dap in variables_body.get("variables", []):
                                parsed_variables_data.append({
                                    "name": var_dap.get("name"),
                                    "value": var_dap.get("value", ""),
                                    "type": var_dap.get("type", ""),
                                    "variablesReference": var_dap.get("variablesReference", 0), # For expandable vars
                                    "scope": scope_name # Add scope name for context in UI
                                })
                        # else: This should ideally not happen if scope_variables_received was true.

        if not all_variables_for_all_scopes_received:
            # print(f"DebugManager: Waiting for some variable responses for seq {base_request_seq}")
            return # Still waiting for some variable responses

        # All data (stack, scopes, variables for all scopes) has been gathered.
        # Emit the 'paused' signal.
        self.output_received.emit("adapter_info", f"Paused state fully processed for thread {paused_info['thread_id']}. Emitting 'paused' signal.\n")
        self.paused.emit(
            paused_info["thread_id"],
            paused_info["reason"],
            parsed_call_stack,
            parsed_variables_data
        )

        # Highlight the current execution line
        if parsed_call_stack:
            top_frame = parsed_call_stack[0]
            if top_frame.get("file") and top_frame.get("line", 0) > 0:
                 # self.execution_location_changed.emit(top_frame["file"], top_frame["line"]) # Currently not used by MainWindow
                 pass # MainWindow will get this from 'paused' signal

        # Clean up this specific pending response from the dictionary
        if base_request_seq in self._dap_request_pending_response:
            del self._dap_request_pending_response[base_request_seq]
        # print(f"DebugManager: Cleaned up pending response for seq {base_request_seq}")

    def _request_stack_trace(self, thread_id: int, base_request_seq: int):
        # This method is now implicitly called by _handle_dap_event for 'stopped' event.
        # The _send_dap_request in _handle_dap_event for "stackTrace" serves this purpose.
        # This stub can be removed if not called from anywhere else, or kept as pass.
        # For clarity of the new strategy, it's better if _handle_dap_event directly calls _send_dap_request.
        # The original plan had this as a separate method, but it's more integrated now.
        pass # Logic moved to _handle_dap_event -> _send_dap_request("stackTrace", ...)

    def _request_scopes(self, frame_id: int, base_request_seq: int):
        # This method is called by _try_process_paused_state.
        # It sends a 'scopes' request and uses base_request_seq to link it to the ongoing paused event data collection.
        # print(f"DAP SEND (scopes for frame {frame_id}, base_seq {base_request_seq})") # Debug
        self._send_dap_request("scopes", {"frameId": frame_id}, request_id=base_request_seq)

    def _request_variables(self, variables_reference: int, base_request_seq: int):
        # This method is called by _try_process_paused_state.
        # It sends a 'variables' request and uses base_request_seq for linking.
        # print(f"DAP SEND (variables for ref {variables_reference}, base_seq {base_request_seq})") # Debug
        self._send_dap_request("variables", {"variablesReference": variables_reference}, request_id=base_request_seq)

    # --- Public API Methods (Slots for MainWindow) ---
    @Slot(str)
    def start_session(self, program_path: str):
        if self.is_session_active:
            self.dap_error.emit("Debug session is already active or starting.")
            return

        self.current_program_path = os.path.abspath(program_path)
        if not os.path.exists(self.current_program_path):
            self.dap_error.emit(f"Program path does not exist: {self.current_program_path}")
            return

        self.is_session_active = True # Mark that a session start has been requested by the user
        self.output_received.emit("adapter_info", f"Attempting to start debug session for: {self.current_program_path}\n")

        # Example for debugpy: Start adapter, it prints port, then we connect & initialize.
        # The actual adapter command might need to be configurable in the future.
        adapter_cmd = ["python", "-m", "debugpy.adapter"]
        # For other adapters like cpptools, this command would be different, e.g., ["path/to/cpptools/debugAdapters/OpenDebugAD7"]

        if not self._start_debug_adapter(adapter_cmd):
            self.output_received.emit("adapter_error", "Failed to start the debug adapter process.\n")
            # _start_debug_adapter emits dap_error and cleans up its own state.
            self.is_session_active = False # Reset if adapter process itself failed to start
            self.session_stopped.emit() # Notify UI that the session attempt failed early
            return

        # At this point, DAP process is started (or starting).
        # Connection to socket and DAP initialization sequence will follow based on adapter output (port) or fixed port.
        # The session_started signal will be emitted by _handle_dap_response after 'launch' or 'attach' is successful.

    @Slot()
    def stop_session(self):
        # This method can be called by user or internally (e.g., on 'terminated' event or errors)
        if not self.is_session_active and not self.is_adapter_running and not self.is_socket_connected:
            # self.output_received.emit("adapter_info", "No active debug session or components to stop.\n") # Can be noisy
            return

        self.output_received.emit("adapter_info", "Stopping debug session requested...\n")

        # Gracefully try to terminate the debuggee if it was launched by this session
        if self.is_target_launched and self.is_socket_connected:
            self.output_received.emit("adapter_info", "Sending DAP 'disconnect' request to terminate debuggee...\n")
            # terminateDebuggee=True asks adapter to try and terminate the target.
            # Some adapters might also support a 'terminate' request.
            self._send_dap_request("disconnect", {"terminateDebuggee": True})
            # After this, we expect the adapter to send a 'terminated' event, then close the socket,
            # or we might need to forcefully close after a timeout.
            # For now, _handle_dap_disconnect will be called by recv_loop or errors.

        # Perform immediate cleanup of our side
        self._handle_dap_disconnect()   # Cleans up socket, DAP state, emits session_stopped if was active
        self._cleanup_dap_process_state() # Stops the DAP QProcess and cleans its state

        # Ensure is_session_active is false after all cleanup, even if session_stopped was emitted by _handle_dap_disconnect
        # self.is_session_active = False # This is handled in _handle_dap_disconnect now
        self.output_received.emit("adapter_info", "Debug session stop process completed.\n")

    def _handle_dap_disconnect(self): # Centralized disconnect logic
        # print("DebugManager: _handle_dap_disconnect called.") # Debug log
        was_session_active_before_disconnect = self.is_session_active

        self._reset_socket_state() # Close socket, join thread, clear buffer, set is_socket_connected=False

        # Reset DAP state flags
        self.is_adapter_initialized = False
        self.is_target_launched = False
        self._dap_port = None # Reset port so it can be re-parsed if adapter restarts
        self._current_thread_id_for_stepping = None
        self._dap_request_pending_response.clear() # Clear any pending requests
        self._connect_retry_timer.stop() # Stop any pending connection retries

        # Only emit session_stopped if the session was considered active from user's perspective
        # or if target was launched. Avoid emitting if it was just an adapter failing to start internally.
        if was_session_active_before_disconnect:
            self.session_stopped.emit()
            # print("DebugManager: Emitted session_stopped.") # Debug log

        self.is_session_active = False # Final flag indicating session is fully down
        self.output_received.emit("adapter_info", "DAP connection ended and state reset.\n")

    def _send_step_command(self, dap_command: str):
        if not self.is_target_launched or not self.is_socket_connected:
            self.dap_error.emit(f"Cannot {dap_command}: Debug target not launched or not connected.")
            return
        if not self._current_thread_id_for_stepping:
            self.dap_error.emit(f"Cannot {dap_command}: No current paused thread ID available.")
            return

        self.output_received.emit("adapter_info", f"Sending DAP '{dap_command}' request (thread {self._current_thread_id_for_stepping})...\n")
        self._send_dap_request(dap_command, {"threadId": self._current_thread_id_for_stepping})
        # State change (e.g., to resumed, then stopped again) will come via DAP events.

    @Slot()
    def continue_execution(self):
        self._send_step_command("continue")

    @Slot()
    def step_over(self):
        self._send_step_command("next")

    @Slot()
    def step_into(self):
        self._send_step_command("stepIn")

    @Slot()
    def step_out(self):
        self._send_step_command("stepOut")

    @Slot(str, object) # Path (str), lines (set of int)
    def update_internal_breakpoints(self, file_path: str, lines_set: set):
        # Ensure paths are normalized for consistent dictionary keys
        norm_path = os.path.normpath(file_path)
        if not lines_set: # If set is empty, remove path from tracking
            self.current_breakpoints.pop(norm_path, None)
            # print(f"DebugManager: Cleared internal breakpoints for {norm_path}")
        else:
            self.current_breakpoints[norm_path] = set(lines_set) # Ensure it's a set
            # print(f"DebugManager: Updated internal breakpoints for {norm_path}: {self.current_breakpoints[norm_path]}")

        # If a DAP session is fully up and running (adapter initialized and target launched/attached),
        # send this breakpoint update to the adapter immediately.
        # Otherwise, breakpoints will be sent by _send_breakpoints_to_adapter_after_init().
        if self.is_session_active and self.is_adapter_initialized: # and self.is_target_launched:
            # Some adapters prefer setting BPs before launch/attach is fully complete (after initialize is enough)
            self.set_breakpoints_on_adapter(norm_path, list(self.current_breakpoints.get(norm_path, [])))

    @Slot(str, list) # Path (str), lines (list of int)
    def set_breakpoints_on_adapter(self, file_path: str, lines_list: list):
        if not self.is_adapter_initialized or not self.is_socket_connected:
            # self.dap_error.emit("Cannot set breakpoints: Adapter not initialized or not connected.")
            # print(f"DebugManager: Cannot set breakpoints for {file_path}. Adapter not ready.")
            # It's okay if this is called early; they are cached in self.current_breakpoints
            # and will be sent by _send_breakpoints_to_adapter_after_init.
            return

        abs_file_path = os.path.abspath(os.path.normpath(file_path))
        dap_breakpoints = [{"line": line} for line in lines_list] # DAP lines are 1-based

        # self.output_received.emit("adapter_info", f"Sending/updating breakpoints for {abs_file_path}: {lines_list}\n")
        self._send_dap_request("setBreakpoints", {
            "source": {"path": abs_file_path, "name": os.path.basename(abs_file_path)},
            "breakpoints": dap_breakpoints,
            "sourceModified": False # Assume source on disk is not modified for BP setting
        })

    # --- Cleanup ---
    def __del__(self):
        print("DebugManagerRefactored: __del__ called. Ensuring session is stopped.")
        self.stop_session() # Ensure all resources are cleaned up
