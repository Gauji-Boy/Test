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
        self.output_received.emit("network_info", msg + "\n") # Using output_received for logs
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
                self.output_received.emit("network_warn", "New connection attempt while already connected. Rejecting.\n")
                next_pending_socket.close()
                next_pending_socket.deleteLater()
            return

        client_socket = self.tcp_server.nextPendingConnection()
        if client_socket:
            self.output_received.emit("network_info", f"New client connected from: {client_socket.peerAddress().toString()}:{client_socket.peerPort()}\n")
            self._handle_new_client_connection(client_socket)
        else:
            self.output_received.emit("network_warn", "Failed to accept new connection (socket is null).\n")

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
        self.output_received.emit("network_info", msg + "\n")
        self.connected_to_peer.emit()

    @Slot()
    def _on_client_socket_disconnected(self):
        # This is for when this instance is a client and gets disconnected from the host.
        if not self.is_connected_as_client: # Prevent multiple calls or calls when not relevant
            return

        peer_name = self.client_socket.peerName() if self.client_socket else "unknown_host"
        error_msg = f"Disconnected from host {peer_name}."

        self.output_received.emit("network_info", error_msg + "\n")
        self.status_message.emit("Disconnected from host.")
        self.error_occurred.emit(error_msg) # Notify UI of disconnection

        self._reset_network_state() # Full cleanup
        self.disconnected_from_peer.emit()

    @Slot(QAbstractSocket.SocketError)
    def _on_client_socket_error(self, socket_error: QAbstractSocket.SocketError):
        # This is for when this instance is a client and its socket has an error.
        if not self.client_socket: return

        error_msg = f"Socket error with host: {self.client_socket.errorString()} (Code: {socket_error})"
        self.output_received.emit("network_error", error_msg + "\n")
        self.error_occurred.emit(error_msg)
        # Disconnection will likely follow, or _reset_network_state might be called by the handler of this error.
        # For now, let _on_client_socket_disconnected handle the full cleanup if error leads to disconnect.

    # --- Common Connection Handling (for both host client connections and client's connection to host) ---
    def _handle_new_client_connection(self, client_socket: QTcpSocket):
        # This method is called by the host when a new client connects.
        # For now, assuming a single client connection for the host.
        if self.host_connections: # If somehow called again while one exists
            self.output_received.emit("network_warn", "_handle_new_client_connection called with existing connections. Closing new one.\n")
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
        pass

    def _process_received_data(self, socket_wrapper_or_direct_socket):
        pass # Parses framed messages from _recv_buffer

    def _handle_parsed_message(self, message_type: str, payload: dict, source_socket_info=None):
        pass # Acts on a fully received and parsed message

    # --- Data Sending ---
    @Slot(str, object) # type, payload (dict/list)
    def send_data_to_peer(self, message_type: str, payload: object):
        pass # Serializes (e.g. to JSON) and sends data to connected peer(s)

    def _send_raw_data(self, data: QByteArray, target_socket: QTcpSocket = None):
        pass # Helper to send framed QByteArray to a specific socket or all

    # --- Session Control & Cleanup ---
    @Slot()
    def stop_current_session(self):
        pass # Stops hosting or disconnects from host

    def _cleanup_connection(self, socket_wrapper_or_socket, was_initiated_by_us=True):
        pass # Closes a specific socket and cleans up related resources

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
        pass

    @Slot(bool) # grant (True to grant, False to decline)
    def respond_to_control_request(self, grant: bool): # Host calls this
        pass

    @Slot()
    def reclaim_editing_control(self): # Host calls this if it previously granted control
        pass

    # --- Getters/Setters for State (if needed by MainWindow) ---
    def is_connected(self) -> bool:
        return self.is_hosting or self.is_connected_as_client

    def current_peer_info(self) -> str | None:
        pass # Returns info about connected peer if any

    def __del__(self):
        self.stop_current_session()

    # --- Slots for client socket signals (when this instance is the host) ---
    @Slot()
    def _on_host_client_socket_disconnected(self):
        # This slot would be connected to the disconnected() signal of a client_socket
        # stored in self.host_connections.
        # Find which socket disconnected if managing multiple.
        sender_socket = self.sender() # QTcpSocket that emitted the signal
        if sender_socket in self.host_connections:
            peer_info = f"{sender_socket.peerAddress().toString()}:{sender_socket.peerPort()}"
            self.output_received.emit("network_info", f"Client {peer_info} disconnected.\n")
            self._cleanup_connection(sender_socket, was_initiated_by_us=False)
        else:
            self.output_received.emit("network_warn", "A client socket disconnected but was not in the managed list.\n")

        # If no clients left, can emit disconnected_from_peer or just update status
        if not self.host_connections:
            self.disconnected_from_peer.emit()
            self.status_message.emit("Client disconnected. Waiting for new connection...")
            # Host might retain control or reset based on policy.
            # self.has_editing_control = True # Host typically regains/retains control
            # self.editing_control_acquired.emit()

    # @Slot("QTcpSocket::SocketError") # Or the actual enum QAbstractSocket.SocketError
    def _on_host_client_socket_error(self, socket_error):
        # This slot would handle errors from a specific client socket on the host side.
        sender_socket = self.sender()
        if sender_socket in self.host_connections:
            error_msg = f"Error on client socket ({sender_socket.peerAddress().toString()}): {sender_socket.errorString()} (Code: {socket_error})"
            self.error_occurred.emit(error_msg)
            self.output_received.emit("network_error", error_msg + "\n")
            # self._cleanup_connection(sender_socket, was_initiated_by_us=False) # Disconnect might follow
        else:
            self.output_received.emit("network_warn", "Error from an unmanaged client socket.\n")
