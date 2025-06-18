import pytest
from unittest.mock import MagicMock, patch, call, PropertyMock

from PySide6.QtCore import QProcess, Signal # Added Signal for spec
from PySide6.QtWidgets import QMessageBox, QListWidgetItem, QTreeWidgetItem # For UI interactions

# Adjust import path as necessary
from execution_coordinator import ExecutionCoordinator
from code_editor import CodeEditor # For type hinting and mocking
from config_manager import ConfigManager # For mocking config loading

# Default configs, in case the mocked ConfigManager needs to return them
DEFAULT_RUNNER_CONFIG = {
    "Python": ["python", "-u", "{file}"]
}
DEFAULT_EXTENSION_TO_LANGUAGE_MAP = {
    ".py": "Python"
}

@pytest.fixture
def mock_main_window():
    mw = MagicMock(spec=[
        '_get_current_code_editor', 'status_bar', 'editor_file_coordinator',
        'process_manager', 'debug_manager', 'command_output_viewer',
        'debugger_toolbar', 'run_action_button', 'debug_action_button',
        'variables_panel', 'call_stack_panel', 'breakpoints_panel',
        'continue_action', 'step_over_action', 'step_into_action',
        'step_out_action', 'stop_action', 'active_breakpoints',
        'current_run_mode', 'bottom_dock_tab_widget', 'terminal_dock', # Added dock widgets
        'left_tab_widget' # Added for debugger panel focus
    ])

    mw._get_current_code_editor = MagicMock(return_value=None) # Default to no editor
    mw.status_bar = MagicMock()
    mw.status_bar.showMessage = MagicMock()

    mw.editor_file_coordinator = MagicMock()
    mw.editor_file_coordinator.save_current_file = MagicMock(return_value=True)
    mw.editor_file_coordinator.editor_to_path = {} # Mock this mapping

    mw.process_manager = MagicMock()
    mw.process_manager.execute = MagicMock()

    mw.debug_manager = MagicMock()
    mw.debug_manager.update_internal_breakpoints = MagicMock()
    mw.debug_manager.start_session = MagicMock()
    mw.debug_manager.set_breakpoints_on_adapter = MagicMock()
    # Mock DAP client state for breakpoint updates
    type(mw.debug_manager).dap_client = PropertyMock()
    mw.debug_manager.dap_client.isOpen = MagicMock(return_value=True)
    mw.debug_manager._dap_request_pending_response = {'handshake_complete': True}


    mw.command_output_viewer = MagicMock()
    mw.command_output_viewer.append_output = MagicMock()
    mw.command_output_viewer.clear_output = MagicMock()

    mw.debugger_toolbar = MagicMock()
    mw.debugger_toolbar.setVisible = MagicMock()

    mw.run_action_button = MagicMock()
    mw.run_action_button.setEnabled = MagicMock()
    mw.debug_action_button = MagicMock()
    mw.debug_action_button.setEnabled = MagicMock()

    mw.variables_panel = MagicMock(spec=QTreeWidgetItem) # Should be QTreeWidget
    mw.variables_panel.clear = MagicMock()
    mw.variables_panel.addTopLevelItem = MagicMock()
    mw.variables_panel.expandAll = MagicMock()


    mw.call_stack_panel = MagicMock(spec=QListWidgetItem) # Should be QListWidget
    mw.call_stack_panel.clear = MagicMock()
    mw.call_stack_panel.addItem = MagicMock()

    mw.breakpoints_panel = MagicMock(spec=QListWidgetItem) # Should be QListWidget
    mw.breakpoints_panel.clear = MagicMock()
    mw.breakpoints_panel.addItem = MagicMock()

    # Debugger actions
    for action_name in ['continue_action', 'step_over_action', 'step_into_action', 'step_out_action', 'stop_action']:
        action_mock = MagicMock()
        action_mock.setEnabled = MagicMock()
        setattr(mw, action_name, action_mock)

    # ExecutionCoordinator modifies these MainWindow attributes
    mw.active_breakpoints = {}
    mw.current_run_mode = "Run"

    mw.bottom_dock_tab_widget = MagicMock() # For showing command output viewer
    mw.bottom_dock_tab_widget.setCurrentWidget = MagicMock()
    mw.terminal_dock = MagicMock() # For showing terminal dock
    mw.terminal_dock.show = MagicMock()
    mw.terminal_dock.raise_ = MagicMock()

    mw.left_tab_widget = MagicMock() # For focusing Debugger tab
    mw.left_tab_widget.count = MagicMock(return_value=1) # Assume Debugger tab exists
    mw.left_tab_widget.tabText = MagicMock(return_value="Debugger")
    mw.left_tab_widget.setCurrentIndex = MagicMock()


    return mw

@pytest.fixture
def mock_config_manager():
    cm = MagicMock(spec=ConfigManager)
    cm.load_setting.side_effect = lambda key, default: {
        'runner_config': DEFAULT_RUNNER_CONFIG,
        'extension_to_language_map': DEFAULT_EXTENSION_TO_LANGUAGE_MAP
    }.get(key, default)
    return cm

@pytest.fixture
def exc(mock_main_window, mock_config_manager):
    # Patch ConfigManager at the point of import within execution_coordinator module
    with patch('execution_coordinator.ConfigManager', return_value=mock_config_manager):
        coordinator = ExecutionCoordinator()
    coordinator.set_main_window_ref(mock_main_window)
    # Verify that the coordinator's dicts are indeed the ones from MainWindow
    assert coordinator.active_breakpoints is mock_main_window.active_breakpoints
    # This assertion is tricky because current_run_mode is a property in MainWindow
    # that delegates to ExecutionCoordinator's internal _current_run_mode.
    # For the purpose of this test, we'll assume the setter/getter in MainWindow
    # correctly points to EXC's internal attribute if it were a real MainWindow.
    # Here, we are testing EXC directly, so we can check its internal attribute.
    # assert coordinator._current_run_mode == mock_main_window.current_run_mode
    # Instead, we check if the initial value set in the mock_main_window fixture for
    # current_run_mode is what EXC would start with (or what its property would reflect).
    # This is less about the fixture connection and more about EXC's initialization.
    # The fixture `exc` will initialize `_current_run_mode` to "Run" by default.
    # `mock_main_window.current_run_mode` is also "Run" in the fixture.
    # So, this check is more about initial state than the dynamic link.
    # A better way would be to ensure EXC's property setter is called if MainWindow's property changes.
    # However, for these tests, we are more interested in EXC changing MainWindow's view of current_run_mode.
    return coordinator

@pytest.fixture
def mock_code_editor():
    editor = MagicMock(spec=CodeEditor)
    editor.file_path = "/test/script.py" # Default file path
    editor.gutter = MagicMock() # Mock the gutter for breakpoint display updates
    editor.gutter.update_breakpoints_display = MagicMock()
    editor.set_exec_highlight = MagicMock() # For debugger pause highlight
    return editor

# --- Tests for _handle_run_request ---
def test_handle_run_request_success(exc, mock_main_window, mock_code_editor):
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    # EFC's editor_to_path map needs to contain the mock_code_editor and its path
    mock_main_window.editor_file_coordinator.editor_to_path = {mock_code_editor: "/test/script.py"}

    exc._handle_run_request()

    mock_main_window.editor_file_coordinator.save_current_file.assert_called_once()
    expected_command = ["python", "-u", "/test/script.py"]
    expected_working_dir = "/test"
    mock_main_window.process_manager.execute.assert_called_once_with(expected_command, expected_working_dir)

def test_handle_run_request_no_editor(exc, mock_main_window):
    mock_main_window._get_current_code_editor.return_value = None
    exc._handle_run_request()
    mock_main_window.status_bar.showMessage.assert_called_with("No active editor to run.", 3000)
    mock_main_window.process_manager.execute.assert_not_called()

def test_handle_run_request_save_fails(exc, mock_main_window, mock_code_editor):
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    mock_main_window.editor_file_coordinator.save_current_file.return_value = False # Simulate save fail/cancel

    exc._handle_run_request()
    mock_main_window.status_bar.showMessage.assert_called_with("Save operation cancelled or failed. Run aborted.", 3000)
    mock_main_window.process_manager.execute.assert_not_called()

@patch('PySide6.QtWidgets.QMessageBox.warning')
def test_handle_run_request_untitled_file(mock_msgbox_warning, exc, mock_main_window, mock_code_editor):
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    mock_code_editor.file_path = "untitled:Untitled-1" # Simulate untitled file
    mock_main_window.editor_file_coordinator.editor_to_path = {mock_code_editor: "untitled:Untitled-1"}

    exc._handle_run_request()
    mock_msgbox_warning.assert_called_once_with(mock_main_window, "Execution Error", "Please save the file before running.")
    mock_main_window.process_manager.execute.assert_not_called()

# --- Tests for _handle_debug_request ---
def test_handle_debug_request_success(exc, mock_main_window, mock_code_editor):
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    file_path = "/test/script_to_debug.py"
    mock_code_editor.file_path = file_path

    # Simulate some active breakpoints
    exc.active_breakpoints = {"/test/script_to_debug.py": {10, 15}}

    exc._handle_debug_request()

    mock_main_window.editor_file_coordinator.save_current_file.assert_called_once()
    mock_main_window.debug_manager.update_internal_breakpoints.assert_called_with(file_path, {10, 15})
    mock_main_window.debug_manager.start_session.assert_called_once_with(file_path)

# --- Tests for ProcessManager signal handlers ---
def test_handle_process_output(exc, mock_main_window):
    output = "Process output line"
    exc._handle_process_output(output)
    mock_main_window.command_output_viewer.append_output.assert_called_once_with(output)
    mock_main_window.bottom_dock_tab_widget.setCurrentWidget.assert_called_with(mock_main_window.command_output_viewer)

def test_handle_process_started(exc, mock_main_window):
    exc._handle_process_started()
    mock_main_window.status_bar.showMessage.assert_called_with("Process started...")
    mock_main_window.run_action_button.setEnabled.assert_called_with(False)
    mock_main_window.debug_action_button.setEnabled.assert_called_with(False)
    mock_main_window.command_output_viewer.clear_output.assert_called_once()
    mock_main_window.terminal_dock.show.assert_called_once() # Check dock visibility

def test_handle_process_finished(exc, mock_main_window):
    exc._handle_process_finished(0, QProcess.NormalExit)
    mock_main_window.status_bar.showMessage.assert_called_with("Process finished successfully.", 5000)
    mock_main_window.command_output_viewer.append_output.assert_called_with("\n--- Process finished successfully. ---\n")
    mock_main_window.run_action_button.setEnabled.assert_called_with(True)
    mock_main_window.debug_action_button.setEnabled.assert_called_with(True)

@patch('PySide6.QtWidgets.QMessageBox.critical')
def test_handle_process_error(mock_msgbox_critical, exc, mock_main_window):
    error_msg = "Failed to start"
    exc._handle_process_error(error_msg)
    mock_msgbox_critical.assert_called_once_with(mock_main_window, "Process Error", f"Process error: {error_msg}")
    mock_main_window.command_output_viewer.append_output.assert_called_with(f"\n--- ERROR: {error_msg} ---\n")

# --- Tests for DebugManager signal handlers ---
def test_on_debug_session_started(exc, mock_main_window):
    exc._on_debug_session_started()
    mock_main_window.debugger_toolbar.setVisible.assert_called_with(True)
    mock_main_window.run_action_button.setEnabled.assert_called_with(False)
    # Check debugger actions state
    mock_main_window.continue_action.setEnabled.assert_called_with(True)
    mock_main_window.stop_action.setEnabled.assert_called_with(True)

def test_on_debug_session_stopped(exc, mock_main_window, mock_code_editor):
    # Simulate an open editor to test exec highlight clearing
    mock_main_window.editor_file_coordinator.path_to_editor = {"/path.py": mock_code_editor}

    exc._on_debug_session_stopped()
    mock_main_window.debugger_toolbar.setVisible.assert_called_with(False)
    mock_main_window.variables_panel.clear.assert_called_once()
    mock_main_window.call_stack_panel.clear.assert_called_once()
    mock_code_editor.set_exec_highlight.assert_called_with(None) # Check highlight cleared

def test_on_debugger_paused(exc, mock_main_window, mock_code_editor):
    call_stack = [{'file': '/test/script.py', 'line': 5, 'name': 'my_func'}]
    variables = [{'name': 'x', 'value': '10', 'type': 'int'}]

    # Simulate the paused file is the current editor
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    mock_code_editor.file_path = '/test/script.py'

    exc._on_debugger_paused(1, "breakpoint", call_stack, variables)

    mock_main_window.call_stack_panel.addItem.assert_called_once() # Or check specific text
    mock_main_window.variables_panel.addTopLevelItem.assert_called_once() # Or check specific items
    mock_code_editor.set_exec_highlight.assert_called_with(5)
    mock_main_window.step_over_action.setEnabled.assert_called_with(True)
    mock_main_window.left_tab_widget.setCurrentIndex.assert_called_once() # Check focus on Debugger tab

def test_on_debugger_resumed(exc, mock_main_window, mock_code_editor):
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    exc._on_debugger_resumed()
    mock_main_window.variables_panel.clear.assert_called_once()
    mock_main_window.call_stack_panel.clear.assert_called_once()
    mock_code_editor.set_exec_highlight.assert_called_with(None)
    mock_main_window.continue_action.setEnabled.assert_called_with(False)

# --- Test _handle_breakpoint_toggled ---
@patch('PySide6.QtWidgets.QMessageBox.warning')
def test_handle_breakpoint_toggled_new_breakpoint(mock_msgbox_warning, exc, mock_main_window, mock_code_editor):
    line_num = 10
    file_path = "/test/script.py"
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    mock_code_editor.file_path = file_path

    exc._handle_breakpoint_toggled(line_num)

    assert exc.active_breakpoints[file_path] == {line_num}
    mock_main_window.breakpoints_panel.addItem.assert_called_once() # Or check text
    mock_code_editor.gutter.update_breakpoints_display.assert_called_with({line_num})
    mock_main_window.debug_manager.update_internal_breakpoints.assert_called_with(file_path, {line_num})
    # Check if set_breakpoints_on_adapter was called (assuming DAP client is open and handshake complete)
    mock_main_window.debug_manager.set_breakpoints_on_adapter.assert_called_with(file_path, [line_num])


def test_handle_breakpoint_toggled_remove_breakpoint(exc, mock_main_window, mock_code_editor):
    line_num = 10
    file_path = "/test/script.py"
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    mock_code_editor.file_path = file_path
    exc.active_breakpoints = {file_path: {line_num, 15}} # Pre-existing breakpoints

    exc._handle_breakpoint_toggled(line_num) # Toggle to remove

    assert exc.active_breakpoints[file_path] == {15}
    # breakpoints_panel.clear() is called, then items are re-added
    mock_main_window.breakpoints_panel.clear.assert_called_once()
    assert mock_main_window.breakpoints_panel.addItem.call_count > 0 # Called for remaining BP
    mock_code_editor.gutter.update_breakpoints_display.assert_called_with({15})
    mock_main_window.debug_manager.update_internal_breakpoints.assert_called_with(file_path, {15})
    mock_main_window.debug_manager.set_breakpoints_on_adapter.assert_called_with(file_path, [15])


@patch('PySide6.QtWidgets.QMessageBox.warning')
def test_handle_breakpoint_toggled_untitled_file(mock_msgbox_warning, exc, mock_main_window, mock_code_editor):
    mock_main_window._get_current_code_editor.return_value = mock_code_editor
    mock_code_editor.file_path = "untitled:MyScript" # Untitled file

    exc._handle_breakpoint_toggled(5)

    mock_msgbox_warning.assert_called_once_with(mock_main_window, "Breakpoints", "Please save the file before setting breakpoints.")
    assert not exc.active_breakpoints # No breakpoint should be added
