import json
import socket # For finding an open port
from contextlib import closing
import sys # For sys.executable
from PySide6.QtCore import QObject, Signal, QProcess, QTcpSocket, QThread, QTimer
from PySide6.QtNetwork import QAbstractSocket # For error types if needed

class DebugManager(QObject):
    # Signals
    session_started = Signal()
    session_stopped = Signal()
    # For paused: thread_id (int), reason (str), call_stack (list of dicts), variables (list of dicts)
    # Example for call_stack item: {'id': frame_id, 'name': frame_name, 'file': file_path, 'line': line_num}
    # Example for variables item: {'name': var_name, 'type': var_type, 'value': var_value, 'variablesReference': ref_id_for_children}
    paused = Signal(int, str, list, list)
    resumed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.dap_client = None  # QTcpSocket for DAP communication
        self.debugger_process = None  # QProcess for the user's script with debugpy

        self.breakpoints = {}

        self.host = "127.0.0.1"
        self.port = 0 # Will be dynamically assigned

        self._dap_seq = 1
        self._buffer = bytearray()

        self._active_thread_id = None
        self._call_stack_data = []
        self._variables_data = []
        self._scopes_references = {}
        self._pending_variable_requests = 0

        self._connect_timer = QTimer(self)
        self._connect_timer.setSingleShot(True)
        self._connect_timer.timeout.connect(self._handle_connect_timeout)

        self._dap_request_pending_response = {}
        self._pending_breakpoint_sync_count = 0
        self._current_stop_reason = ""

    def _get_next_dap_seq(self):
        current_seq = self._dap_seq
        self._dap_seq += 1
        return current_seq

    def _handle_connect_timeout(self):
        print("DebugManager: Connection to debugpy timed out.")
        if self.dap_client:
            self.dap_client.abort()
        if self.debugger_process and self.debugger_process.state() != QProcess.ProcessState.NotRunning:
            print("DebugManager: Terminating debugger process due to connection timeout.")
            self.debugger_process.terminate()
            if not self.debugger_process.waitForFinished(1000):
                self.debugger_process.kill()
        self.session_stopped.emit()

    def _find_free_port(self):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind((self.host, 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    def _send_dap_request(self, command: str, arguments: dict = None, request_seq_to_store=None):
        if not self.dap_client or not self.dap_client.isOpen():
            print(f"DebugManager Error: DAP client not connected. Cannot send {command}.")
            return

        request_seq = self._get_next_dap_seq()
        request = {
            "seq": request_seq,
            "type": "request",
            "command": command
        }
        if arguments is not None:
            request["arguments"] = arguments

        # If request_seq_to_store is provided, it means this request is part of a sequence
        # or we want to track its specific response using its own sequence number.
        # For now, let's use the request's own sequence number to track its response.
        if request_seq_to_store is None:
            request_seq_to_store = request_seq # Default to tracking response for this request

        self._dap_request_pending_response[request_seq_to_store] = command
        # Storing command to know what response we are waiting for.

        json_request = json.dumps(request).encode('utf-8')
        header = f"Content-Length: {len(json_request)}\r\n\r\n".encode('utf-8')

        self.dap_client.write(header + json_request)
        print(f"DAP Sent: {request}")

    def _handle_dap_ready_read(self):
        if not self.dap_client:
            return

        self._buffer.extend(self.dap_client.readAll().data())

        while True:
            try:
                content_length_header_start = self._buffer.find(b"Content-Length: ")
                if content_length_header_start == -1:
                    break # Need more data for header

                header_end_marker = b"\r\n\r\n"
                header_end_pos = self._buffer.find(header_end_marker, content_length_header_start)
                if header_end_pos == -1:
                    break # Need more data for header end

                content_length_str = self._buffer[content_length_header_start + len(b"Content-Length: "):header_end_pos].decode('utf-8')
                content_length = int(content_length_str)

                json_start_pos = header_end_pos + len(header_end_marker)
                total_message_size = json_start_pos + content_length

                if len(self._buffer) < total_message_size:
                    break # Message incomplete

                message_bytes = self._buffer[:total_message_size]
                self._buffer = self._buffer[total_message_size:] # Consume message from buffer

                json_payload_bytes = message_bytes[json_start_pos:]
                json_payload = json_payload_bytes.decode('utf-8')
                dap_message = json.loads(json_payload)

                print(f"DAP Recv: {dap_message}")
                self._dispatch_dap_message(dap_message)

                # If a message was processed, continue to check for more in buffer
                continue
            except ValueError as e: # Includes JSONDecodeError
                print(f"DebugManager Error: Could not parse DAP message header or JSON: {e}")
                # Potentially clear buffer or handle malformed message
                # For now, break and wait for more data, assuming it might be a partial message
                break
            except Exception as e:
                print(f"DebugManager Error: Unexpected error processing DAP message: {e}")
                # Consider clearing buffer or more robust error handling
                break # Stop processing to avoid error loops

    def _dispatch_dap_message(self, message: dict):
        msg_type = message.get("type")
        if msg_type == "event":
            self._handle_dap_event(message)
        elif msg_type == "response":
            request_seq = message.get("request_seq")
            # Check if we were waiting for this response
            if request_seq in self._dap_request_pending_response:
                # Potentially use the command stored in _dap_request_pending_response[request_seq]
                # to guide handling, then remove it.
                del self._dap_request_pending_response[request_seq]
            else:
                print(f"DebugManager Warning: Received response for untracked request_seq: {request_seq}")
            self._handle_dap_response(message)
        else:
            print(f"DebugManager Warning: Unknown DAP message type received: {msg_type}")

    def _handle_dap_event(self, event_message: dict):
        event_name = event_message.get("event")
        body = event_message.get("body", {})
        print(f"DAP Event Received: {event_name}, Body: {body}")

        if event_name == "stopped":
            print("DebugManager: Received 'stopped' event.")
            thread_id = body.get("threadId")
            reason = body.get("reason", "unknown")
            if thread_id is None:
                print("DebugManager Error: 'stopped' event received without threadId.")
                return

            self._active_thread_id = thread_id
            self._current_stop_reason = reason # Store reason
            self._call_stack_data.clear()
            self._variables_data.clear()
            self._scopes_references.clear()

            print(f"DebugManager: Requesting stack trace for thread {thread_id}.")
            self._send_dap_request("stackTrace", arguments={"threadId": thread_id}, request_seq_to_store=f"stackTrace_{thread_id}")

        elif event_name == "continued":
            print("DebugManager: Received 'continued' event.")
            thread_id = body.get("threadId")
            # If allThreadsContinued is true, or if the specific thread that was active is continued
            if body.get("allThreadsContinued", True) or thread_id == self._active_thread_id:
                self.resumed.emit()
                self._active_thread_id = None # No longer actively stopped in this thread
                self._current_stop_reason = ""
                self._call_stack_data.clear()
                self._variables_data.clear()
                self._scopes_references.clear()

        elif event_name == "terminated":
            print("DebugManager: Received 'terminated' event. Stopping session.")
            self.stop_session() # This will emit session_stopped

        elif event_name == "output":
            category = body.get("category", "console")
            output = body.get("output", "")
            print(f"DAP Output ({category}): {output.strip()}")
            # Later, route this to a debug console in MainWindow via a signal

        elif event_name == "module":
            # Optional: good for debugging DAP communication
            print(f"DAP Module Event: Reason: {body.get('reason')}, Module: {body.get('module')}")

        elif event_name == "thread":
            # Optional: good for debugging DAP communication
            print(f"DAP Thread Event: Reason: {body.get('reason')}, Thread ID: {body.get('threadId')}")


    def _handle_dap_response(self, response_message: dict):
        request_command = response_message.get("command")
        success = response_message.get("success", False)
        request_seq = response_message.get("request_seq") # Used for logging/debugging specific requests

        print(f"DAP Response for '{request_command}' (req_seq: {request_seq}): Success={success}, Body: {response_message.get('body')}")

        if request_command == "initialize":
            if success:
                print("DebugManager: Initialize successful.")
                self._dap_request_pending_response['initialize_complete'] = True
                # Launch the debugger. For debugpy, 'program' is often optional if script was passed at launch.
                # Sending it as None or omitting it might be necessary.
                # If debugpy was started with --wait-for-client and the script, this launch request might be
                # more of a formality or for specific launch configurations not used here.
                # Some debug adapters might not need a separate "launch" after "attach" if script is pre-specified.
                # Let's assume a simple launch is fine.
                self._send_dap_request("launch", arguments={"program": None}, request_seq_to_store="launch")
            else:
                print("DebugManager Error: Initialize failed!")
                self.stop_session()

        elif request_command == "launch":
            if success:
                print("DebugManager: Launch successful.")
                self._dap_request_pending_response['launch_complete'] = True
                self._synchronize_all_breakpoints_on_startup()
            else:
                print("DebugManager Error: Launch failed!")
                self.stop_session()

        elif request_command == "setBreakpoints":
            # Response body contains actual breakpoints set by the adapter
            # For now, just log it. We might use this to update our internal state if needed.
            print(f"DebugManager: Breakpoints set for request_seq {request_seq}. Body: {response_message.get('body')}")
            if self._pending_breakpoint_sync_count > 0:
                self._pending_breakpoint_sync_count -= 1
                if self._pending_breakpoint_sync_count == 0:
                    print("DebugManager: All initial breakpoints synchronized. Sending ConfigurationDone.")
                    self._send_dap_request("configurationDone", request_seq_to_store="configurationDone")

        elif request_command == "configurationDone":
            if success:
                print("DebugManager: ConfigurationDone successful. Debug session should be running.")
                self._dap_request_pending_response['handshake_complete'] = True
                self.session_started.emit()
            else:
                print("DebugManager Error: ConfigurationDone failed!")
                self.stop_session()

        # Handle other responses like stackTrace, scopes, variables in later steps
        body = response_message.get("body", {})

        if request_command == "stackTrace":
            if success:
                stack_frames = body.get("stackFrames", [])
                self._call_stack_data.clear() # Clear previous stack data
                for frame in stack_frames:
                    frame_id = frame.get("id")
                    frame_name = frame.get("name", "Unknown Frame")
                    source_info = frame.get("source", {})
                    file_path = source_info.get("path", source_info.get("name", "Unknown File"))
                    line_num = frame.get("line", 0)
                    self._call_stack_data.append({"id": frame_id, "name": frame_name, "file": file_path, "line": line_num})

                if self._call_stack_data: # If we have frames
                    top_frame_id = self._call_stack_data[0]["id"]
                    print(f"DebugManager: Requesting scopes for top frame {top_frame_id}.")
                    self._send_dap_request("scopes", arguments={"frameId": top_frame_id}, request_seq_to_store=f"scopes_{top_frame_id}")
                else: # No stack frames, unusual if stopped.
                    print("DebugManager: No stack frames received, cannot fetch variables.")
                    self.paused.emit(self._active_thread_id, self._current_stop_reason, [], [])
            else:
                print("DebugManager Error: stackTrace request failed.")
                self.paused.emit(self._active_thread_id, self._current_stop_reason, [], []) # Emit with empty data

        elif request_command == "scopes":
            if success:
                self._scopes_references.clear() # Clear old scope references
                self._variables_data.clear()    # Clear old variable data
                scopes = body.get("scopes", [])
                self._pending_variable_requests = 0
                for scope in scopes:
                    scope_name = scope.get("name")
                    variables_reference = scope.get("variablesReference")
                    if variables_reference > 0: # DAP spec: 0 means no variables/children
                        self._scopes_references[scope_name] = variables_reference
                        print(f"DebugManager: Requesting variables for scope '{scope_name}' (ref: {variables_reference}).")
                        self._send_dap_request("variables", arguments={"variablesReference": variables_reference}, request_seq_to_store=f"variables_{variables_reference}")
                        self._pending_variable_requests += 1

                if self._pending_variable_requests == 0: # No scopes or no valid variable references
                    print("DebugManager: No variables to request from scopes.")
                    self.paused.emit(self._active_thread_id, self._current_stop_reason, list(self._call_stack_data), [])
            else:
                print("DebugManager Error: scopes request failed.")
                self.paused.emit(self._active_thread_id, self._current_stop_reason, list(self._call_stack_data), [])

        elif request_command == "variables":
            if success:
                variables = body.get("variables", [])
                for var in variables:
                    self._variables_data.append({
                        "name": var.get("name"),
                        "type": var.get("type", "Unknown Type"),
                        "value": var.get("value", "N/A"),
                        "variablesReference": var.get("variablesReference", 0) # For expandable objects
                    })
            else: # variables request failed
                print(f"DebugManager Error: variables request failed for request_seq {request_seq}.")

            # This logic handles responses for variables from potentially multiple scopes
            if self._pending_variable_requests > 0: # Should always be true if we are here from a successful scopes req
                 self._pending_variable_requests -= 1

            if self._pending_variable_requests == 0: # All variable requests for this stop event are processed
                print("DebugManager: All variable requests complete.")
                self.paused.emit(self._active_thread_id, self._current_stop_reason, list(self._call_stack_data), list(self._variables_data))


    def _synchronize_all_breakpoints_on_startup(self):
        print("DebugManager: Synchronizing all breakpoints on startup.")
        if not self.breakpoints: # self.breakpoints is path -> {lines}
            print("DebugManager: No breakpoints to synchronize. Sending ConfigurationDone directly.")
            self._send_dap_request("configurationDone", request_seq_to_store="configurationDone")
            return

        self._pending_breakpoint_sync_count = len(self.breakpoints)

        for file_path, lines_set in self.breakpoints.items():
            if not lines_set: # Should not happen if update_internal_breakpoints cleans up empty sets
                self._pending_breakpoint_sync_count -=1
                continue

            # DAP paths are typically absolute local paths.
            # No URI conversion needed for debugpy with local paths.
            bp_args = {
                "source": {"path": file_path},
                "breakpoints": [{"line": l} for l in sorted(list(lines_set))]
            }
            # Use a unique seq store key for each file's breakpoints request
            self._send_dap_request("setBreakpoints", arguments=bp_args, request_seq_to_store=f"setBreakpoints_startup_{file_path}")

        # If, after queuing, there are no pending syncs (e.g., all paths had empty line sets)
        if self._pending_breakpoint_sync_count == 0:
            print("DebugManager: All breakpoint sets were empty. Sending ConfigurationDone.")
            self._send_dap_request("configurationDone", request_seq_to_store="configurationDone")


    def _handle_dap_connected(self):
        self._connect_timer.stop()
        print("DebugManager: DAP client connected to debugpy.")
        # Initiate DAP handshake
        self._send_dap_request(
            "initialize",
            arguments={
                "adapterID": "python",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "pathFormat": "path",
                # Add any other capabilities your client supports
                "supportsVariableType": True,
                "supportsVariablePaging": True,
                "supportsRunInTerminalRequest": True,
            },
            request_seq_to_store="initialize" # Track this specific request
        )

    def _handle_dap_disconnected(self):
        print("DebugManager: DAP client disconnected.")
        self.stop_session() # Ensure full cleanup

    def _handle_dap_socket_error(self, error: QAbstractSocket.SocketError):
        # socket_error = self.dap_client.error() # QAbstractSocket.SocketError enum
        error_string = self.dap_client.errorString() if self.dap_client else "Unknown socket error"
        print(f"DebugManager: DAP socket error: {error} - {error_string}")
        if self._connect_timer.isActive(): # If error occurred during connection attempt
            self._connect_timer.stop()
        self.stop_session() # Ensure full cleanup

    def _handle_debugger_process_error(self, error: QProcess.ProcessError):
        error_map = {
            QProcess.ProcessError.FailedToStart: "FailedToStart",
            QProcess.ProcessError.Crashed: "Crashed",
            QProcess.ProcessError.Timedout: "Timedout",
            QProcess.ProcessError.ReadError: "ReadError",
            QProcess.ProcessError.WriteError: "WriteError",
            QProcess.ProcessError.UnknownError: "UnknownError"
        }
        error_name = error_map.get(error, "UnknownError")
        print(f"DebugManager: Debugger process error: {error_name}")
        # If the process failed to start, it's a critical session issue.
        if error == QProcess.ProcessError.FailedToStart:
            self.stop_session()

    def _handle_debugger_process_finished(self, exit_code, exit_status: QProcess.ExitStatus):
        status_map = {
            QProcess.ExitStatus.NormalExit: "NormalExit",
            QProcess.ExitStatus.CrashExit: "CrashExit"
        }
        status_name = status_map.get(exit_status, "UnknownExitStatus")
        print(f"DebugManager: Debugger process finished. Exit code: {exit_code}, Exit status: {status_name}")
        self.stop_session() # Ensure full cleanup and emit session_stopped

    def _handle_debugger_process_stdout(self):
        if self.debugger_process:
            data = self.debugger_process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            print(f"Debugger STDOUT: {data.strip()}")

    def _handle_debugger_process_stderr(self):
        if self.debugger_process:
            data = self.debugger_process.readAllStandardError().data().decode('utf-8', errors='replace')
            print(f"Debugger STDERR: {data.strip()}")


    def start_session(self, script_path: str):
        print(f"DebugManager: Attempting to start session for {script_path}")
        self.stop_session() # Clean up any existing session first

        self.port = self._find_free_port()
        if self.port == 0:
            print("DebugManager Error: Could not find a free port.")
            self.session_stopped.emit()
            return

        print(f"DebugManager: Found free port: {self.port}")

        command = [sys.executable, "-m", "debugpy", "--listen", f"{self.host}:{self.port}", "--wait-for-client", script_path]

        self.debugger_process = QProcess(self)
        self.debugger_process.errorOccurred.connect(self._handle_debugger_process_error)
        self.debugger_process.finished.connect(self._handle_debugger_process_finished)
        self.debugger_process.readyReadStandardOutput.connect(self._handle_debugger_process_stdout)
        self.debugger_process.readyReadStandardError.connect(self._handle_debugger_process_stderr)

        print(f"DebugManager: Starting process: {' '.join(command)}")
        self.debugger_process.start(command[0], command[1:])

        if not self.debugger_process.waitForStarted(5000): # 5-second timeout
            print("DebugManager Error: Debugger process failed to start.")
            # errorOccurred might have already called stop_session, but call it defensively.
            self.stop_session()
            return

        print(f"DebugManager: Debugger process started (PID: {self.debugger_process.processId()}). Connecting DAP client...")

        self.dap_client = QTcpSocket(self)
        self.dap_client.connected.connect(self._handle_dap_connected)
        self.dap_client.disconnected.connect(self._handle_dap_disconnected)
        self.dap_client.readyRead.connect(self._handle_dap_ready_read)
        # Corrected signal name for QTcpSocket based on typical Qt naming
        self.dap_client.errorOccurred.connect(self._handle_dap_socket_error)

        self.dap_client.connectToHost(self.host, self.port)
        self._connect_timer.start(10000) # 10-second timeout for DAP connection

    def stop_session(self):
        print("DebugManager: Attempting to stop session...")
        if self._connect_timer.isActive():
            self._connect_timer.stop()

        # Try to gracefully disconnect from the debugger
        if self.dap_client and self.dap_client.isOpen():
            if self._dap_request_pending_response.get('handshake_complete', False) or \
               self._dap_request_pending_response.get('initialize_complete', False): # Check if we even started handshake
                print("DebugManager: Sending disconnect request to DAP server.")
                # TerminateDebuggee argument might be configurable later
                self._send_dap_request("disconnect", arguments={"terminateDebuggee": True}, request_seq_to_store="disconnect")
                # We might want a short wait here or handle the disconnect response,
                # but for now, we'll proceed to cleanup. If disconnect is successful,
                # debugpy might terminate the process itself.
            else:
                # If no handshake, just abort the connection.
                self.dap_client.abort()

            # It's safer to schedule deletion after the current event loop finishes
            self.dap_client.deleteLater()
            self.dap_client = None

        if self.debugger_process:
            if self.debugger_process.state() != QProcess.ProcessState.NotRunning:
                print(f"DebugManager: Terminating debugger process (PID: {self.debugger_process.processId()}).")
                self.debugger_process.terminate()
                if not self.debugger_process.waitForFinished(2000): # Shorter timeout after disconnect attempt
                    print("DebugManager: Debugger process did not terminate gracefully after disconnect, killing.")
                    self.debugger_process.kill()
            self.debugger_process.deleteLater()
            self.debugger_process = None

        # Reset state variables
        self.breakpoints.clear()
        self._active_thread_id = None
        self._current_stop_reason = ""
        self._call_stack_data.clear()
        self._variables_data.clear()
        self._scopes_references.clear()
        self._pending_variable_requests = 0
        self._pending_breakpoint_sync_count = 0
        self._buffer = bytearray()
        self._dap_seq = 1 # Reset sequence for next session
        self.port = 0 # Reset port

        # Clear any pending response flags, including handshake stages
        self._dap_request_pending_response.clear()

        self.session_stopped.emit()
        print("DebugManager: Session stop finalized and signal emitted.")


    def continue_execution(self, thread_id=None):
        if not self.dap_client or not self.dap_client.isOpen() or self._active_thread_id is None:
            print("DebugManager Warning: Cannot continue. DAP client not connected or not paused.")
            return
        target_thread_id = thread_id if thread_id is not None else self._active_thread_id
        print(f"DebugManager: Sending 'continue' request for thread {target_thread_id}.")
        self._send_dap_request("continue", arguments={"threadId": target_thread_id}, request_seq_to_store="continue")
        # DAP server will send a 'continued' event if successful.

    def step_over(self, thread_id=None):
        if not self.dap_client or not self.dap_client.isOpen() or self._active_thread_id is None:
            print("DebugManager Warning: Cannot step over. DAP client not connected or not paused.")
            return
        target_thread_id = thread_id if thread_id is not None else self._active_thread_id
        print(f"DebugManager: Sending 'next' (step over) request for thread {target_thread_id}.")
        self._send_dap_request("next", arguments={"threadId": target_thread_id}, request_seq_to_store="next")

    def step_into(self, thread_id=None):
        if not self.dap_client or not self.dap_client.isOpen() or self._active_thread_id is None:
            print("DebugManager Warning: Cannot step into. DAP client not connected or not paused.")
            return
        target_thread_id = thread_id if thread_id is not None else self._active_thread_id
        print(f"DebugManager: Sending 'stepIn' request for thread {target_thread_id}.")
        self._send_dap_request("stepIn", arguments={"threadId": target_thread_id}, request_seq_to_store="stepIn")

    def step_out(self, thread_id=None):
        if not self.dap_client or not self.dap_client.isOpen() or self._active_thread_id is None:
            print("DebugManager Warning: Cannot step out. DAP client not connected or not paused.")
            return
        target_thread_id = thread_id if thread_id is not None else self._active_thread_id
        print(f"DebugManager: Sending 'stepOut' request for thread {target_thread_id}.")
        self._send_dap_request("stepOut", arguments={"threadId": target_thread_id}, request_seq_to_store="stepOut")

    def set_breakpoints_on_adapter(self, file_path: str, lines: list): # lines is a list here
        if not self.dap_client or not self.dap_client.isOpen():
            print("DebugManager Error: DAP client not connected. Cannot set breakpoints on adapter.")
            return

        # It's generally okay to send breakpoints even if handshake isn't "fully" complete,
        # as long as "initialize" response has been received and processed.
        # Adapters usually queue these if "launch/attach" isn't done yet.
        # However, the _synchronize_all_breakpoints_on_startup handles initial ones.
        # This method is for dynamic updates.
        if not self._dap_request_pending_response.get('initialize_complete', False):
             print("DebugManager Warning: DAP 'initialize' not yet complete. Breakpoint setting might be queued by adapter or fail.")
        # No longer strictly checking for 'handshake_complete' to allow more flexibility,
        # especially if user modifies breakpoints before 'configurationDone' response.

        bp_args = {
            "source": {"path": file_path},
            "breakpoints": [{"line": l} for l in sorted(list(lines))] # Ensure it's a list of unique, sorted lines
        }
        print(f"DebugManager: Sending dynamic setBreakpoints for {file_path} with lines: {lines}")
        self._send_dap_request("setBreakpoints", arguments=bp_args, request_seq_to_store=f"setBreakpoints_dynamic_{file_path}")


    def update_internal_breakpoints(self, file_path: str, lines: set):
        if not lines:
            if file_path in self.breakpoints:
                del self.breakpoints[file_path]
        else:
            self.breakpoints[file_path] = set(lines)

        if self.dap_client and self.dap_client.isOpen() and self._dap_request_pending_response.get('handshake_complete'):
             self.set_breakpoints_on_adapter(file_path, list(lines))


if __name__ == '__main__':
    from PySide6.QtCore import QCoreApplication
    import sys

    app = QCoreApplication(sys.argv)
    manager = DebugManager()

    manager.session_started.connect(lambda: print("Test: Session Started!"))
    manager.session_stopped.connect(lambda: print("Test: Session Stopped!"))
    manager.paused.connect(lambda tid, r, cs, var: print(f"Test: Paused (Thread: {tid}, Reason: {r})"))
    manager.resumed.connect(lambda: print("Test: Resumed!"))

    print("DebugManager instance created.")
    # app.exec()
