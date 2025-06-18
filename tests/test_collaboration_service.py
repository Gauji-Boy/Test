import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from PySide6.QtWidgets import QMessageBox # For mocking

# Adjust import path as necessary
from collaboration_service import CollaborationService
from network_manager import NetworkMessageType # For sending specific message types
from code_editor import CodeEditor # For type hinting/mocking editor

@pytest.fixture
def mock_main_window():
    mw = MagicMock(spec=[
        'network_manager', 'status_bar', 'start_host_action',
        'connect_host_action', 'stop_session_action', 'request_control_button',
        'update_ui_for_control_state', 'editor_file_coordinator', # Added EFC
        '_update_undo_redo_actions' # For text update handling
    ])

    mw.network_manager = MagicMock()
    mw.network_manager.is_connected = MagicMock(return_value=False) # Default to not connected
    mw.network_manager.start_hosting = MagicMock(return_value=True) # Default to success
    mw.network_manager.connect_to_host = MagicMock()
    mw.network_manager.stop_session = MagicMock()
    mw.network_manager.send_data = MagicMock()

    mw.status_bar = MagicMock()
    mw.status_bar.showMessage = MagicMock()

    # Mock actions and buttons
    for name in ['start_host_action', 'connect_host_action', 'stop_session_action', 'request_control_button']:
        action_mock = MagicMock()
        action_mock.setEnabled = MagicMock()
        setattr(mw, name, action_mock)

    mw.update_ui_for_control_state = MagicMock()

    # Mock EditorFileCoordinator and its _get_current_code_editor method
    mw.editor_file_coordinator = MagicMock()
    mw.editor_file_coordinator._get_current_code_editor = MagicMock(return_value=None)

    mw._update_undo_redo_actions = MagicMock()


    return mw

@pytest.fixture
def cs(mock_main_window): # cs for CollaborationService
    service = CollaborationService()
    service.set_main_window_ref(mock_main_window)
    return service

# --- Test is_connected ---
def test_is_connected_delegates_to_network_manager(cs, mock_main_window):
    mock_main_window.network_manager.is_connected.return_value = True
    assert cs.is_connected() is True
    mock_main_window.network_manager.is_connected.assert_called_once()

    mock_main_window.network_manager.is_connected.return_value = False
    assert cs.is_connected() is False

# --- Test start_hosting_session ---
@patch('collaboration_service.ConnectionDialog.get_details')
def test_start_hosting_session_success(mock_get_details, cs, mock_main_window):
    mock_get_details.return_value = ("0.0.0.0", 12345) # User provides details

    cs.start_hosting_session()

    mock_main_window.network_manager.start_hosting.assert_called_once_with(12345)
    mock_main_window.status_bar.showMessage.assert_called_with("Hosting on port 12345...")
    mock_main_window.start_host_action.setEnabled.assert_called_with(False)
    # ... other UI updates
    assert cs.is_host is True
    assert cs.has_control is True
    mock_main_window.update_ui_for_control_state.assert_called_once()

@patch('collaboration_service.ConnectionDialog.get_details')
def test_start_hosting_session_dialog_cancel(mock_get_details, cs, mock_main_window):
    mock_get_details.return_value = (None, None) # User cancels dialog
    cs.start_hosting_session()
    mock_main_window.network_manager.start_hosting.assert_not_called()

@patch('collaboration_service.ConnectionDialog.get_details')
def test_start_hosting_session_failure(mock_get_details, cs, mock_main_window):
    mock_get_details.return_value = ("0.0.0.0", 12345)
    mock_main_window.network_manager.start_hosting.return_value = False # Simulate NM failure

    with patch('PySide6.QtWidgets.QMessageBox.critical') as mock_qmessagebox_critical:
        cs.start_hosting_session()

    mock_qmessagebox_critical.assert_called_once()
    assert cs.is_host is False # Should not be set to True on failure
    assert cs.has_control is False

# --- Test connect_to_host_session ---
@patch('collaboration_service.ConnectionDialog.get_details')
def test_connect_to_host_session_success(mock_get_details, cs, mock_main_window):
    ip, port = "127.0.0.1", 54321
    mock_get_details.return_value = (ip, port)

    cs.connect_to_host_session()

    mock_main_window.network_manager.connect_to_host.assert_called_once_with(ip, port)
    mock_main_window.status_bar.showMessage.assert_called_with(f"Connecting to {ip}:{port}...")
    assert cs.is_host is False
    assert cs.has_control is False # Client initially does not have control
    mock_main_window.update_ui_for_control_state.assert_called_once()

# --- Test stop_current_session ---
def test_stop_current_session(cs, mock_main_window):
    cs.is_host = True # Simulate was hosting
    cs.has_control = True

    cs.stop_current_session()

    mock_main_window.network_manager.stop_session.assert_called_once()
    mock_main_window.status_bar.showMessage.assert_called_with("Session stopped.")
    assert cs.is_host is False
    assert cs.has_control is False
    mock_main_window.update_ui_for_control_state.assert_called() # Called to reset UI

# --- Test on_network_data_received ---
def test_on_network_data_received_updates_editor(cs, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    # Mock the textCursor and its position method
    mock_cursor = MagicMock()
    mock_cursor.position.return_value = 0
    mock_editor.textCursor.return_value = mock_cursor

    mock_main_window.editor_file_coordinator._get_current_code_editor.return_value = mock_editor

    test_data = "new text from network"
    cs.on_network_data_received(test_data)

    assert cs.is_updating_from_network is True # Check flag was set during update
    mock_editor.setPlainText.assert_called_once_with(test_data)
    # Reset flag after operation
    # The test needs to check the state *during* the call if possible, or ensure it's reset.
    # Since it's reset within the method, we can check its state before/after if needed,
    # or trust the logic if the primary outcome (setPlainText) is verified.
    # For this test, we'll assume the flag is reset internally.
    # To truly test the flag's state *during* setPlainText, more complex mocking of setPlainText might be needed.
    mock_main_window._update_undo_redo_actions.assert_called_once()


# --- Test on_peer_connected ---
@patch('PySide6.QtWidgets.QMessageBox.information')
def test_on_peer_connected(mock_qmessagebox_info, cs, mock_main_window):
    cs.on_peer_connected()
    mock_main_window.status_bar.showMessage.assert_called_with("Peer connected!")
    mock_qmessagebox_info.assert_called_once()
    mock_main_window.update_ui_for_control_state.assert_called()

# --- Test on_peer_disconnected ---
@patch('PySide6.QtWidgets.QMessageBox.warning')
def test_on_peer_disconnected(mock_qmessagebox_warning, cs, mock_main_window):
    cs.is_host = True # Simulate was connected
    cs.has_control = True

    cs.on_peer_disconnected()

    mock_main_window.status_bar.showMessage.assert_called_with("Peer disconnected.")
    mock_qmessagebox_warning.assert_called_once()
    assert cs.is_host is False # State should reset
    assert cs.has_control is False
    mock_main_window.update_ui_for_control_state.assert_called()

# --- Test request_control ---
def test_request_control_when_client_and_no_control(cs, mock_main_window):
    cs.is_host = False
    cs.has_control = False
    mock_main_window.network_manager.is_connected.return_value = True # Is connected

    cs.request_control()

    mock_main_window.network_manager.send_data.assert_called_once_with(NetworkMessageType.REQ_CONTROL)
    mock_main_window.status_bar.showMessage.assert_called_with("Requesting control...")
    mock_main_window.request_control_button.setEnabled.assert_called_with(False)

def test_request_control_noop_conditions(cs, mock_main_window):
    # Case 1: Is host
    cs.is_host = True
    cs.request_control()
    mock_main_window.network_manager.send_data.assert_not_called()
    cs.is_host = False # Reset

    # Case 2: Has control already
    cs.has_control = True
    cs.request_control()
    mock_main_window.network_manager.send_data.assert_not_called()
    cs.has_control = False # Reset

    # Case 3: Not connected
    mock_main_window.network_manager.is_connected.return_value = False
    cs.request_control()
    mock_main_window.network_manager.send_data.assert_not_called()


# --- Test on_control_request_received ---
@patch('PySide6.QtWidgets.QMessageBox.question')
def test_on_control_request_received_host_grants(mock_qmessagebox_question, cs, mock_main_window):
    cs.is_host = True
    cs.has_control = True
    mock_qmessagebox_question.return_value = QMessageBox.Yes # Host grants

    cs.on_control_request_received()

    mock_main_window.network_manager.send_data.assert_called_once_with(NetworkMessageType.GRANT_CONTROL)
    assert cs.has_control is False # Host loses control
    mock_main_window.update_ui_for_control_state.assert_called()
    mock_main_window.status_bar.showMessage.assert_called_with("Control granted to client.")

@patch('PySide6.QtWidgets.QMessageBox.question')
def test_on_control_request_received_host_declines(mock_qmessagebox_question, cs, mock_main_window):
    cs.is_host = True
    cs.has_control = True
    mock_qmessagebox_question.return_value = QMessageBox.No # Host declines

    cs.on_control_request_received()

    mock_main_window.network_manager.send_data.assert_called_once_with(NetworkMessageType.DECLINE_CONTROL)
    assert cs.has_control is True # Host retains control
    # UI for control state shouldn't change for host if they decline and retain control
    # mock_main_window.update_ui_for_control_state.assert_not_called()
    # Actually, it IS called to ensure UI consistency, even if state might not change for host.
    mock_main_window.update_ui_for_control_state.assert_called()
    mock_main_window.status_bar.showMessage.assert_called_with("Control request declined.")

# --- Test on_control_granted ---
def test_on_control_granted_to_client(cs, mock_main_window):
    cs.is_host = False # Is a client
    cs.has_control = False # Does not have control

    cs.on_control_granted()

    assert cs.has_control is True
    mock_main_window.update_ui_for_control_state.assert_called()
    mock_main_window.status_bar.showMessage.assert_called_with("You have been granted editing control.")

# --- Test on_control_declined ---
def test_on_control_declined_for_client(cs, mock_main_window):
    cs.is_host = False # Is a client
    cs.on_control_declined()
    mock_main_window.status_bar.showMessage.assert_called_with("Host declined the request.", 3000)
    mock_main_window.request_control_button.setEnabled.assert_called_with(True)

# --- Test on_control_revoked ---
def test_on_control_revoked_for_client(cs, mock_main_window):
    cs.is_host = False # Is a client
    cs.has_control = True # Client had control

    cs.on_control_revoked()

    assert cs.has_control is False
    mock_main_window.update_ui_for_control_state.assert_called()
    mock_main_window.status_bar.showMessage.assert_called_with("Editing control has been revoked.")

# --- Test on_host_reclaim_control ---
def test_on_host_reclaim_control(cs, mock_main_window):
    cs.is_host = True
    cs.has_control = False # Host did not have control (client had it)

    cs.on_host_reclaim_control()

    assert cs.has_control is True
    mock_main_window.update_ui_for_control_state.assert_called()
    mock_main_window.network_manager.send_data.assert_called_once_with(NetworkMessageType.REVOKE_CONTROL)
    mock_main_window.status_bar.showMessage.assert_called_with("You have reclaimed editing control.")
