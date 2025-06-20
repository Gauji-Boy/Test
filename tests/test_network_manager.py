import pytest
import json
from unittest.mock import MagicMock, patch, call

from PySide6.QtCore import Signal, QByteArray, QObject
from PySide6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress, QAbstractSocket

# Adjust import path as necessary
from network_manager import NetworkManager, NetworkMessageType

# Helper for signal assertion
def assert_signal_emitted(signal_mock, *args, **kwargs):
    # Simplified version for this test suite focusing on direct argument matching
    # or checking if any call contains all specified kwargs.
    if args and kwargs:
        signal_mock.emit.assert_any_call(*args, **kwargs)
    elif args:
        signal_mock.emit.assert_any_call(*args)
    elif kwargs:
        found = False
        for call_args_tuple in signal_mock.emit.call_args_list:
            actual_args, actual_kwargs = call_args_tuple
            # Check if all provided kwargs are in the actual call's kwargs
            # and their values match.
            match = True
            for k, v_expected in kwargs.items():
                if k not in actual_kwargs or actual_kwargs[k] != v_expected:
                    match = False
                    break
            if match:
                found = True
                break
        assert found, f"Signal not emitted with kwargs {kwargs}. Calls: {signal_mock.emit.call_args_list}"
    else:
        signal_mock.emit.assert_called()


@pytest.fixture
def network_manager(qtbot): # qtbot might be useful if NetworkManager interacts with event loop
    nm = NetworkManager()
    # Mock signals
    nm.data_received = MagicMock(spec=Signal)
    nm.status_changed = MagicMock(spec=Signal)
    nm.peer_connected = MagicMock(spec=Signal)
    nm.peer_disconnected = MagicMock(spec=Signal)
    nm.control_request_received = MagicMock(spec=Signal)
    nm.control_granted = MagicMock(spec=Signal)
    nm.control_declined = MagicMock(spec=Signal)
    nm.control_revoked = MagicMock(spec=Signal)

    # Mock the internal QTcpServer and QTcpSocket directly on the instance for more control
    # This way, when NetworkManager calls self.tcp_server.listen(), it calls our mock.
    nm.tcp_server = MagicMock(spec=QTcpServer)
    nm.tcp_socket = MagicMock(spec=QTcpSocket) # This is the client socket

    # Simulate that the server is not initially listening and socket not connected
    nm.tcp_server.isListening.return_value = False
    nm.tcp_socket.state.return_value = QAbstractSocket.UnconnectedState

    return nm

# --- Tests for start_hosting ---

def test_start_hosting_success(network_manager):
    port = 12345
    network_manager.tcp_server.listen.return_value = True # Simulate successful listen

    assert network_manager.start_hosting(port)
    network_manager.tcp_server.listen.assert_called_once_with(QHostAddress.Any, port)
    assert_signal_emitted(network_manager.status_changed, f"Hosting on port {port}...")

def test_start_hosting_already_listening(network_manager):
    network_manager.tcp_server.isListening.return_value = True # Simulate already listening

    assert not network_manager.start_hosting(12345)
    assert_signal_emitted(network_manager.status_changed, "Server already listening.")
    network_manager.tcp_server.listen.assert_not_called()

def test_start_hosting_listen_failure(network_manager):
    port = 12345
    network_manager.tcp_server.listen.return_value = False # Simulate listen failure
    network_manager.tcp_server.errorString.return_value = "Bind error"

    assert not network_manager.start_hosting(port)
    assert_signal_emitted(network_manager.status_changed, "Failed to start hosting: Bind error")

# --- Tests for connect_to_host ---

def test_connect_to_host_success(network_manager):
    ip = "127.0.0.1"
    port = 12345
    network_manager.connect_to_host(ip, port)
    network_manager.tcp_socket.connectToHost.assert_called_once_with(ip, port)
    assert_signal_emitted(network_manager.status_changed, f"Connecting to {ip}:{port}...")

def test_connect_to_host_already_connected(network_manager):
    network_manager.tcp_socket.state.return_value = QAbstractSocket.ConnectedState # Simulate connected
    network_manager.connect_to_host("127.0.0.1", 12345)
    assert_signal_emitted(network_manager.status_changed, "Already connected to a host.")
    network_manager.tcp_socket.connectToHost.assert_not_called()

# --- Tests for stop_session ---

def test_stop_session_hosting(network_manager):
    network_manager.tcp_server.isListening.return_value = True
    # Simulate a peer was connected
    mock_peer_socket = MagicMock(spec=QTcpSocket)
    network_manager.peer_socket = mock_peer_socket

    network_manager.stop_session()

    network_manager.tcp_server.close.assert_called_once()
    mock_peer_socket.disconnectFromHost.assert_called_once()
    mock_peer_socket.waitForDisconnected.assert_called_once_with(1000)
    assert network_manager.peer_socket is None
    assert_signal_emitted(network_manager.status_changed, "Hosting session stopped.")

def test_stop_session_client(network_manager):
    network_manager.tcp_server.isListening.return_value = False # Not hosting
    network_manager.tcp_socket.state.return_value = QAbstractSocket.ConnectedState # Connected as client

    network_manager.stop_session()

    network_manager.tcp_socket.disconnectFromHost.assert_called_once()
    network_manager.tcp_socket.waitForDisconnected.assert_called_once_with(1000)
    assert_signal_emitted(network_manager.status_changed, "Connected session stopped.")

def test_stop_session_no_active_session(network_manager):
    network_manager.tcp_server.isListening.return_value = False
    network_manager.tcp_socket.state.return_value = QAbstractSocket.UnconnectedState

    network_manager.stop_session()
    assert_signal_emitted(network_manager.status_changed, "No active session to stop.")

# --- Tests for _on_new_connection ---

def test_on_new_connection_first_peer(network_manager):
    mock_pending_socket = MagicMock(spec=QTcpSocket)
    mock_pending_socket.peerAddress.return_value.toString.return_value = "192.168.1.100"
    mock_pending_socket.peerPort.return_value = 54321
    network_manager.tcp_server.nextPendingConnection.return_value = mock_pending_socket
    network_manager.peer_socket = None # Ensure no peer initially

    network_manager._on_new_connection() # Manually call slot

    assert network_manager.peer_socket == mock_pending_socket
    mock_pending_socket.readyRead.connect.assert_called_with(network_manager._read_data)
    mock_pending_socket.disconnected.connect.assert_called_with(network_manager._on_peer_disconnected)
    assert_signal_emitted(network_manager.status_changed, "Peer connected from 192.168.1.100:54321")
    network_manager.peer_connected.emit.assert_called_once()
    assert mock_pending_socket in network_manager.buffer

def test_on_new_connection_reject_second_peer(network_manager):
    network_manager.peer_socket = MagicMock(spec=QTcpSocket) # A peer is already connected

    mock_rejected_socket = MagicMock(spec=QTcpSocket)
    network_manager.tcp_server.nextPendingConnection.return_value = mock_rejected_socket

    network_manager._on_new_connection()

    assert_signal_emitted(network_manager.status_changed, "Rejected new connection: already have a peer.")
    mock_rejected_socket.disconnectFromHost.assert_called_once()

# --- Tests for _on_connected (client connected to host) ---

def test_on_connected_client(network_manager):
    network_manager.tcp_socket.peerAddress.return_value.toString.return_value = "10.0.0.1"
    network_manager.tcp_socket.peerPort.return_value = 8080

    network_manager._on_connected() # Manually call slot

    assert_signal_emitted(network_manager.status_changed, "Connected to host 10.0.0.1:8080")
    network_manager.peer_connected.emit.assert_called_once()
    assert network_manager.tcp_socket in network_manager.buffer

# --- Tests for _on_disconnected (client disconnected from host) ---

def test_on_disconnected_client(network_manager):
    # Add to buffer to simulate it was there
    network_manager.buffer[network_manager.tcp_socket] = "some data"
    network_manager._on_disconnected()
    assert_signal_emitted(network_manager.status_changed, "Disconnected from host.")
    network_manager.peer_disconnected.emit.assert_called_once()
    assert network_manager.tcp_socket not in network_manager.buffer

# --- Tests for _on_peer_disconnected (server's peer disconnected) ---

def test_on_peer_disconnected_server(network_manager):
    mock_peer_socket = MagicMock(spec=QTcpSocket)
    network_manager.peer_socket = mock_peer_socket
    network_manager.buffer[mock_peer_socket] = "peer data"

    network_manager._on_peer_disconnected()

    assert_signal_emitted(network_manager.status_changed, "Peer disconnected.")
    network_manager.peer_disconnected.emit.assert_called_once()
    mock_peer_socket.deleteLater.assert_called_once()
    assert network_manager.peer_socket is None
    assert mock_peer_socket not in network_manager.buffer

# --- Tests for _read_data and send_data ---

@pytest.mark.parametrize("message_type, content_payload, expected_signal_mock, expected_signal_args", [
    (NetworkMessageType.TEXT_UPDATE, "Hello there", "data_received", ("Hello there",)),
    (NetworkMessageType.REQ_CONTROL, None, "control_request_received", ()),
    (NetworkMessageType.GRANT_CONTROL, None, "control_granted", ()),
    (NetworkMessageType.DECLINE_CONTROL, None, "control_declined", ()),
    (NetworkMessageType.REVOKE_CONTROL, None, "control_revoked", ()),
])
def test_read_data_various_messages(network_manager, message_type, content_payload, expected_signal_mock, expected_signal_args):
    # Simulate data being read from the client socket (self.tcp_socket)
    # This socket will be the 'sender' in _read_data
    mock_sender_socket = network_manager.tcp_socket
    network_manager.buffer[mock_sender_socket] = "" # Initialize buffer for this socket

    message_dict = {'type': message_type.value}
    if content_payload is not None:
        message_dict['content'] = content_payload

    json_message = json.dumps(message_dict) + '\n' # Add newline delimiter

    # Simulate QTcpSocket.readAll()
    mock_sender_socket.readAll.return_value = QByteArray(json_message.encode('utf-8'))

    # Manually call _read_data, passing the socket that "emitted" readyRead
    # The 'sender()' method in _read_data needs to return this socket.
    with patch.object(network_manager, 'sender', return_value=mock_sender_socket):
        network_manager._read_data()

    signal_to_check = getattr(network_manager, expected_signal_mock)
    if expected_signal_args:
        assert_signal_emitted(signal_to_check, *expected_signal_args)
    else:
        assert_signal_emitted(signal_to_check)


def test_read_data_partial_message_then_complete(network_manager):
    mock_sender_socket = network_manager.tcp_socket
    network_manager.buffer[mock_sender_socket] = ""

    part1 = json.dumps({'type': NetworkMessageType.TEXT_UPDATE.value, 'content': "Part 1 "})[:-5] # Incomplete JSON
    part2 = "text"}\n" # Completes the JSON for "Part 1 text"

    with patch.object(network_manager, 'sender', return_value=mock_sender_socket):
        # First read: partial message
        mock_sender_socket.readAll.return_value = QByteArray(part1.encode('utf-8'))
        network_manager._read_data()
        network_manager.data_received.emit.assert_not_called() # No complete message yet
        assert network_manager.buffer[mock_sender_socket] == part1

        # Second read: completes the message
        mock_sender_socket.readAll.return_value = QByteArray(part2.encode('utf-8'))
        network_manager._read_data()
        assert_signal_emitted(network_manager.data_received, "Part 1 text")
        assert network_manager.buffer[mock_sender_socket] == "" # Buffer should be empty


def test_send_data_to_client_socket(network_manager): # When NM is connected to a host
    network_manager.tcp_socket.state.return_value = QAbstractSocket.ConnectedState
    network_manager.peer_socket = None # Not hosting

    message_type = NetworkMessageType.TEXT_UPDATE
    content = "Test data"
    expected_json_message = json.dumps({'type': message_type.value, 'content': content}) + '\n'

    network_manager.send_data(message_type, content)

    network_manager.tcp_socket.write.assert_called_once_with(QByteArray(expected_json_message.encode('utf-8')))

def test_send_data_to_peer_socket(network_manager): # When NM is hosting
    network_manager.tcp_server.isListening.return_value = True
    mock_peer = MagicMock(spec=QTcpSocket)
    mock_peer.state.return_value = QAbstractSocket.ConnectedState
    network_manager.peer_socket = mock_peer
    network_manager.tcp_socket.state.return_value = QAbstractSocket.UnconnectedState # Not connected as client

    message_type = NetworkMessageType.REQ_CONTROL
    expected_json_message = json.dumps({'type': message_type.value}) + '\n'

    network_manager.send_data(message_type)

    mock_peer.write.assert_called_once_with(QByteArray(expected_json_message.encode('utf-8')))


def test_send_data_no_connection(network_manager):
    network_manager.tcp_socket.state.return_value = QAbstractSocket.UnconnectedState
    network_manager.peer_socket = None

    network_manager.send_data(NetworkMessageType.TEXT_UPDATE, "data")

    network_manager.tcp_socket.write.assert_not_called()
    # If peer_socket was mocked and assigned, also check it's not called:
    # network_manager.peer_socket.write.assert_not_called() (if it existed)

# --- Test for is_connected ---

def test_is_connected(network_manager):
    # Initially, neither client socket is connected nor is there a peer_socket
    network_manager.tcp_socket.state.return_value = QAbstractSocket.UnconnectedState
    network_manager.peer_socket = None
    assert not network_manager.is_connected()

    # Connected as a client
    network_manager.tcp_socket.state.return_value = QAbstractSocket.ConnectedState
    assert network_manager.is_connected()
    network_manager.tcp_socket.state.return_value = QAbstractSocket.UnconnectedState # Reset

    # Hosting and a peer is connected
    mock_peer = MagicMock(spec=QTcpSocket)
    mock_peer.state.return_value = QAbstractSocket.ConnectedState
    network_manager.peer_socket = mock_peer
    assert network_manager.is_connected()

    # Hosting but peer disconnected
    mock_peer.state.return_value = QAbstractSocket.UnconnectedState
    assert not network_manager.is_connected()
    network_manager.peer_socket = None # Reset
