import pytest
from unittest.mock import MagicMock, patch, call

from PySide6.QtCore import QProcess, QByteArray, Signal

# Adjust import path as necessary
from process_manager import ProcessManager

# Helper for signal assertion (can be shared if in a conftest.py or common test utils)
def assert_signal_emitted(signal_mock, *args, **kwargs):
    if args and kwargs:
        signal_mock.emit.assert_any_call(*args, **kwargs)
    elif args:
        signal_mock.emit.assert_any_call(*args)
    elif kwargs:
        found = False
        for call_args in signal_mock.emit.call_args_list:
            # Ensure all provided kwargs are in the actual call's kwargs
            # and their values match.
            actual_kwargs = call_args.kwargs
            match = True
            for k, v in kwargs.items():
                if k not in actual_kwargs or actual_kwargs[k] != v:
                    match = False
                    break
            if match:
                found = True
                break
        assert found, f"Signal not emitted with kwargs {kwargs}. Calls: {signal_mock.emit.call_args_list}"
    else: # Just check if emitted at all
        signal_mock.emit.assert_called()


@pytest.fixture
def process_manager():
    pm = ProcessManager()
    # Mock signals
    pm.output_received = MagicMock(spec=Signal)
    pm.process_started = MagicMock(spec=Signal)
    pm.process_finished = MagicMock(spec=Signal)
    pm.process_error = MagicMock(spec=Signal)
    return pm

@pytest.fixture
def mock_qprocess():
    # Create a mock QProcess instance that can be further customized in tests
    # This allows tests to simulate QProcess signals being emitted.
    # We patch 'process_manager.QProcess' if ProcessManager creates its own QProcess instances
    # or pass a mock QProcess if it's injected. Assuming it creates its own:
    with patch('process_manager.QProcess') as MockQProcess:
        mock_instance = MockQProcess.return_value
        # Mock methods that ProcessManager calls
        mock_instance.setWorkingDirectory = MagicMock()
        mock_instance.setProgram = MagicMock()
        mock_instance.setArguments = MagicMock()
        mock_instance.start = MagicMock()
        mock_instance.terminate = MagicMock()
        mock_instance.kill = MagicMock()
        mock_instance.waitForFinished = MagicMock(return_value=True) # Default to finishing quickly
        mock_instance.state = MagicMock(return_value=QProcess.NotRunning)
        mock_instance.errorString = MagicMock(return_value="Mocked QProcess error")
        mock_instance.readAllStandardOutput = MagicMock(return_value=QByteArray())
        mock_instance.readAllStandardError = MagicMock(return_value=QByteArray())

        # Mock signals that ProcessManager connects to
        # These are attributes on the mock_instance that ProcessManager will connect to.
        # They need to be actual objects with a `connect` method.
        mock_instance.readyReadStandardOutput = MagicMock(spec=Signal)
        mock_instance.readyReadStandardError = MagicMock(spec=Signal)
        mock_instance.finished = MagicMock(spec=Signal) # (int, QProcess.ExitStatus)
        mock_instance.errorOccurred = MagicMock(spec=Signal) # (QProcess.ProcessError)
        mock_instance.started = MagicMock(spec=Signal)

        yield mock_instance # The mock QProcess *instance*

# --- Tests for execute ---

def test_execute_success(process_manager, mock_qprocess):
    command_parts = ["echo", "Hello"]
    working_dir = "/tmp"

    # Simulate QProcess.findExecutable finding the program
    with patch("PySide6.QtCore.QProcess.findExecutable", return_value="echo"):
        process_manager.execute(command_parts, working_dir)

    mock_qprocess.setWorkingDirectory.assert_called_once_with(working_dir)
    mock_qprocess.setProgram.assert_called_once_with("echo")
    mock_qprocess.setArguments.assert_called_once_with(["Hello"])
    mock_qprocess.start.assert_called_once()

    # To test process_started signal, we need to simulate QProcess emitting its 'started' signal
    # This is typically done by capturing the connected slot and calling it,
    # or by having the mock_qprocess.started object itself be a mock that we can assert was connected.
    # For simplicity here, we'll assume the connection happens and ProcessManager would emit if QProcess did.
    # A more rigorous test would involve pm.process.started.connect(pm.process_started.emit)
    # and then mock_qprocess.started.emit()

    # Simulate the QProcess 'started' signal being connected and then emitted
    # This requires that the mock_qprocess.started object is the one ProcessManager connects to.
    # The ProcessManager connects its own self.process_started slot to the QProcess's started signal.
    # So, we check if the QProcess's started signal was connected.
    mock_qprocess.started.connect.assert_called_with(process_manager.process_started)
    # If we want to test the emission path, we'd need to call the slot that QProcess's started signal is connected to.
    # For now, let's assume if QProcess.start() is called, and if it were a real QProcess that started,
    # the signal chain would work.
    # process_manager.process_started.emit.assert_called_once() # This would be if PM directly emits without QProcess signal

def test_execute_process_already_running(process_manager, mock_qprocess):
    # Simulate process is running
    process_manager.process = mock_qprocess # Assign a mock process
    mock_qprocess.state.return_value = QProcess.Running

    process_manager.execute(["echo", "First"], "/tmp") # This call should make it "running"

    # Now try to execute another while the first is (simulated as) running
    process_manager.execute(["echo", "Second"], "/tmp")

    assert_signal_emitted(process_manager.process_error, "A process is already running.")
    # Ensure the second process's start was not attempted
    assert mock_qprocess.start.call_count == 1 # Only the first call to execute should attempt start

def test_execute_empty_command(process_manager):
    process_manager.execute([], "/tmp")
    assert_signal_emitted(process_manager.process_error, "Command cannot be empty.")

@patch("PySide6.QtCore.QProcess.findExecutable", return_value=None) # Executable not found by QProcess
@patch("os.path.isfile", return_value=False) # Also not a direct file path
def test_execute_executable_not_found(mock_os_isfile, mock_find_exec, process_manager, mock_qprocess):
    process_manager.execute(["nonexistent_command"], "/tmp")
    assert_signal_emitted(process_manager.process_error, "Executable 'nonexistent_command' not found or not executable.")
    mock_qprocess.start.assert_not_called()

# --- Tests for output handling ---

def test_handle_stdout(process_manager, mock_qprocess):
    process_manager.process = mock_qprocess # Assign the active process
    output_text = "Standard output line"
    mock_qprocess.readAllStandardOutput.return_value = QByteArray(output_text.encode())

    # Simulate the readyReadStandardOutput signal being emitted by QProcess
    # This requires finding the slot connected to mock_qprocess.readyReadStandardOutput
    # and calling it.
    # For simplicity, we directly call the handler method.
    process_manager._handle_stdout()

    assert_signal_emitted(process_manager.output_received, output_text)

def test_handle_stderr(process_manager, mock_qprocess):
    process_manager.process = mock_qprocess
    error_text = "Error output line"
    mock_qprocess.readAllStandardError.return_value = QByteArray(error_text.encode())

    process_manager._handle_stderr()

    assert_signal_emitted(process_manager.output_received, error_text)

# --- Tests for process finishing ---

def test_handle_finished(process_manager, mock_qprocess):
    process_manager.process = mock_qprocess
    exit_code = 0
    exit_status = QProcess.NormalExit

    process_manager._handle_finished(exit_code, exit_status)

    assert_signal_emitted(process_manager.process_finished, exit_code, exit_status)
    assert process_manager.process is None # Process should be cleared

# --- Tests for process error ---

def test_handle_error_occurred(process_manager, mock_qprocess):
    process_manager.process = mock_qprocess
    process_error = QProcess.FailedToStart
    mock_qprocess.errorString.return_value = "Failed to start" # QProcess provides this

    process_manager._handle_error_occurred(process_error)

    assert_signal_emitted(process_manager.process_error, "Failed to start")
    assert process_manager.process is None # Process should be cleared

# --- Tests for is_running ---

def test_is_running(process_manager, mock_qprocess):
    assert not process_manager.is_running() # Initially not running

    process_manager.process = mock_qprocess
    mock_qprocess.state.return_value = QProcess.Running
    assert process_manager.is_running()

    mock_qprocess.state.return_value = QProcess.NotRunning
    assert not process_manager.is_running()

    process_manager.process = None
    assert not process_manager.is_running()

# --- Tests for kill_process ---

def test_kill_process_when_running(process_manager, mock_qprocess):
    process_manager.process = mock_qprocess
    mock_qprocess.state.return_value = QProcess.Running
    # Simulate waitForFinished returns False (process didn't terminate quickly)
    mock_qprocess.waitForFinished.return_value = False

    process_manager.kill_process()

    mock_qprocess.terminate.assert_called_once()
    mock_qprocess.waitForFinished.assert_called_once_with(1000)
    mock_qprocess.kill.assert_called_once()

def test_kill_process_when_running_terminates_quickly(process_manager, mock_qprocess):
    process_manager.process = mock_qprocess
    mock_qprocess.state.return_value = QProcess.Running
    mock_qprocess.waitForFinished.return_value = True # Terminates quickly

    process_manager.kill_process()

    mock_qprocess.terminate.assert_called_once()
    mock_qprocess.waitForFinished.assert_called_once_with(1000)
    mock_qprocess.kill.assert_not_called() # Should not be called if terminate worked

def test_kill_process_not_running(process_manager, mock_qprocess):
    process_manager.process = mock_qprocess
    mock_qprocess.state.return_value = QProcess.NotRunning # Simulate not running

    process_manager.kill_process()

    mock_qprocess.terminate.assert_not_called()
    mock_qprocess.kill.assert_not_called()

def test_execute_findexecutable_is_file_and_executable(process_manager, mock_qprocess):
    command_parts = ["./local_script.sh", "arg"]
    working_dir = "/some/path"

    # Simulate QProcess.findExecutable fails, but os.path.isfile and os.access succeed
    with patch("PySide6.QtCore.QProcess.findExecutable", return_value=None),          patch("os.path.isfile", return_value=True),          patch("os.access", return_value=True):
        process_manager.execute(command_parts, working_dir)

    mock_qprocess.setProgram.assert_called_once_with("./local_script.sh")
    mock_qprocess.setArguments.assert_called_once_with(["arg"])
    mock_qprocess.start.assert_called_once()
