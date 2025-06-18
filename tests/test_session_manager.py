import os
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock, call

from PySide6.QtCore import QStandardPaths, Signal

# Adjust import path as necessary
from session_manager import SessionManager

# Helper to quickly check if a signal was emitted with specific arguments
def assert_signal_emitted(signal_mock, *args, **kwargs):
    if args and kwargs:
        signal_mock.emit.assert_any_call(*args, **kwargs)
    elif args:
        signal_mock.emit.assert_any_call(*args)
    elif kwargs:
        found = False
        for call_args in signal_mock.emit.call_args_list:
            if all(item in call_args.kwargs.items() for item in kwargs.items()):
                found = True
                break
        assert found, f"Signal not emitted with kwargs {kwargs}. Calls: {signal_mock.emit.call_args_list}"
    else:
        signal_mock.emit.assert_called()

@pytest.fixture
def session_manager():
    sm = SessionManager()
    # Mock signals
    sm.session_error = MagicMock(spec=Signal)
    sm.session_loaded = MagicMock(spec=Signal)
    sm.session_saved = MagicMock(spec=Signal)
    return sm

@pytest.fixture
def mock_qstandardpaths():
    with patch("PySide6.QtCore.QStandardPaths.writableLocation") as mock_writable_location:
        mock_writable_location.return_value = "/fake/config/dir"
        yield mock_writable_location

# --- Tests for _get_session_file_path ---

def test_get_session_file_path(session_manager, mock_qstandardpaths):
    expected_app_config_dir = "/fake/config/dir"
    expected_session_dir = os.path.join(expected_app_config_dir, ".aether_editor")
    expected_path = os.path.join(expected_session_dir, "session.json")

    with patch("os.makedirs") as mock_makedirs:
        actual_path = session_manager._get_session_file_path()

    mock_qstandardpaths.assert_called_once_with(QStandardPaths.AppConfigLocation)
    mock_makedirs.assert_called_once_with(expected_session_dir, exist_ok=True)
    assert actual_path == expected_path

# --- Tests for save_session ---

def test_save_session_success(session_manager, mock_qstandardpaths):
    open_files_data = {"file1.py": {"is_dirty": False, "content_hash": 123}}
    recent_projects = ["/proj1", "/proj2"]
    root_path = "/proj1"
    active_file_path = "/proj1/file1.py"

    expected_session_data = {
        "open_files_data": open_files_data,
        "recent_projects": recent_projects,
        "root_path": root_path,
        "active_file_path": active_file_path
    }

    with patch("os.makedirs"),          patch("builtins.open", mock_open()) as mock_file,          patch("json.dump") as mock_json_dump:

        session_manager.save_session(open_files_data, recent_projects, root_path, active_file_path)

    session_file_path = session_manager._get_session_file_path() # Path it would try to use
    mock_file.assert_called_once_with(session_file_path, 'w', encoding='utf-8')
    mock_json_dump.assert_called_once_with(expected_session_data, mock_file(), indent=4)
    assert_signal_emitted(session_manager.session_saved)
    session_manager.session_error.emit.assert_not_called()


def test_save_session_io_error(session_manager, mock_qstandardpaths):
    with patch("os.makedirs"),          patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = IOError("Permission denied")
        session_manager.save_session({}, [], None, None)

    session_file_path = session_manager._get_session_file_path()
    assert_signal_emitted(session_manager.session_error, f"Error saving session to {session_file_path}: Permission denied")
    session_manager.session_saved.emit.assert_not_called()


def test_save_session_unexpected_error(session_manager, mock_qstandardpaths):
    with patch("os.makedirs"),          patch("builtins.open", mock_open()),          patch("json.dump", side_effect=TypeError("Unexpected type")) as mock_json_dump:
        session_manager.save_session({}, [], None, None)

    assert_signal_emitted(session_manager.session_error, "An unexpected error occurred while saving session: Unexpected type")
    session_manager.session_saved.emit.assert_not_called()

# --- Tests for load_session ---

DEFAULT_SESSION_DATA = {
    "open_files_data": {},
    "recent_projects": [],
    "root_path": None,
    "active_file_path": None
}

def test_load_session_success_file_exists(session_manager, mock_qstandardpaths):
    loaded_json_data = {
        "open_files_data": {"file.py": {"is_dirty": True, "content_hash": 456}},
        "recent_projects": ["/path/to/project"],
        "root_path": "/path/to/project",
        "active_file_path": "/path/to/project/file.py"
    }

    with patch("os.path.exists", return_value=True),          patch("builtins.open", mock_open(read_data=json.dumps(loaded_json_data))) as mock_file,          patch("json.load", return_value=loaded_json_data) as mock_json_load:

        loaded_data = session_manager.load_session()

    session_file_path = session_manager._get_session_file_path()
    mock_file.assert_called_once_with(session_file_path, 'r', encoding='utf-8')
    assert loaded_data == loaded_json_data
    assert_signal_emitted(session_manager.session_loaded, loaded_json_data)
    session_manager.session_error.emit.assert_not_called()

def test_load_session_file_not_found(session_manager, mock_qstandardpaths):
    with patch("os.path.exists", return_value=False):
        loaded_data = session_manager.load_session()

    assert loaded_data == DEFAULT_SESSION_DATA
    assert_signal_emitted(session_manager.session_loaded, DEFAULT_SESSION_DATA)
    session_manager.session_error.emit.assert_not_called() # Not an error for missing file

def test_load_session_json_decode_error(session_manager, mock_qstandardpaths):
    with patch("os.path.exists", return_value=True),          patch("builtins.open", mock_open(read_data="invalid json")),          patch("json.load", side_effect=json.JSONDecodeError("Error", "doc", 0)):

        loaded_data = session_manager.load_session()

    session_file_path = session_manager._get_session_file_path()
    assert loaded_data == DEFAULT_SESSION_DATA
    assert_signal_emitted(session_manager.session_error, f"Error decoding session file {session_file_path}: Error: line 1 column 1 (char 0). Using default session.")
    assert_signal_emitted(session_manager.session_loaded, DEFAULT_SESSION_DATA)


def test_load_session_unexpected_error(session_manager, mock_qstandardpaths):
    with patch("os.path.exists", return_value=True),          patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = Exception("Something went wrong")
        loaded_data = session_manager.load_session()

    assert loaded_data == DEFAULT_SESSION_DATA
    assert_signal_emitted(session_manager.session_error, "An unexpected error occurred while loading session: Something went wrong. Using default session.")
    assert_signal_emitted(session_manager.session_loaded, DEFAULT_SESSION_DATA)


def test_load_session_old_format_active_file_index(session_manager, mock_qstandardpaths):
    # Simulate a session file that has the old "active_file_index"
    # and no "active_file_path"
    old_format_data = {
        "open_files_data": {"file.py": {"is_dirty": False, "content_hash": 123}},
        "recent_projects": ["/project"],
        "root_path": "/project",
        "active_file_index": 0 # Old field
    }

    expected_loaded_data = {
        "open_files_data": {"file.py": {"is_dirty": False, "content_hash": 123}},
        "recent_projects": ["/project"],
        "root_path": "/project",
        "active_file_path": None # Should be added as None
    }

    with patch("os.path.exists", return_value=True),          patch("builtins.open", mock_open(read_data=json.dumps(old_format_data))),          patch("json.load", return_value=old_format_data): # json.load returns the dict as is

        loaded_data = session_manager.load_session()

    assert loaded_data == expected_loaded_data
    assert_signal_emitted(session_manager.session_loaded, expected_loaded_data)
    session_manager.session_error.emit.assert_not_called()

def test_load_session_new_format_with_active_file_path(session_manager, mock_qstandardpaths):
    # Ensure it correctly loads a session with the new "active_file_path"
    new_format_data = {
        "open_files_data": {"file.py": {"is_dirty": False, "content_hash": 123}},
        "recent_projects": ["/project"],
        "root_path": "/project",
        "active_file_path": "/project/file.py"
    }

    with patch("os.path.exists", return_value=True),          patch("builtins.open", mock_open(read_data=json.dumps(new_format_data))),          patch("json.load", return_value=new_format_data):

        loaded_data = session_manager.load_session()

    assert loaded_data == new_format_data
    assert_signal_emitted(session_manager.session_loaded, new_format_data)
    session_manager.session_error.emit.assert_not_called()
