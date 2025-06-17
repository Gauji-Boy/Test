import logging
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox
from connection_dialog import ConnectionDialog
from network_manager import NetworkMessageType
from code_editor import CodeEditor
from typing import TYPE_CHECKING, Optional # Added

if TYPE_CHECKING:
    from main_window import MainWindow # Assuming main_window.py

logger = logging.getLogger(__name__)

class CollaborationService(QObject):
    main_win: Optional['MainWindow'] # Forward reference, now Optional
    is_host: bool
    has_control: bool
    is_updating_from_network: bool

    def __init__(self) -> None: # Removed main_window parameter
        super().__init__()
        self.main_win = None # Initialize as None
        self.is_host = False
        self.has_control = False
        self.is_updating_from_network = False

    def set_main_window_ref(self, main_window: 'MainWindow') -> None:
        self.main_win = main_window
        # No other initializations depended on main_window in the original __init__

    def is_connected(self) -> bool:
        if not self.main_win: return False
        return self.main_win.network_manager.is_connected()

    @Slot()
    def start_hosting_session(self) -> None:
        if not self.main_win: return
        ip_port_tuple: tuple[str | None, int | None] = ConnectionDialog.get_details(self.main_win)
        ip: str | None = ip_port_tuple[0]
        port: int | None = ip_port_tuple[1]

        if ip and port is not None:
            if self.main_win.network_manager.start_hosting(port):
                self.main_win.status_bar.showMessage(f"Hosting on port {port}...")
                self.main_win.start_host_action.setEnabled(False)
                self.main_win.connect_host_action.setEnabled(False)
                self.main_win.stop_session_action.setEnabled(True)
                self.is_host = True
                self.has_control = True
                self.main_win.update_ui_for_control_state()
                logger.info(f"Started hosting on port {port}. is_host={self.is_host}, has_control={self.has_control}")
            else:
                logger.error("Failed to start hosting session.")
                QMessageBox.critical(self.main_win, "Error", "Failed to start hosting session.")

    @Slot()
    def connect_to_host_session(self) -> None:
        if not self.main_win: return
        ip_port_tuple: tuple[str | None, int | None] = ConnectionDialog.get_details(self.main_win)
        ip: str | None = ip_port_tuple[0]
        port: int | None = ip_port_tuple[1]

        if ip and port is not None:
            self.main_win.network_manager.connect_to_host(ip, port)
            self.main_win.status_bar.showMessage(f"Connecting to {ip}:{port}...")
            self.main_win.start_host_action.setEnabled(False)
            self.main_win.connect_host_action.setEnabled(False)
            self.main_win.stop_session_action.setEnabled(True)
            self.is_host = False
            self.has_control = False
            self.main_win.update_ui_for_control_state()
            logger.info(f"Connected to host {ip}:{port}. is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def stop_current_session(self) -> None:
        if not self.main_win: return
        self.main_win.network_manager.stop_session()
        self.main_win.status_bar.showMessage("Session stopped.")
        self.main_win.start_host_action.setEnabled(True)
        self.main_win.connect_host_action.setEnabled(True)
        self.main_win.stop_session_action.setEnabled(False)
        self.is_host = False
        self.has_control = False
        self.main_win.update_ui_for_control_state()
        logger.info(f"Stopped current session. is_host={self.is_host}, has_control={self.has_control}")

    @Slot(str)
    def on_network_data_received(self, data: str) -> None:
        if not self.main_win: return
        current_editor: CodeEditor | None = self.main_win.editor_file_coordinator._get_current_code_editor()
        if current_editor:
            try:
                content: str = data
                self.is_updating_from_network = True
                current_cursor_pos: int = current_editor.textCursor().position()
                current_editor.setPlainText(content)
                cursor = current_editor.textCursor()
                cursor.setPosition(min(current_cursor_pos, len(content)))
                current_editor.setTextCursor(cursor)
                self.is_updating_from_network = False
                self.main_win._update_undo_redo_actions()
            except Exception as e:
                logger.error(f"Error processing received network data: {e}", exc_info=True)

    @Slot()
    def on_peer_connected(self) -> None:
        if not self.main_win: return
        self.main_win.status_bar.showMessage("Peer connected!")
        QMessageBox.information(self.main_win, "Connection Status", "Peer connected successfully!")
        self.main_win.start_host_action.setEnabled(False)
        self.main_win.connect_host_action.setEnabled(False)
        self.main_win.stop_session_action.setEnabled(True)
        self.main_win.update_ui_for_control_state()
        logger.info(f"Peer connected. is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_peer_disconnected(self) -> None:
        if not self.main_win: return
        self.main_win.status_bar.showMessage("Peer disconnected.")
        QMessageBox.warning(self.main_win, "Connection Status", "Peer disconnected.")
        self.main_win.start_host_action.setEnabled(True)
        self.main_win.connect_host_action.setEnabled(True)
        self.main_win.stop_session_action.setEnabled(False)
        self.is_host = False
        self.has_control = False
        self.main_win.update_ui_for_control_state()
        logger.info(f"Peer disconnected. is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def request_control(self) -> None:
        if not self.main_win: return
        if not self.is_host and not self.has_control and self.is_connected():
            self.main_win.network_manager.send_data(NetworkMessageType.REQ_CONTROL)
            self.main_win.status_bar.showMessage("Requesting control...")
            self.main_win.request_control_button.setEnabled(False)
            logger.debug(f"Requested control. is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_control_request_received(self) -> None:
        if not self.main_win: return
        if self.is_host and self.has_control:
            reply: QMessageBox.StandardButton = QMessageBox.question(self.main_win, "Control Request",
                                         "The client has requested editing control. Grant control?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.main_win.network_manager.send_data(NetworkMessageType.GRANT_CONTROL)
                self.has_control = False
                self.main_win.update_ui_for_control_state()
                self.main_win.status_bar.showMessage("Control granted to client.")
                logger.info("Control granted to client.")
            else:
                self.main_win.network_manager.send_data(NetworkMessageType.DECLINE_CONTROL)
                self.main_win.status_bar.showMessage("Control request declined.")
                logger.info("Control request declined by host.")

    @Slot()
    def on_control_granted(self) -> None:
        if not self.main_win: return
        if not self.is_host:
            self.has_control = True
            self.main_win.update_ui_for_control_state()
            self.main_win.status_bar.showMessage("You have been granted editing control.")
            logger.info(f"Control granted to this client. is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_control_declined(self) -> None:
        if not self.main_win: return
        if not self.is_host:
            self.main_win.status_bar.showMessage("Host declined the request.", 3000)
            self.main_win.request_control_button.setEnabled(True)

    @Slot()
    def on_control_revoked(self) -> None:
        if not self.main_win: return
        if not self.is_host:
            self.has_control = False
            self.main_win.update_ui_for_control_state()
            self.main_win.status_bar.showMessage("Editing control has been revoked.")
            logger.info(f"Control revoked for this client. is_host={self.is_host}, has_control={self.has_control}")

    @Slot()
    def on_host_reclaim_control(self) -> None:
        if not self.main_win: return
        if self.is_host and not self.has_control:
            self.has_control = True
            self.main_win.update_ui_for_control_state()
            self.main_win.network_manager.send_data(NetworkMessageType.REVOKE_CONTROL)
            self.main_win.status_bar.showMessage("You have reclaimed editing control.")
            logger.info(f"Host reclaimed control. is_host={self.is_host}, has_control={self.has_control}")

# Ensure a newline at the end of the file
