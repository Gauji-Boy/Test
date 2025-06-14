import json
import os # Though not used in this snippet, often useful in network managers
import sys # For sys.platform
from PySide6.QtCore import QObject, Signal, Slot, QByteArray, QDataStream, QIODevice
from PySide6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress, QAbstractSocket

class NetworkManagerRefactored(QObject):
    # Signals for UI updates / events
    connected_to_peer = Signal()
    disconnected_from_peer = Signal()
    error_occurred = Signal(str) # General network errors
    status_message = Signal(str) # For user-facing status updates

    # Signals for data exchange (collaborative editing)
    # For text content, cursor position, selection changes, etc.
    # These need to be well-defined based on the collaboration protocol.
    # Example: data_received(type: str, payload: dict)
    # 'type' could be 'text_update', 'cursor_update', 'selection_update', 'file_open', 'file_close'
    # 'payload' would contain relevant data like file_path, content, position, etc.
    data_received_from_peer = Signal(str, object) # type, payload (payload can be dict/list)

    # Signals for control management (collaborative editing)
    control_request_received = Signal() # Host receives this from client
    control_granted_to_peer = Signal()  # Host sends this, client receives
    control_revoked_from_peer = Signal() # Host sends this, client receives
    control_request_declined = Signal() # Host sends this, client receives
    # Signals for this instance gaining/losing control
    editing_control_acquired = Signal()
    editing_control_lost = Signal()


    def __init__(self, parent=None):
        super().__init__(parent)
        self.tcp_server = None
        self.client_socket = None # For client connecting to a host
        self.host_connections = [] # For host managing multiple clients (if supported, for now single client)
        
        self.is_hosting = False
        self.is_connected_as_client = False
        self.has_editing_control = False # Relevant for collaborative sessions
        
        # Buffer for receiving data (similar to DAP manager)
        self._recv_buffer = QByteArray()
        self._expected_msg_size = -1 # For message framing (e.g. if messages are prefixed with size)

    # --- Server (Hosting) Methods --- 
    @Slot(int) # port
    def start_hosting_session(self, port: int) -> bool:
        if self.is_hosting or self.is_connected_as_client:
            self.error_occurred.emit("A network session is already active.")
            return False

        self._reset_network_state() # Ensure clean state before starting

        self.tcp_server = QTcpServer(self)
        self.tcp_server.newConnection.connect(self._on_new_connection)
        
        if not self.tcp_server.listen(QHostAddress.Any, port):
            error_msg = f"Failed to start hosting on port {port}: {self.tcp_server.errorString()}"
            self.error_occurred.emit(error_msg)
            self.status_message.emit(f"Error: Could not listen on port {port}.")
            self.tcp_server = None
            return False
        
        self.is_hosting = True
        # For collaborative editing, host usually starts with control.
        # This might be adjusted based on desired initial state or a handshake.
        self.has_editing_control = True 
        self.editing_control_acquired.emit() # Notify UI that this instance has control

        actual_port = self.tcp_server.serverPort()
        msg = f"Hosting session started on port {actual_port}. Waiting for connection..."
        self.status_message.emit(msg)
        self.network_info_received.emit("network_info", msg + "\n") # Using output_received for logs
        return True

    @Slot()
    def _on_new_connection(self):
        if not self.tcp_server:
            return

        # For now, assume only one client connection is managed by the host.
        # If multiple clients were supported, this logic would need to manage a list of client_sockets.
        if self.host_connections: # If we already have a connection
            # Optionally, reject new connection or replace old one.
            # For simplicity, let's reject new ones if one is active.
            next_pending_socket = self.tcp_server.nextPendingConnection()
            if next_pending_socket:
                self.network_info_received.emit("network_warn", "New connection attempt while already connected. Rejecting.\n")
                next_pending_socket.close()
                next_pending_socket.deleteLater()
            return

        client_socket = self.tcp_server.nextPendingConnection()
        if client_socket:
            self.network_info_received.emit("network_info", f"New client connected from: {client_socket.peerAddress().toString()}:{client_socket.peerPort()}\n")
            self._handle_new_client_connection(client_socket)
        else:
            self.network_info_received.emit("network_warn", "Failed to accept new connection (socket is null).\n")

    # --- Client Methods --- 
    @Slot(str, int) # host_address, port
    def connect_to_host_session(self, host_address: str, port: int) -> bool:
        if self.is_hosting or self.is_connected_as_client:
            self.error_occurred.emit("A network session is already active.")
            return False

        self._reset_network_state() # Ensure clean state

        self.client_socket = QTcpSocket(self)
        self.client_socket.connected.connect(self._on_client_socket_connected)
        self.client_socket.disconnected.connect(self._on_client_socket_disconnected)
        self.client_socket.errorOccurred.connect(self._on_client_socket_error) # Connect this correctly
        self.client_socket.readyRead.connect(self._on_socket_ready_read)

        msg = f"Attempting to connect to host {host_address}:{port}..."
        self.status_message.emit(msg)
        self.output_received.emit("network_info", msg + "\n") # Using output_received for logs
        self.client_socket.connectToHost(host_address, port)
        
        return True # Indicates connection attempt has started

    @Slot()
    def _on_client_socket_connected(self):
        self.is_connected_as_client = True
        self.has_editing_control = False # Client usually starts without control
        self.editing_control_lost.emit() # Notify UI that this client instance initially doesn't have control
        
        msg = f"Successfully connected to host: {self.client_socket.peerName()}:{self.client_socket.peerPort()}"
        self.status_message.emit(msg)
        self.network_info_received.emit("network_info", msg + "\n")
        self.connected_to_peer.emit()

    @Slot()
    def _on_client_socket_disconnected(self):
        # This is for when this instance is a client and gets disconnected from the host.
        if not self.is_connected_as_client: # Prevent multiple calls or calls when not relevant
            return 
            
        peer_name = self.client_socket.peerName() if self.client_socket else "unknown_host"
        error_msg = f"Disconnected from host {peer_name}."
        
        self.network_info_received.emit("network_info", error_msg + "\n")
        self.status_message.emit("Disconnected from host.")
        self.error_occurred.emit(error_msg) # Notify UI of disconnection
        
        self._reset_network_state() # Full cleanup
        self.disconnected_from_peer.emit()

    @Slot(QAbstractSocket.SocketError) 
    def _on_client_socket_error(self, socket_error: QAbstractSocket.SocketError):
        # This is for when this instance is a client and its socket has an error.
        if not self.client_socket: return

        error_msg = f"Socket error with host: {self.client_socket.errorString()} (Code: {socket_error})"
        self.network_info_received.emit("network_error", error_msg + "\n")
        self.error_occurred.emit(error_msg)
        # Disconnection will likely follow, or _reset_network_state might be called by the handler of this error.
        # For now, let _on_client_socket_disconnected handle the full cleanup if error leads to disconnect.

    # --- Common Connection Handling (for both host client connections and client's connection to host) ---
    def _handle_new_client_connection(self, client_socket: QTcpSocket):
        # This method is called by the host when a new client connects.
        # For now, assuming a single client connection for the host.
        if self.host_connections: # If somehow called again while one exists
            self.network_info_received.emit("network_warn", "_handle_new_client_connection called with existing connections. Closing new one.\n")
            client_socket.close()
            client_socket.deleteLater()
            return

        self.host_connections.append(client_socket) # Store the socket
        # Connect signals for this specific client socket
        client_socket.readyRead.connect(self._on_socket_ready_read)
        client_socket.disconnected.connect(self._on_host_client_socket_disconnected) # Need this new slot
        # client_socket.errorOccurred.connect(self._on_host_client_socket_error) # Need this new slot

        self.connected_to_peer.emit() # Signal that a peer is now connected
        self.status_message.emit("Client connected. Session active.")
        
        # Initial state for collaboration: host has control.
        # If client needs to know this, send an initial state message.
        # Example: self.send_data_to_peer("control_status", {"has_control": False}) # Tell client it doesn't have control

    @Slot()
    def _on_socket_ready_read(self): # Connected to readyRead signal of active socket(s)
        socket = self.sender() # Get the QTcpSocket that emitted the signal
        if not socket or not isinstance(socket, QTcpSocket):
            self.network_info_received.emit("network_warn", "_on_socket_ready_read from unexpected sender.\n")
            return

        if socket == self.client_socket or (self.host_connections and socket == self.host_connections[0]):
            try:
                data = socket.readAll()
                if data:
                    self._recv_buffer.append(data)
                    self._process_received_data(socket) 
                # else: socket might be closing or no more data for now
            except Exception as e:
                self.error_occurred.emit(f"Error reading from socket: {e}")
                self._cleanup_connection(socket, was_initiated_by_us=False)
        else:
            self.network_info_received.emit("network_warn", "Data received on an unrecognized socket.\n")

    def _process_received_data(self, source_socket: QTcpSocket):
        # Message Framing: 4-byte Big Endian unsigned integer for size, then UTF-8 JSON message.
        while True:
            if self._expected_msg_size == -1: 
                if self._recv_buffer.size() >= 4:
                    try:
                        stream = QDataStream(self._recv_buffer, QIODevice.OpenModeFlag.ReadOnly)
                        self._expected_msg_size = stream.readUInt32() 
                        self._recv_buffer = self._recv_buffer.mid(4) 
                    except Exception as e:
                        self.error_occurred.emit(f"Error reading message size: {e}. Buffer content: {self._recv_buffer.toHex().data().decode()}")
                        self._recv_buffer.clear() 
                        self._expected_msg_size = -1
                        self._cleanup_connection(source_socket, was_initiated_by_us=False) 
                        return
                else:
                    break 
            
            if self._expected_msg_size > 0 and self._recv_buffer.size() >= self._expected_msg_size:
                message_data_qba = self._recv_buffer.mid(0, self._expected_msg_size)
                self._recv_buffer = self._recv_buffer.mid(self._expected_msg_size)
                self._expected_msg_size = -1 # Reset for next message

                try:
                    message_str = message_data_qba.data().decode('utf-8')
                    parsed_json = json.loads(message_str)
                    msg_type = parsed_json.get("type")
                    payload = parsed_json.get("payload")
                    if msg_type:
                        self._handle_parsed_message(msg_type, payload, source_socket)
                    else:
                        self.network_info_received.emit("network_warn", f"Received message with no type: {parsed_json}\n")
                except json.JSONDecodeError as jde:
                    self.error_occurred.emit(f"JSON decode error: {jde}. Data: {message_data_qba.data().decode(errors='replace')}")
                except UnicodeDecodeError as ude:
                    self.error_occurred.emit(f"UTF-8 decode error: {ude}. Data (hex): {message_data_qba.toHex().data().decode()}")
                except Exception as e:
                    self.error_occurred.emit(f"Error processing received message: {e}")
            else:
                break 

    def _handle_parsed_message(self, message_type: str, payload: dict, source_socket: QTcpSocket = None):
        # self.network_info_received.emit("network_debug", f"Handling message type '{message_type}' with payload: {payload}\n")

        if message_type == "error_notification": 
            self.error_occurred.emit(f"Error from peer: {payload.get('message', 'Unknown error')}")
            return
        
        self.data_received_from_peer.emit(message_type, payload)

        if message_type == "request_control":
            if self.is_hosting: 
                self.control_request_received.emit()
        elif message_type == "grant_control":
            if self.is_connected_as_client: 
                self.has_editing_control = True
                self.editing_control_acquired.emit()
                self.status_message.emit("Editing control granted.")
        elif message_type == "decline_control":
            if self.is_connected_as_client:
                self.control_request_declined.emit()
                self.status_message.emit("Host declined control request.")
        elif message_type == "revoke_control":
            if self.is_connected_as_client:
                self.has_editing_control = False
                self.editing_control_lost.emit()
                self.status_message.emit("Editing control revoked by host.")

    # --- Data Sending --- 
    @Slot(str, object) # type, payload (dict/list)
    def send_data_to_peer(self, message_type: str, payload: object):
        if not self.is_connected():
            self.error_occurred.emit("Cannot send data: Not connected to any peer.")
            return

        message = {
            "type": message_type,
            "payload": payload
        }
        try:
            json_message = json.dumps(message)
            encoded_message = json_message.encode('utf-8') 

            data_to_send = QByteArray()
            stream = QDataStream(data_to_send, QIODevice.OpenModeFlag.WriteOnly)
            stream.writeUInt32(len(encoded_message)) 
            data_to_send.append(encoded_message)
            
            if self.is_hosting:
                if self.host_connections:
                    self._send_raw_data(data_to_send, self.host_connections[0])
                else:
                    self.network_info_received.emit("network_warn", "Host: No clients to send data to.\n")
            elif self.is_connected_as_client and self.client_socket:
                self._send_raw_data(data_to_send, self.client_socket)
            
        except json.JSONEncodeError as jde:
            self.error_occurred.emit(f"JSON encode error while sending: {jde}")
        except Exception as e:
            self.error_occurred.emit(f"Error preparing data to send: {e}")

    def _send_raw_data(self, data_qbytearray: QByteArray, target_socket: QTcpSocket):
        if target_socket and target_socket.isOpen() and target_socket.state() == QTcpSocket.SocketState.ConnectedState:
            written = target_socket.write(data_qbytearray)
            if written == -1:
                self.error_occurred.emit(f"Failed to write data to socket: {target_socket.errorString()}")
                self._cleanup_connection(target_socket, was_initiated_by_us=False) 
            elif written < data_qbytearray.size():
                self.error_occurred.emit("Failed to write complete data to socket (short write).")
                self._cleanup_connection(target_socket, was_initiated_by_us=False)
        else:
            self.error_occurred.emit("Cannot send raw data: Target socket is not valid or not connected.")

    # --- Session Control & Cleanup --- 
    @Slot()
    def stop_current_session(self):
        self.network_info_received.emit("network_info", "Stopping current network session...\n")
        if self.is_hosting:
            # For host, close server and all client connections
            if self.tcp_server:
                self.tcp_server.close()
                # self.tcp_server.deleteLater() # Defer this to _reset_network_state
            # _reset_network_state will handle host_connections cleanup
        elif self.is_connected_as_client:
            # For client, just close its own socket
            if self.client_socket:
                self.client_socket.abort() # Force close
                # self.client_socket.deleteLater() # Defer this to _reset_network_state
        
        # Full cleanup of states and objects
        self._reset_network_state() 
        self.status_message.emit("Network session stopped.")
        self.disconnected_from_peer.emit() # General signal indicating no peer connection
        if self.has_editing_control: # If this instance had control, it's now lost
            self.has_editing_control = False
            self.editing_control_lost.emit()

    def _cleanup_connection(self, socket_to_cleanup: QTcpSocket, was_initiated_by_us: bool = True):
        # This method is primarily for host-side cleanup of a specific client socket
        # or for client-side cleanup of its own socket if called directly (though _reset_network_state is more common for client).
        if not socket_to_cleanup: return

        peer_info_str = f"{socket_to_cleanup.peerAddress().toString()}:{socket_to_cleanup.peerPort()}"
        self.network_info_received.emit("network_info", f"Cleaning up connection with {peer_info_str}. Initiated by us: {was_initiated_by_us}\n")

        # Disconnect all signals from this specific socket
        try: socket_to_cleanup.readyRead.disconnect(self._on_socket_ready_read) 
        except RuntimeError: pass
        
        if socket_to_cleanup in self.host_connections:
            try: socket_to_cleanup.disconnected.disconnect(self._on_host_client_socket_disconnected)
            except RuntimeError: pass
            # try: socket_to_cleanup.errorOccurred.disconnect(self._on_host_client_socket_error)
            # except RuntimeError: pass # Assuming this was connected
            self.host_connections.remove(socket_to_cleanup)
        elif socket_to_cleanup == self.client_socket:
            try: socket_to_cleanup.connected.disconnect(self._on_client_socket_connected)
            except RuntimeError: pass
            try: socket_to_cleanup.disconnected.disconnect(self._on_client_socket_disconnected)
            except RuntimeError: pass
            try: socket_to_cleanup.errorOccurred.disconnect(self._on_client_socket_error)
            except RuntimeError: pass
            self.client_socket = None # Clear our reference if it's the main client socket
            self.is_connected_as_client = False

        if socket_to_cleanup.isOpen():
            socket_to_cleanup.abort() # Force close
        socket_to_cleanup.deleteLater() # Schedule for deletion

        # If we were host and no clients left, or if we were client and disconnected
        if (self.is_hosting and not self.host_connections) or \
           (not self.is_hosting and not self.is_connected_as_client and socket_to_cleanup == self.client_socket):
            # self.disconnected_from_peer.emit() # This might be emitted by the calling context already
            # self.status_message.emit("Peer disconnected.")
            if self.has_editing_control and not self.is_hosting: # Client lost control due to disconnect
                self.has_editing_control = False
                self.editing_control_lost.emit()
            # If host, host usually retains control. If client, loses it.

    def _reset_network_state(self):
        # print("NetworkManager: Resetting network state.") # Debug log
        if self.client_socket:
            # Disconnect signals before closing and deleting
            try: self.client_socket.connected.disconnect(self._on_client_socket_connected) 
            except RuntimeError: pass
            try: self.client_socket.disconnected.disconnect(self._on_client_socket_disconnected) 
            except RuntimeError: pass
            try: self.client_socket.errorOccurred.disconnect(self._on_client_socket_error) 
            except RuntimeError: pass
            try: self.client_socket.readyRead.disconnect(self._on_socket_ready_read) 
            except RuntimeError: pass
            
            if self.client_socket.isOpen():
                self.client_socket.abort() # Force close immediately
            self.client_socket.deleteLater()
            self.client_socket = None

        if self.tcp_server:
            self.tcp_server.close() # Stop listening
            # Disconnect newConnection signal
            try: self.tcp_server.newConnection.disconnect(self._on_new_connection)
            except RuntimeError: pass
            self.tcp_server.deleteLater()
            self.tcp_server = None
        
        # Close and delete any client sockets connected to the host
        for sock in self.host_connections:
            try: sock.readyRead.disconnect(self._on_socket_ready_read) 
            except RuntimeError: pass
            try: sock.disconnected.disconnect(self._on_host_client_socket_disconnected) 
            except RuntimeError: pass
            # try: sock.errorOccurred.disconnect(self._on_host_client_socket_error) 
            # except RuntimeError: pass
            if sock.isOpen():
                sock.abort()
            sock.deleteLater()
        self.host_connections.clear()

        self._recv_buffer.clear()
        self._expected_msg_size = -1
        self.is_hosting = False
        self.is_connected_as_client = False
        self.has_editing_control = False # Reset control state
        # Do not emit editing_control_lost here unless it was explicitly held before reset.
        # print("NetworkManager: Network state has been reset.") # Debug log

    # --- Collaborative Editing Control Management (Example Methods) ---
    @Slot()
    def request_editing_control(self): # Client calls this
        if self.is_connected_as_client and not self.has_editing_control:
            self.send_data_to_peer("request_control", {})
            self.status_message.emit("Requesting editing control from host...")
        elif not self.is_connected_as_client:
            self.error_occurred.emit("Cannot request control: Not connected as client.")
        elif self.has_editing_control:
            self.status_message.emit("Already have editing control.")

    @Slot(bool) # grant (True to grant, False to decline)
    def respond_to_control_request(self, grant: bool): # Host calls this
        if not self.is_hosting or not self.host_connections:
            self.error_occurred.emit("Cannot respond to control request: Not hosting or no client.")
            return

        if grant:
            self.send_data_to_peer("grant_control", {})
            self.has_editing_control = False # Host gives up control
            self.editing_control_lost.emit()
            self.control_granted_to_peer.emit() # Internal signal for host UI if needed
            self.status_message.emit("Editing control granted to client.")
        else:
            self.send_data_to_peer("decline_control", {})
            self.control_request_declined.emit() # Internal signal for host UI
            self.status_message.emit("Editing control request declined.")

    @Slot()
    def reclaim_editing_control(self): # Host calls this if it previously granted control
        if not self.is_hosting or not self.host_connections:
            self.error_occurred.emit("Cannot reclaim control: Not hosting or no client.")
            return
        
        if not self.has_editing_control: # If host doesn't have it, it means client might
            self.send_data_to_peer("revoke_control", {})
            self.has_editing_control = True # Host reclaims control
            self.editing_control_acquired.emit()
            self.control_revoked_from_peer.emit() # Internal signal for host UI
            self.status_message.emit("Editing control reclaimed by host.")
        else:
            self.status_message.emit("Host already has editing control.")

    # --- Getters/Setters for State (if needed by MainWindow) --- 
    def is_connected(self) -> bool:
        # A more precise check for active, usable connection
        if self.is_hosting:
            return bool(self.host_connections and self.host_connections[0].state() == QTcpSocket.SocketState.ConnectedState)
        elif self.is_connected_as_client:
            return bool(self.client_socket and self.client_socket.state() == QTcpSocket.SocketState.ConnectedState)
        return False

    def current_peer_info(self) -> str | None:
        socket_to_check = None
        if self.is_hosting and self.host_connections:
            socket_to_check = self.host_connections[0]
        elif self.is_connected_as_client and self.client_socket:
            socket_to_check = self.client_socket
        
        if socket_to_check and socket_to_check.state() == QTcpSocket.SocketState.ConnectedState:
            return f"{socket_to_check.peerAddress().toString()}:{socket_to_check.peerPort()}"
        return None

    def __del__(self):
        # print("NetworkManagerRefactored: __del__ called.") # Optional debug
        # Avoid emitting signals or relying on Qt objects in __del__ as they might already be destroyed.
        # Explicit cleanup should be handled by the parent object (e.g., MainWindow)
        # self.stop_current_session()

        # --- Slots for client socket signals (when this instance is the host) ---
        @Slot()
        def _on_host_client_socket_disconnected(self):
            # This slot would be connected to the disconnected() signal of a client_socket
            # stored in self.host_connections.
            # Find which socket disconnected if managing multiple.
            sender_socket = self.sender() # QTcpSocket that emitted the signal
            if sender_socket in self.host_connections:
                peer_info = f"{sender_socket.peerAddress().toString()}:{sender_socket.peerPort()}"
                self.network_info_received.emit("network_info", f"Client {peer_info} disconnected.\n")
                self._cleanup_connection(sender_socket, was_initiated_by_us=False)
            else:
                self.network_info_received.emit("network_warn", "A client socket disconnected but was not in the managed list.\n")
            
            # If no clients left, can emit disconnected_from_peer or just update status
            if not self.host_connections:
                self.disconnected_from_peer.emit()
                self.status_message.emit("Client disconnected. Waiting for new connection...")
                # Host might retain control or reset based on policy.
                # self.has_editing_control = True # Host typically regains/retains control
                # self.editing_control_acquired.emit()

        @Slot(QAbstractSocket.SocketError)
        def _on_host_client_socket_error(self, socket_error: QAbstractSocket.SocketError):
            # This slot would handle errors from a specific client socket on the host side.
            sender_socket = self.sender()
            if sender_socket in self.host_connections:
                error_msg = f"Error on client socket ({sender_socket.peerAddress().toString()}): {sender_socket.errorString()} (Code: {socket_error})"
                self.error_occurred.emit(error_msg)
                self.network_info_received.emit("network_error", error_msg + "\n")
                # self._cleanup_connection(sender_socket, was_initiated_by_us=False) # Disconnect might follow
            else:
                self.network_info_received.emit("network_warn", "Error from an unmanaged client socket.\n")
