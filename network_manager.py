from PySide6.QtCore import QObject, Signal, Slot, QByteArray
from PySide6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress # Reverted imports
import json
import logging
from enum import Enum
from typing import Any, cast # Keep cast for sender() if needed, Any for content

logger = logging.getLogger(__name__)

# SERVER_CERT_PATH and SERVER_KEY_PATH removed

class NetworkMessageType(Enum):
    TEXT_UPDATE = "TEXT_UPDATE"
    REQ_CONTROL = "REQ_CONTROL"
    GRANT_CONTROL = "GRANT_CONTROL"
    DECLINE_CONTROL = "DECLINE_CONTROL"
    REVOKE_CONTROL = "REVOKE_CONTROL"

class NetworkManager(QObject):
    data_received: Signal = Signal(str)
    status_changed: Signal = Signal(str)
    peer_connected: Signal = Signal()
    peer_disconnected: Signal = Signal()
    control_request_received: Signal = Signal()
    control_granted: Signal = Signal()
    control_declined: Signal = Signal()
    control_revoked: Signal = Signal()

    tcp_server: QTcpServer
    tcp_socket: QTcpSocket # Reverted to QTcpSocket
    peer_socket: QTcpSocket | None # Reverted to QTcpSocket
    buffer: dict[QTcpSocket, str] # Reverted key type

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.tcp_server = QTcpServer(self)
        self.tcp_socket = QTcpSocket(self) # Reverted to QTcpSocket
        self.peer_socket = None
        self.buffer = {}

        self.tcp_server.newConnection.connect(self._on_new_connection)
        self.tcp_socket.connected.connect(self._on_connected)
        self.tcp_socket.disconnected.connect(self._on_disconnected)
        self.tcp_socket.readyRead.connect(self._read_data)
        # Removed sslErrors and encrypted signal connections

    # Removed _load_server_certificate, _load_private_key, _on_ssl_errors, _on_encrypted_successfully

    def start_hosting(self, port: int) -> bool:
        if self.tcp_server.isListening():
            self.status_changed.emit("Server already listening.")
            return False
        
        if self.tcp_server.listen(QHostAddress.Any, port):
            self.status_changed.emit(f"Hosting on port {port}...")
            return True
        else:
            error_msg: str = f"Failed to start hosting: {self.tcp_server.errorString()}"
            logger.error(error_msg)
            self.status_changed.emit(error_msg)
            return False

    def connect_to_host(self, ip: str, port: int) -> None:
        if self.tcp_socket.state() == QTcpSocket.ConnectedState: # QTcpSocket.ConnectedState is fine
            self.status_changed.emit("Already connected to a host.")
            return
        
        self.status_changed.emit(f"Connecting to {ip}:{port}...")
        self.tcp_socket.connectToHost(ip, port) # Reverted to connectToHost

    def stop_session(self) -> None:
        if self.tcp_server.isListening():
            self.tcp_server.close()
            if self.peer_socket:
                self.peer_socket.disconnectFromHost()
                self.peer_socket.waitForDisconnected(1000)
                self.peer_socket = None
            self.status_changed.emit("Hosting session stopped.")
        elif self.tcp_socket.state() == QTcpSocket.ConnectedState:
            self.tcp_socket.disconnectFromHost()
            self.tcp_socket.waitForDisconnected(1000)
            self.status_changed.emit("Connected session stopped.")
        else:
            self.status_changed.emit("No active session to stop.")

    @Slot()
    def _on_new_connection(self) -> None:
        if self.peer_socket:
            raw_socket_reject: QTcpSocket | None = self.tcp_server.nextPendingConnection()
            if raw_socket_reject:
                raw_socket_reject.disconnectFromHost()
                raw_socket_reject.waitForDisconnected(1000)
            self.status_changed.emit("Rejected new connection: already have a peer.")
            return

        # Simplified: directly assign to self.peer_socket
        self.peer_socket = self.tcp_server.nextPendingConnection()
        if self.peer_socket:
            self.peer_socket.readyRead.connect(self._read_data)
            self.peer_socket.disconnected.connect(self._on_peer_disconnected)
            self.status_changed.emit(f"Peer connected from {self.peer_socket.peerAddress().toString()}:{self.peer_socket.peerPort()}")
            self.peer_connected.emit()
            self.buffer[self.peer_socket] = ""
        else:
            logger.error("nextPendingConnection returned None in _on_new_connection.")


    @Slot()
    def _on_connected(self) -> None:
        self.status_changed.emit(f"Connected to host {self.tcp_socket.peerAddress().toString()}:{self.tcp_socket.peerPort()}")
        # Removed startClientEncryption and related logging
        self.peer_connected.emit()
        self.buffer[self.tcp_socket] = ""

    @Slot()
    def _on_disconnected(self) -> None:
        self.status_changed.emit("Disconnected from host.")
        self.peer_disconnected.emit()
        if self.tcp_socket in self.buffer:
            del self.buffer[self.tcp_socket]

    @Slot()
    def _on_peer_disconnected(self) -> None:
        if self.peer_socket:
            if self.peer_socket in self.buffer:
                del self.buffer[self.peer_socket]
            self.peer_socket.deleteLater()
            self.peer_socket = None
        self.status_changed.emit("Peer disconnected.")
        self.peer_disconnected.emit()

    @Slot()
    def _read_data(self) -> None:
        sender_obj: QObject | None = self.sender()
        # Check for QTcpSocket as it's reverted
        if not isinstance(sender_obj, QTcpSocket):
            logger.warning(f"_read_data called by non-QTcpSocket sender: {type(sender_obj)}")
            return

        sender_socket: QTcpSocket = cast(QTcpSocket, sender_obj)

        raw_data_qba: QByteArray = sender_socket.readAll()
        raw_data_bytes: bytes = raw_data_qba.data()

        decoded_data: str = raw_data_bytes.decode('utf-8', errors='ignore')
        logger.debug(f"readyRead triggered. Received raw data: {decoded_data}")

        self.buffer[sender_socket] += decoded_data

        while '\n' in self.buffer[sender_socket]:
            message_str: str
            message_str, self.buffer[sender_socket] = self.buffer[sender_socket].split('\n', 1)
            if not message_str.strip():
                continue
            try:
                message: dict[str, Any] = json.loads(message_str)
                logger.debug(f"Parsed message in NetworkManager: {message}")
                msg_type: str | None = message.get('type')

                if msg_type == NetworkMessageType.TEXT_UPDATE.value:
                    content: str = message.get('content', '')
                    logger.debug(f"Emitting data_received with content: {content[:50]}...")
                    self.data_received.emit(content)
                elif msg_type == NetworkMessageType.REQ_CONTROL.value:
                    self.control_request_received.emit()
                elif msg_type == NetworkMessageType.GRANT_CONTROL.value:
                    self.control_granted.emit()
                elif msg_type == NetworkMessageType.DECLINE_CONTROL.value:
                    self.control_declined.emit()
                elif msg_type == NetworkMessageType.REVOKE_CONTROL.value:
                    self.control_revoked.emit()
                else:
                    logger.warning(f"Unknown message type received: {msg_type}")
            except json.JSONDecodeError:
                logger.error(f"Received non-JSON data or incomplete JSON in buffer: '{message_str}'", exc_info=True)
            except Exception:
                logger.exception("Error processing received data from buffer")

    def send_data(self, message_type: NetworkMessageType, content: Any = None) -> None:
        logger.debug(f"send_data - Entry, Type: {message_type.value}")
        message: dict[str, Any] = {'type': message_type.value}
        if content is not None:
            message['content'] = content
        
        json_message: str = json.dumps(message) + '\n'
        data_qba: QByteArray = QByteArray(json_message.encode('utf-8'))
        logger.debug(f"Formatting message: {json_message.strip()}")
 
        target_socket: QTcpSocket | None = None # Reverted to QTcpSocket
        # QTcpSocket.ConnectedState is appropriate here
        if self.tcp_socket and self.tcp_socket.state() == QTcpSocket.ConnectedState:
            target_socket = self.tcp_socket
        elif self.peer_socket and self.peer_socket.state() == QTcpSocket.ConnectedState:
            target_socket = self.peer_socket
 
        if target_socket:
            try:
                target_socket.write(data_qba)
                logger.debug("Data written to socket.")
                logger.info(f"Data sent via {target_socket.objectName()}: {message_type.value}")
            except Exception as e:
                logger.error(f"Error writing to socket: {e}", exc_info=True)
                self.status_changed.emit(f"Network error: {str(e)}")
        else:
            logger.warning("send_data - No active connection to send data.")
        logger.debug("send_data - Exit")

    def is_connected(self) -> bool:
        # QTcpSocket.ConnectedState is appropriate here
        return self.tcp_socket.state() == QTcpSocket.ConnectedState or \
               (self.peer_socket is not None and self.peer_socket.state() == QTcpSocket.ConnectedState)