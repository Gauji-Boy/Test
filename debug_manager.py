import json
import re
from PySide6.QtCore import QObject, Signal, QProcess, QByteArray, QTimer
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket

class DebugManager(QObject):
    # DAP Signals
    dap_initialized = Signal()
    dap_launched = Signal()
    dap_terminated = Signal()
    dap_output = Signal(str, str)
    dap_event = Signal(str, dict)
    dap_error = Signal(str)

    # Debugger State Signals
    breakpoint_hit = Signal(str, int, int, dict)
    threads_received = Signal(list)
    stack_frames_received = Signal(list)
    scopes_received = Signal(list)
    variables_received = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dap_process = None
        self.dap_socket = None
        self.dap_host = '127.0.0.1'
        self.dap_port = 0
        self.seq = 0
        self.buffer = bytearray()
        self.content_length = -1
        self.breakpoints = {}
        self.is_debugging = False
        self.capabilities = {}
        self.dap_port_found_event = QTimer(self)
        self.dap_port_found_event.setSingleShot(True)

    # --- DAP Server Process Management ---
    def start_dap_server(self, dap_command: list, dap_working_dir: str):
        if self.dap_process and self.dap_process.state() != QProcess.ProcessState.NotRunning:
            self.dap_error.emit(f"DAP server process is already running (PID: {self.dap_process.processId()}).")
            return
        if not dap_command:
            self.dap_error.emit("No DAP server command provided.")
            return
        self.dap_process = QProcess(self)
        self.dap_process.setWorkingDirectory(dap_working_dir)
        self.dap_process.readyReadStandardOutput.connect(self._handle_dap_server_stdout)
        self.dap_process.readyReadStandardError.connect(self._handle_dap_server_stderr)
        self.dap_process.finished.connect(self._handle_dap_server_finished)
        self.dap_process.errorOccurred.connect(self._handle_dap_server_error)
        executable = dap_command[0]
        args = dap_command[1:]
        print(f"Starting DAP server: {executable} {' '.join(args)} in {dap_working_dir}")
        self.dap_process.start(executable, args)

    def stop_dap_server(self):
        if self.dap_socket and self.dap_socket.isOpen():
            print("Closing DAP socket...")
            self.dap_socket.abort()
        if self.dap_process and self.dap_process.state() != QProcess.ProcessState.NotRunning:
            print("Stopping DAP server process...")
            self.dap_process.terminate()
            if not self.dap_process.waitForFinished(2000):
                print("DAP server did not terminate gracefully, killing.")
                self.dap_process.kill()
                self.dap_process.waitForFinished(1000)
        else:
            print("DAP server process not running or already stopped.")
        self.dap_process = None
        self.is_debugging = False

    def _handle_dap_server_stdout(self):
        if not self.dap_process: return
        data = self.dap_process.readAllStandardOutput().data().decode(errors='replace').strip()
        if data:
            print(f"DAP Server STDOUT: {data}")
            if self.dap_port == 0 or (self.dap_socket and self.dap_socket.state() != QTcpSocket.SocketState.ConnectedState):
                match = re.search(r"(?:port|listening on)\s+(?:[\d\.]+:)?(\d+)", data, re.IGNORECASE)
                if match:
                    try:
                        port = int(match.group(1))
                        if 1024 <= port <= 65535:
                            self.dap_port = port
                            print(f"DAP server port {self.dap_port} found in stdout.")
                            if not self.dap_port_found_event.isActive():
                                self.dap_port_found_event.start(100)
                                self.dap_port_found_event.timeout.connect(self._connect_to_dap_server)
                        else:
                            print(f"Invalid port number parsed from DAP server stdout: {port}")
                    except ValueError:
                        print(f"Could not parse port number from DAP server stdout match: {match.group(1)}")
            self.dap_output.emit("dap_server_stdout", data)

    def _handle_dap_server_stderr(self):
        if not self.dap_process: return
        data = self.dap_process.readAllStandardError().data().decode(errors='replace').strip()
        if data:
            print(f"DAP Server STDERR: {data}")
            self.dap_output.emit("dap_server_stderr", data)

    def _handle_dap_server_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        status_text = "normally" if exit_status == QProcess.ExitStatus.NormalExit else "by crashing"
        message = f"DAP server process finished {status_text} with exit code {exit_code}."
        print(message)
        if exit_code != 0 or exit_status == QProcess.ExitStatus.CrashExit:
            self.dap_error.emit(message)
        self.is_debugging = False
        self.dap_process = None
        if self.dap_socket and self.dap_socket.isOpen():
            self.dap_socket.abort()

    def _handle_dap_server_error(self, error: QProcess.ProcessError):
        if not self.dap_process: q_error_str = "N/A"
        else: q_error_str = self.dap_process.errorString()
        error_map = {
            QProcess.ProcessError.FailedToStart: "DAP server failed to start.",
            QProcess.ProcessError.Crashed: "DAP server crashed.",
            QProcess.ProcessError.Timedout: "DAP server timed out.",
            QProcess.ProcessError.ReadError: "Error reading from DAP server process.",
            QProcess.ProcessError.WriteError: "Error writing to DAP server process.",
            QProcess.ProcessError.UnknownError: "An unknown error occurred with DAP server process."
        }
        error_message = error_map.get(error, "Unspecified DAP server process error.")
        full_message = f"{error_message} Details: {q_error_str}"
        print(full_message)
        self.dap_error.emit(full_message)
        self.is_debugging = False
        self.dap_process = None
        if self.dap_socket and self.dap_socket.isOpen():
            self.dap_socket.abort()

    # --- DAP Socket Communication ---
    def _connect_to_dap_server(self):
        if self.dap_socket and self.dap_socket.isOpen():
            print("DAP socket already open or connecting.")
            return
        if self.dap_port == 0:
            error_msg = "DAP server port not set. Cannot connect."
            self.dap_error.emit(error_msg)
            print(error_msg)
            return
        print(f"Connecting to DAP server at {self.dap_host}:{self.dap_port}...")
        self.dap_socket = QTcpSocket(self)
        self.dap_socket.connected.connect(self._on_dap_socket_connected)
        self.dap_socket.readyRead.connect(self._on_dap_socket_ready_read)
        self.dap_socket.disconnected.connect(self._on_dap_socket_disconnected)
        self.dap_socket.errorOccurred.connect(self._on_dap_socket_error)
        self.dap_socket.connectToHost(self.dap_host, self.dap_port)

    def _on_dap_socket_connected(self):
        print("Successfully connected to DAP server.")
        self.is_debugging = True

    def _on_dap_socket_ready_read(self):
        if not self.dap_socket or not self.dap_socket.isOpen(): return
        self.buffer.extend(self.dap_socket.readAll().data())
        while True:
            if self.content_length == -1:
                header_match = re.search(rb"Content-Length: *(\d+)\r\n\r\n", self.buffer, re.DOTALL | re.MULTILINE)
                if header_match:
                    self.content_length = int(header_match.group(1))
                    self.buffer = self.buffer[header_match.end():]
                else:
                    if len(self.buffer) > 8192:
                        print("DAP buffer too large without complete header, clearing.")
                        self.dap_error.emit("DAP communication error: Buffer overflow, header not found.")
                        self.buffer.clear()
                        if self.dap_socket and self.dap_socket.isOpen(): self.dap_socket.abort()
                        return
                    break
            if self.content_length != -1 and len(self.buffer) >= self.content_length:
                message_body_bytes = self.buffer[:self.content_length]
                self.buffer = self.buffer[self.content_length:]
                self.content_length = -1
                try:
                    message_str = message_body_bytes.decode('utf-8')
                    message_payload = json.loads(message_str)
                    self._handle_dap_message(message_payload)
                except json.JSONDecodeError as e:
                    err_msg = f"DAP JSON decode error: {e}"
                    self.dap_error.emit(err_msg)
                    print(f"{err_msg} - Message part: {message_str[:200]}")
                except UnicodeDecodeError as e:
                    err_msg = f"DAP Unicode decode error: {e}"
                    self.dap_error.emit(err_msg)
                    print(f"{err_msg} - Bytes part: {message_body_bytes[:200]}")
                except Exception as e:
                    err_msg = f"Unexpected error handling DAP message: {e}"
                    self.dap_error.emit(err_msg)
                    print(err_msg)
            else:
                break

    def _on_dap_socket_disconnected(self):
        disconnected_msg = "DAP socket disconnected."
        print(disconnected_msg)
        self.dap_error.emit(disconnected_msg)
        self.is_debugging = False
        if self.dap_socket:
            self.dap_socket.deleteLater()
            self.dap_socket = None

    def _on_dap_socket_error(self, socket_error: QAbstractSocket.SocketError):
        error_string = "Unknown socket error"
        if self.dap_socket:
            error_string = self.dap_socket.errorString()
        print(f"DAP socket error enum {socket_error}: {error_string}")
        self.dap_error.emit(f"DAP connection error: {error_string}")
        self.is_debugging = False
        if self.dap_socket:
            self.dap_socket.deleteLater()
            self.dap_socket = None

    def _send_dap_message(self, message_dict: dict):
        if not self.dap_socket or not self.dap_socket.isOpen():
            error_msg = "Cannot send DAP message: Not connected to DAP server."
            self.dap_error.emit(error_msg)
            print(error_msg)
            return False
        try:
            message_json = json.dumps(message_dict)
            message_bytes = message_json.encode('utf-8')
            header = f"Content-Length: {len(message_bytes)}\r\n\r\n".encode('utf-8')
            bytes_written = self.dap_socket.write(header + message_bytes)
            if bytes_written == -1:
                self.dap_error.emit("Failed to write DAP message to socket.")
                return False
            return True
        except Exception as e:
            error_msg = f"Error preparing or sending DAP message: {e}"
            self.dap_error.emit(error_msg)
            print(error_msg)
            return False

    def _send_dap_request(self, command: str, arguments: dict = None):
        self.seq += 1
        request_payload = {
            "seq": self.seq,
            "type": "request",
            "command": command
        }
        if arguments is not None:
            request_payload["arguments"] = arguments
        if self._send_dap_message(request_payload):
            return self.seq
        return None

    # --- DAP Message Handling ---
    def _handle_dap_message(self, message_payload: dict):
        msg_type = message_payload.get("type")
        if msg_type == "response":
            self._handle_dap_response(message_payload)
        elif msg_type == "event":
            self._handle_dap_event(message_payload)
        else:
            error_msg = f"Received unknown DAP message type: {msg_type}"
            print(f"{error_msg} - Payload: {message_payload}")
            self.dap_error.emit(error_msg)

    def _handle_dap_response(self, response_payload: dict):
        request_command = response_payload.get("command")
        request_seq = response_payload.get("request_seq")
        success = response_payload.get("success", False)
        body = response_payload.get("body")
        message_text = response_payload.get("message")

        if not success:
            error_details_str = message_text if message_text else "No error message provided by DAP server."
            if body and isinstance(body.get('error'), dict) and body['error'].get('format'):
                 error_details_str += f" Details: {body['error']['format']}"
            full_error_msg = f"DAP Error for '{request_command}' (seq {request_seq}): {error_details_str}"
            self.dap_error.emit(full_error_msg)
            print(full_error_msg)
            if request_command in ["launch", "attach", "initialize"]:
                self.is_debugging = False
                self.dap_terminated.emit()
            return

        if request_command == "initialize":
            self.capabilities = body if body else {}
            self.dap_initialized.emit()
            print("DAP 'initialize' successful, capabilities stored.")
        elif request_command in ["launch", "attach"]:
            self.dap_launched.emit()
            print(f"DAP '{request_command}' successful, debug session active.")
        elif request_command == "setBreakpoints":
            print(f"DAP 'setBreakpoints' response: {json.dumps(body, indent=2)}")
            self.dap_event.emit("breakpointsSetResult", body if body else {})
        elif request_command == "threads":
            self.threads_received.emit(body.get("threads", []))
        elif request_command == "stackTrace":
            self.stack_frames_received.emit(body.get("stackFrames", []))
        elif request_command == "scopes":
            self.scopes_received.emit(body.get("scopes", []))
        elif request_command == "variables":
            self.variables_received.emit(body.get("variables", []))
        elif request_command == "continue":
            print("DAP 'continue' acknowledged.")
        elif request_command in ["next", "stepIn", "stepOut", "pause"]:
            print(f"DAP '{request_command}' acknowledged.")
        elif request_command == "disconnect":
            print("DAP 'disconnect' acknowledged. Session ending.")
        elif request_command == "terminate":
            print("DAP 'terminate' (debuggee) acknowledged.")
        elif request_command == "evaluate":
            print(f"DAP 'evaluate' response: {json.dumps(body, indent=2)}")
            self.dap_event.emit("evaluateResult", body if body else {})
        else:
            print(f"Received unhandled successful DAP response for command: {request_command}")

    def _handle_dap_event(self, event_payload: dict):
        event_type = event_payload.get("event")
        body = event_payload.get("body", {})
        if event_type == "initialized":
            print("DAP 'initialized' event: Debug adapter is ready.")
        elif event_type == "output":
            category = body.get("category", "console")
            output_text = body.get("output", "")
            self.dap_output.emit(category, output_text)
        elif event_type == "terminated":
            print("DAP 'terminated' event: Debug session ended by adapter.")
            self.is_debugging = False
            self.dap_terminated.emit()
            if self.dap_socket and self.dap_socket.isOpen():
                self.dap_socket.abort()
            if self.dap_process and self.dap_process.state() != QProcess.ProcessState.NotRunning:
                 self.stop_dap_server()
        elif event_type == "stopped":
            reason = body.get("reason", "unknown")
            thread_id = body.get("threadId", -1)
            source_info = body.get("source", {})
            file_path = source_info.get("path", source_info.get("name", "UnknownFile"))
            line_num = body.get("line", 0)
            print(f"DAP 'stopped' event: Reason '{reason}', Thread {thread_id}, at {file_path}:{line_num}")
            self.breakpoint_hit.emit(file_path, line_num, thread_id, body)
        elif event_type == "continued":
            thread_id = body.get("threadId", -1)
            print(f"DAP 'continued' event for Thread ID {thread_id}")
            self.dap_event.emit(event_type, body)
        elif event_type == "thread":
            print(f"DAP 'thread' event: {json.dumps(body, indent=2)}")
            self.dap_event.emit(event_type, body)
        elif event_type == "process":
             print(f"DAP 'process' event: {json.dumps(body, indent=2)}")
             self.dap_event.emit(event_type, body)
        elif event_type == "module":
             print(f"DAP 'module' event: {json.dumps(body, indent=2)}")
             self.dap_event.emit(event_type, body)
        elif event_type == "breakpoint":
            print(f"DAP 'breakpoint' event (e.g. verified): {json.dumps(body, indent=2)}")
            self.dap_event.emit(event_type, body)
        else:
            print(f"Received unhandled DAP event type: {event_type}")
            self.dap_event.emit(event_type, body)

    # --- Public DAP Command Methods ---
    def dap_initialize(self, adapter_id: str, client_name: str = "AetherEditor", locale: str = "en-US",
                       lines_start_at_1: bool = True, columns_start_at_1: bool = True,
                       supports_variable_type: bool = True, supports_variable_paging: bool = True,
                       supports_run_in_terminal_request: bool = True,
                       path_format: str = "path",
                       additional_args: dict = None) -> int | None:
        if not self.dap_socket or not self.dap_socket.isOpen():
            self.dap_error.emit("Cannot send 'initialize': Not connected to DAP server.")
            print("Cannot send 'initialize': Not connected to DAP server.")
            return None
        arguments = {
            "clientID": client_name,
            "clientName": client_name,
            "adapterID": adapter_id,
            "locale": locale,
            "linesStartAt1": lines_start_at_1,
            "columnsStartAt1": columns_start_at_1,
            "supportsVariableType": supports_variable_type,
            "supportsVariablePaging": supports_variable_paging,
            "supportsRunInTerminalRequest": supports_run_in_terminal_request,
            "pathFormat": path_format,
        }
        if additional_args:
            arguments.update(additional_args)
        return self._send_dap_request("initialize", arguments)

    def dap_launch(self, program_path: str, launch_args: dict = None, no_debug: bool = False) -> int | None:
        arguments = {"program": program_path, "noDebug": no_debug}
        if launch_args:
            arguments.update(launch_args)
        return self._send_dap_request("launch", arguments)

    def dap_attach(self, attach_args: dict) -> int | None:
        return self._send_dap_request("attach", attach_args)

    def dap_set_breakpoints(self, filepath: str, breakpoints: list) -> int | None:
        source_argument = {"path": filepath}
        processed_bps = []
        for bp_info in breakpoints:
            if isinstance(bp_info, dict) and 'line' in bp_info:
                processed_bps.append(bp_info)
            elif isinstance(bp_info, int):
                 processed_bps.append({'line': bp_info})
            else:
                print(f"Warning: Invalid breakpoint format skipped in dap_set_breakpoints: {bp_info}")
        arguments = {
            "source": source_argument,
            "breakpoints": processed_bps,
            "sourceModified": False
        }
        return self._send_dap_request("setBreakpoints", arguments)

    def dap_disconnect(self, terminate_debuggee: bool = True, restart: bool = False, suspend_debuggee: bool = False) -> int | None:
        arguments = { "terminateDebuggee": terminate_debuggee, }
        if restart: arguments["restart"] = True
        if suspend_debuggee: arguments["suspendDebuggee"] = True
        return self._send_dap_request("disconnect", arguments)

    def dap_continue(self, thread_id: int) -> int | None:
        arguments = {"threadId": thread_id}
        return self._send_dap_request("continue", arguments)

    def dap_next(self, thread_id: int) -> int | None:
        arguments = {"threadId": thread_id}
        return self._send_dap_request("next", arguments)

    def dap_step_in(self, thread_id: int) -> int | None:
        arguments = {"threadId": thread_id}
        return self._send_dap_request("stepIn", arguments)

    def dap_step_out(self, thread_id: int) -> int | None:
        arguments = {"threadId": thread_id}
        return self._send_dap_request("stepOut", arguments)

    def dap_pause(self, thread_id: int) -> int | None:
        arguments = {"threadId": thread_id}
        return self._send_dap_request("pause", arguments)

    def dap_terminate(self, restart: bool = False) -> int | None:
        arguments = {}
        if restart: arguments["restart"] = restart
        return self._send_dap_request("terminate", arguments if arguments else None)

    def dap_restart_frame(self, frame_id: int) -> int | None:
        arguments = {"frameId": frame_id}
        return self._send_dap_request("restartFrame", arguments)

    def dap_threads(self) -> int | None:
        return self._send_dap_request("threads")

    def dap_stack_trace(self, thread_id: int, start_frame: int = 0, levels: int = 20,
                        format_args: dict = None) -> int | None:
        arguments = {"threadId": thread_id, "startFrame": start_frame, "levels": levels}
        if format_args: arguments["format"] = format_args
        return self._send_dap_request("stackTrace", arguments)

    def dap_scopes(self, frame_id: int) -> int | None:
        arguments = {"frameId": frame_id}
        return self._send_dap_request("scopes", arguments)

    def dap_variables(self, variables_reference: int, filter_type: str = None,
                        start: int = None, count: int = None, format_args: dict = None) -> int | None:
        arguments = {"variablesReference": variables_reference}
        if filter_type: arguments["filter"] = filter_type
        if start is not None: arguments["start"] = start
        if count is not None: arguments["count"] = count
        if format_args: arguments["format"] = format_args
        return self._send_dap_request("variables", arguments)

    def dap_evaluate(self, expression: str, frame_id: int = None, context: str = None,
                       format_args: dict = None) -> int | None:
        arguments = {"expression": expression}
        if frame_id is not None: arguments["frameId"] = frame_id
        if context: arguments["context"] = context
        if format_args: arguments["format"] = format_args
        return self._send_dap_request("evaluate", arguments)

if __name__ == '__main__':
    manager = DebugManager()
    print("DebugManager instance created (Public DAP command methods implemented).")
