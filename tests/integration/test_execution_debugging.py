import pytest
import os
import sys
import time # For small delays if needed
from unittest.mock import MagicMock, patch, ANY, call

from PySide6.QtCore import QProcess, Signal, QTimer # For QProcess.ExitStatus and Signal spec, QTimer

# Classes under test (or their interfaces)
from execution_coordinator import ExecutionCoordinator
from process_manager import ProcessManager
from debug_manager import DebugManager
from code_editor import CodeEditor # For mocking editor
from PySide6.QtWidgets import QTreeWidget, QListWidget # For specing panels

# Mock MainWindow and its relevant components
@pytest.fixture
def mock_main_window_for_exec_integration():
    mw = MagicMock(spec=[
        '_get_current_code_editor', 'status_bar', 'editor_file_coordinator',
        'process_manager', 'debug_manager', 'command_output_viewer',
        'debugger_toolbar', 'run_action_button', 'debug_action_button',
        'variables_panel', 'call_stack_panel', 'breakpoints_panel',
        'continue_action', 'step_over_action', 'step_into_action',
        'step_out_action', 'stop_action', 'active_breakpoints',
        'current_run_mode', 'bottom_dock_tab_widget', 'terminal_dock',
        'left_tab_widget', 'update_ui_for_control_state', # Added last one for completeness
        'activateWindow', 'raise_' # For _on_debugger_paused
    ])

    # Mock methods and attributes that ExecutionCoordinator interacts with
    mw._get_current_code_editor = MagicMock(return_value=None)
    mw.status_bar = MagicMock()
    mw.status_bar.showMessage = MagicMock()

    mw.editor_file_coordinator = MagicMock()
    mw.editor_file_coordinator.save_current_file = MagicMock(return_value=True)
    mw.editor_file_coordinator.editor_to_path = {} # Initialize as dict

    mw.command_output_viewer = MagicMock()
    mw.command_output_viewer.append_output = MagicMock()
    mw.command_output_viewer.clear_output = MagicMock()

    # Debugger UI elements
    mw.debugger_toolbar = MagicMock()
    mw.debugger_toolbar.setVisible = MagicMock()
    mw.variables_panel = MagicMock(spec=QTreeWidget) # Use actual type for spec
    mw.variables_panel.clear = MagicMock()
    mw.variables_panel.addTopLevelItem = MagicMock()
    mw.variables_panel.expandAll = MagicMock() # if it's called

    mw.call_stack_panel = MagicMock(spec=QListWidget) # Use actual type for spec
    mw.call_stack_panel.clear = MagicMock()
    mw.call_stack_panel.addItem = MagicMock()

    mw.breakpoints_panel = MagicMock(spec=QListWidget)
    mw.breakpoints_panel.clear = MagicMock() # if it's called
    mw.breakpoints_panel.addItem = MagicMock() # if it's called


    for action_name in ['run_action_button', 'debug_action_button', 'continue_action',
                        'step_over_action', 'step_into_action', 'step_out_action', 'stop_action']:
        action_mock = MagicMock()
        action_mock.setEnabled = MagicMock()
        setattr(mw, action_name, action_mock)

    mw.bottom_dock_tab_widget = MagicMock()
    mw.terminal_dock = MagicMock()
    mw.left_tab_widget = MagicMock()

    return mw

@pytest.fixture
def real_process_manager(qtbot): # qtbot for event loop processing
    pm = ProcessManager()
    return pm

@pytest.fixture
def real_debug_manager(qtbot):
    dm = DebugManager()

    dm._find_free_port = MagicMock(return_value=56789)
    dm._send_dap_request = MagicMock()

    with patch('debug_manager.QProcess') as mock_dm_qprocess_class:
        mock_dm_qprocess_instance = mock_dm_qprocess_class.return_value
        mock_dm_qprocess_instance.waitForStarted = MagicMock(return_value=True)
        mock_dm_qprocess_instance.start = MagicMock()
        # Mock signals on this internal QProcess instance
        # Create mock signal objects that can be emitted and have a connect method
        mock_dm_qprocess_instance.errorOccurred = MagicMock(spec=Signal)
        mock_dm_qprocess_instance.errorOccurred.connect = MagicMock()
        mock_dm_qprocess_instance.finished = MagicMock(spec=Signal)
        mock_dm_qprocess_instance.finished.connect = MagicMock()
        mock_dm_qprocess_instance.readyReadStandardOutput = MagicMock(spec=Signal)
        mock_dm_qprocess_instance.readyReadStandardOutput.connect = MagicMock()
        mock_dm_qprocess_instance.readyReadStandardError = MagicMock(spec=Signal)
        mock_dm_qprocess_instance.readyReadStandardError.connect = MagicMock()


        with patch('debug_manager.QTcpSocket') as mock_qtcpsocket_class:
            mock_dap_client_instance = mock_qtcpsocket_class.return_value

            # Store the instance on dm for later access if needed, or use the mock directly
            # dm.dap_client = mock_dap_client_instance

            def sim_connect_to_host(*args):
                # Simulate async connection: use QTimer.singleShot to emit 'connected'
                # Ensure that dm.dap_client is the mock_dap_client_instance when this is called
                if dm.dap_client == mock_dap_client_instance:
                    mock_dap_client_instance.isOpen.return_value = True
                    QTimer.singleShot(0, dm.dap_client.connected.emit)
                else:
                    # This case means dm.dap_client was reassigned or not the one we mocked.
                    # This can happen if DebugManager re-creates its socket.
                    # For this test, we assume it uses the one created at init.
                    pass


            mock_dap_client_instance.connectToHost.side_effect = sim_connect_to_host
            mock_dap_client_instance.isOpen = MagicMock(return_value=False)
            # Create mock signals for the socket, ensuring they are connectable and emittable
            mock_dap_client_instance.errorOccurred = MagicMock(spec=Signal)
            mock_dap_client_instance.errorOccurred.connect = MagicMock()
            mock_dap_client_instance.errorOccurred.emit = MagicMock()
            mock_dap_client_instance.connected = MagicMock(spec=Signal)
            mock_dap_client_instance.connected.connect = MagicMock()
            mock_dap_client_instance.connected.emit = MagicMock()
            mock_dap_client_instance.disconnected = MagicMock(spec=Signal)
            mock_dap_client_instance.disconnected.connect = MagicMock()
            mock_dap_client_instance.disconnected.emit = MagicMock()
            mock_dap_client_instance.readyRead = MagicMock(spec=Signal)
            mock_dap_client_instance.readyRead.connect = MagicMock()
            mock_dap_client_instance.readyRead.emit = MagicMock()

            yield dm

@pytest.fixture
def execution_coordinator_integration(qtbot, mock_main_window_for_exec_integration, real_process_manager, real_debug_manager):
    with patch('execution_coordinator.ConfigManager') as mock_cm_class:
        mock_cm_instance = mock_cm_class.return_value
        mock_cm_instance.load_setting.side_effect = lambda key, default: {
            'runner_config': {"Python": [sys.executable, "-u", "{file}"]}, # Changed from -c to -u {file}
            'extension_to_language_map': {".py": "Python"}
        }.get(key, default)

        exc = ExecutionCoordinator()

    mock_main_window_for_exec_integration.process_manager = real_process_manager
    mock_main_window_for_exec_integration.debug_manager = real_debug_manager

    exc.set_main_window_ref(mock_main_window_for_exec_integration)

    real_process_manager.output_received.connect(exc._handle_process_output)
    real_process_manager.process_started.connect(exc._handle_process_started)
    real_process_manager.process_finished.connect(exc._handle_process_finished)
    real_process_manager.process_error.connect(exc._handle_process_error)

    real_debug_manager.session_started.connect(exc._on_debug_session_started)
    real_debug_manager.session_stopped.connect(exc._on_debug_session_stopped)
    real_debug_manager.paused.connect(exc._on_debugger_paused)
    real_debug_manager.resumed.connect(exc._on_debugger_resumed)

    return exc, real_process_manager, real_debug_manager


@pytest.fixture
def mock_editor_for_exec(tmp_path):
    script_content = "print('Hello from integration test')\nprint('Second line')"
    script_file = tmp_path / "exec_test_script.py"
    script_file.write_text(script_content)

    editor = MagicMock(spec=CodeEditor)
    editor.file_path = str(script_file)
    editor.isReadOnly = MagicMock(return_value=False)
    # Mock gutter for breakpoint updates if EXC interacts with it directly (it does via MainWindow)
    editor.gutter = MagicMock()
    editor.gutter.update_breakpoints_display = MagicMock()
    editor.set_exec_highlight = MagicMock()


    return editor

# --- Integration Tests ---

def test_run_simple_python_script(qtbot, execution_coordinator_integration, mock_main_window_for_exec_integration, mock_editor_for_exec, tmp_path):
    exc, pm, _ = execution_coordinator_integration

    mock_main_window_for_exec_integration._get_current_code_editor.return_value = mock_editor_for_exec
    mock_main_window_for_exec_integration.editor_file_coordinator.editor_to_path = {
        mock_editor_for_exec: mock_editor_for_exec.file_path
    }

    received_outputs = []
    # Connect to the ProcessManager's signal directly for capturing output
    pm.output_received.connect(received_outputs.append)

    exc._handle_run_request()

    def check_process_finished():
        # Check if the finished signal was emitted (indirectly via EXC's handler re-enabling button)
        return mock_main_window_for_exec_integration.run_action_button.setEnabled.call_args == call(True)

    qtbot.waitUntil(check_process_finished, timeout=5000)

    # Check that ProcessManager.execute was called (it's mocked on the main_window's PM, not the real one)
    # This part needs clarification: if pm is real, its execute is real.
    # The mock_main_window_for_exec_integration.process_manager is the real pm.
    # So, we can't assert_called_once on its 'execute' if it's not a mock.
    # Instead, we check the effects: output received.
    # For this test, ProcessManager.execute IS real.

    full_output = "".join(received_outputs)
    assert "Hello from integration test" in full_output
    assert "Second line" in full_output
    mock_main_window_for_exec_integration.command_output_viewer.append_output.assert_any_call(ANY)


@patch('debug_manager.QTimer.singleShot')
def test_debug_simple_script_pause_and_step(mock_qtimer_singleshot, qtbot, execution_coordinator_integration, mock_main_window_for_exec_integration, mock_editor_for_exec, tmp_path):
    exc, _, dm = execution_coordinator_integration

    script_file_path = str(mock_editor_for_exec.file_path)
    mock_main_window_for_exec_integration._get_current_code_editor.return_value = mock_editor_for_exec
    mock_main_window_for_exec_integration.editor_file_coordinator.editor_to_path = {
        mock_editor_for_exec: script_file_path
    }

    breakpoint_line = 1
    exc.active_breakpoints = {script_file_path: {breakpoint_line}}
    dm.update_internal_breakpoints(script_file_path, {breakpoint_line})

    # Mock the DAP client on the real DebugManager instance
    # This is crucial because DebugManager creates its own QTcpSocket instance.
    # The one patched in the fixture might not be the one dm.dap_client refers to
    # if dm re-creates it.
    # mock_dap_client_on_dm = MagicMock(spec=dm.dap_client) # Use spec from existing instance
    # mock_dap_client_on_dm.isOpen = MagicMock(return_value=False)
    # mock_dap_client_on_dm.connectToHost = MagicMock(side_effect=lambda host, port: QTimer.singleShot(0, mock_dap_client_on_dm.connected.emit))
    # mock_dap_client_on_dm.connected = Signal()
    # mock_dap_client_on_dm.disconnected = Signal()
    # mock_dap_client_on_dm.readyRead = Signal()
    # mock_dap_client_on_dm.errorOccurred = Signal(QProcess.ProcessError) # Or appropriate socket error type
    # mock_dap_client_on_dm.write = MagicMock()
    # dm.dap_client = mock_dap_client_on_dm # This direct assignment is no longer needed due to the fixture's patch


    exc._handle_debug_request()

    # Wait for DAP client to be "connected"
    # mock_dap_client_on_dm was commented out; we should use dm.dap_client,
    # which is the instance created and mocked via the fixture's patch.
    qtbot.waitUntil(lambda: dm.dap_client and dm.dap_client.isOpen.return_value is True, timeout=2000)

    # Simulate handshake completion and session_started signal
    dm._dap_request_pending_response['initialize_complete'] = True
    dm._dap_request_pending_response['launch_complete'] = True
    dm._dap_request_pending_response['configurationDone_complete'] = True # For session_started
    dm.session_started.emit()
    qtbot.wait(50) # Allow signal processing

    mock_main_window_for_exec_integration.debugger_toolbar.setVisible.assert_called_with(True)

    call_stack_data = [{'id': 1, 'name': '<module>', 'file': script_file_path, 'line': breakpoint_line}]
    variables_data = [{'name': '__name__', 'type': 'str', 'value': '__main__', 'variablesReference': 0}]

    dm.paused.emit(12345, "breakpoint", call_stack_data, variables_data)
    qtbot.wait(50)

    mock_main_window_for_exec_integration.call_stack_panel.addItem.assert_called()
    mock_main_window_for_exec_integration.variables_panel.addTopLevelItem.assert_called()
    mock_editor_for_exec.set_exec_highlight.assert_called_with(breakpoint_line)
    mock_main_window_for_exec_integration.step_over_action.setEnabled.assert_called_with(True)

    def mock_step_over_effect():
        dm.resumed.emit()
        # QTimer.singleShot(10, lambda: dm.paused.emit(12345, "step", call_stack_data, variables_data)) # Same data for simplicity
        # Emit directly to simplify timing for the test
        dm.paused.emit(12345, "step", call_stack_data, variables_data)

    dm.step_over = MagicMock(side_effect=mock_step_over_effect)

    # This assumes the UI action directly calls dm.step_over()
    # In MainWindow, self.step_over_action.triggered.connect(lambda: self.debug_manager.step_over())
    # So, we can call it directly on dm.

    # Setup checkers for signals expected after dm.step_over() is called
    resumed_checker = MagicMock()
    dm.resumed.connect(resumed_checker)

    # This checker will catch the 'paused' signal emitted *after* the step_over action.
    paused_after_step_checker = MagicMock()
    dm.paused.connect(paused_after_step_checker) # Connect to the real dm.paused signal

    # The mock_step_over_effect is already defined in the outer scope of the test function.
    # Ensure it uses the correct variables (dm, call_stack_data, variables_data) accessible in its scope.
    # dm.step_over = MagicMock(side_effect=mock_step_over_effect) # This is already done.

    dm.step_over() # Call the mocked method that triggers real signal emissions

    qtbot.waitUntil(lambda: resumed_checker.call_count > 0, timeout=1000)
    # The paused_after_step_checker will see the second pause event.
    qtbot.waitUntil(lambda: paused_after_step_checker.call_count > 0, timeout=1000)

    assert resumed_checker.call_count >= 1
    # paused_after_step_checker only sees the pause emission triggered from mock_step_over_effect
    assert paused_after_step_checker.call_count >= 1
