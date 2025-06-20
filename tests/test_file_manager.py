import os
import pytest
from unittest.mock import patch, mock_open, MagicMock, call

from PySide6.QtCore import QObject, Signal

# Adjust the import path according to your project structure
# This assumes file_manager.py is at the root of the project.
# If it's in a sub-directory like 'src', it would be 'src.file_manager'
from file_manager import FileManager

# Helper to quickly check if a signal was emitted with specific arguments
def assert_signal_emitted(signal_mock, *args, **kwargs):
    if args and kwargs:
        signal_mock.emit.assert_any_call(*args, **kwargs)
    elif args:
        signal_mock.emit.assert_any_call(*args)
    elif kwargs:
        # This case is a bit tricky as emit might be called with other positional args
        # For simplicity, we'll check if any call contains all kwargs.
        # A more robust check might be needed depending on exact signal usage.
        found = False
        for call_args in signal_mock.emit.call_args_list:
            if all(item in call_args.kwargs.items() for item in kwargs.items()):
                found = True
                break
        assert found, f"Signal not emitted with kwargs {kwargs}. Calls: {signal_mock.emit.call_args_list}"
    else: # Just check if emitted at all
        signal_mock.emit.assert_called()


@pytest.fixture
def file_manager():
    fm = FileManager()
    # Mock all signals for easy assertion
    fm.file_opened = MagicMock(spec=Signal)
    fm.file_saved = MagicMock(spec=Signal)
    fm.file_open_error = MagicMock(spec=Signal)
    fm.file_save_error = MagicMock(spec=Signal)
    fm.dirty_status_changed = MagicMock(spec=Signal)
    return fm

# --- Tests for open_file ---

def test_open_file_success(file_manager):
    path = "test_dir/test_file.txt"
    content = "Hello, world!"

    with patch("os.path.exists", return_value=True),          patch("os.path.isfile", return_value=True),          patch("builtins.open", mock_open(read_data=content)) as mock_file:

        file_manager.open_file(path)

    mock_file.assert_called_once_with(path, 'r', encoding='utf-8')
    assert_signal_emitted(file_manager.file_opened, path, content)
    assert path in file_manager.open_files_data
    assert not file_manager.open_files_data[path]["is_dirty"]
    assert file_manager.open_files_data[path]["content_hash"] == hash(content)

def test_open_file_not_found(file_manager):
    path = "non_existent_file.txt"
    with patch("os.path.exists", return_value=False):
        file_manager.open_file(path)

    assert_signal_emitted(file_manager.file_open_error, path, f"File not found: {path}")
    assert path not in file_manager.open_files_data

def test_open_file_is_not_file(file_manager):
    path = "actually_a_dir"
    with patch("os.path.exists", return_value=True),          patch("os.path.isfile", return_value=False):
        file_manager.open_file(path)

    assert_signal_emitted(file_manager.file_open_error, path, f"Path is not a file: {path}")
    assert path not in file_manager.open_files_data

def test_open_file_empty_path(file_manager):
    file_manager.open_file("")
    assert_signal_emitted(file_manager.file_open_error, "", "File path is empty.")

def test_open_file_read_error(file_manager):
    path = "file_with_read_error.txt"
    with patch("os.path.exists", return_value=True),          patch("os.path.isfile", return_value=True),          patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = IOError("Read permission denied")
        file_manager.open_file(path)

    assert_signal_emitted(file_manager.file_open_error, path, f"Could not open file {path}: Read permission denied")
    assert path not in file_manager.open_files_data

# --- Tests for save_file ---

def test_save_file_success_new_file(file_manager):
    widget_ref = QObject() # Mock widget reference
    path = "new_dir/new_file.txt"
    content = "Saving new content."

    # Assume file doesn't exist initially, so no entry in open_files_data
    assert path not in file_manager.open_files_data

    with patch("os.makedirs") as mock_makedirs,          patch("builtins.open", mock_open()) as mock_file:

        file_manager.save_file(widget_ref, content, path)

    mock_makedirs.assert_called_once_with(os.path.dirname(path), exist_ok=True)
    mock_file.assert_called_once_with(path, 'w', encoding='utf-8')
    mock_file().write.assert_called_once_with(content)

    assert_signal_emitted(file_manager.file_saved, widget_ref, path, content)
    assert path in file_manager.open_files_data
    assert not file_manager.open_files_data[path]["is_dirty"]
    assert file_manager.open_files_data[path]["content_hash"] == hash(content)
    # Since it was a new file, dirty_status_changed should not be called unless it was marked dirty before save
    # For a brand new save, the initial state is considered clean after save.
    file_manager.dirty_status_changed.emit.assert_not_called()


def test_save_file_success_existing_file_becomes_clean(file_manager):
    widget_ref = QObject()
    path = "existing_file.txt"
    original_content = "Original content"
    new_content = "Updated content"

    # Simulate file was opened and then dirtied
    file_manager.open_files_data[path] = {"is_dirty": True, "content_hash": hash(original_content)}

    with patch("os.makedirs"),          patch("builtins.open", mock_open()) as mock_file:
        file_manager.save_file(widget_ref, new_content, path)

    mock_file.assert_called_once_with(path, 'w', encoding='utf-8')
    mock_file().write.assert_called_once_with(new_content)

    assert_signal_emitted(file_manager.file_saved, widget_ref, path, new_content)
    assert path in file_manager.open_files_data
    assert not file_manager.open_files_data[path]["is_dirty"]
    assert file_manager.open_files_data[path]["content_hash"] == hash(new_content)
    assert_signal_emitted(file_manager.dirty_status_changed, path, False)


def test_save_file_empty_path(file_manager):
    widget_ref = QObject()
    content = "Some content"
    file_manager.save_file(widget_ref, content, "")
    assert_signal_emitted(file_manager.file_save_error, widget_ref, "", "File path cannot be None for saving.")

def test_save_file_makedirs_error(file_manager):
    widget_ref = QObject()
    path = "uncreatable_dir/file.txt"
    content = "Some content"

    with patch("os.makedirs", side_effect=OSError("Permission denied")) as mock_makedirs,          patch("builtins.open", mock_open()): # mock_open to prevent actual file IO
        file_manager.save_file(widget_ref, content, path)

    mock_makedirs.assert_called_once_with(os.path.dirname(path), exist_ok=True)
    assert_signal_emitted(file_manager.file_save_error, widget_ref, path, f"Could not save file {path}: Permission denied")

def test_save_file_write_error(file_manager):
    widget_ref = QObject()
    path = "test_file.txt"
    content = "Some content"

    with patch("os.makedirs"),          patch("builtins.open", mock_open()) as mock_file:
        mock_file().write.side_effect = IOError("Disk full")
        file_manager.save_file(widget_ref, content, path)

    assert_signal_emitted(file_manager.file_save_error, widget_ref, path, f"Could not save file {path}: Disk full")

# --- Tests for update_file_content_changed ---

def test_update_file_content_changed_becomes_dirty(file_manager):
    path = "tracked_file.txt"
    original_content = "Original"
    new_content = "Changed"

    # Simulate file is open and clean
    file_manager.open_files_data[path] = {"is_dirty": False, "content_hash": hash(original_content)}

    file_manager.update_file_content_changed(path, new_content)

    assert file_manager.open_files_data[path]["is_dirty"]
    assert_signal_emitted(file_manager.dirty_status_changed, path, True)

def test_update_file_content_changed_becomes_clean(file_manager):
    path = "tracked_file.txt"
    original_content = "Original"
    # Simulate file is open and dirty, but content matches original saved hash
    file_manager.open_files_data[path] = {"is_dirty": True, "content_hash": hash(original_content)}

    file_manager.update_file_content_changed(path, original_content) # Content changed back

    assert not file_manager.open_files_data[path]["is_dirty"]
    assert_signal_emitted(file_manager.dirty_status_changed, path, False)

def test_update_file_content_no_change_in_dirtiness(file_manager):
    path = "tracked_file.txt"
    original_content = "Original"
    # Simulate file is open and already dirty
    file_manager.open_files_data[path] = {"is_dirty": True, "content_hash": hash(original_content)}

    file_manager.update_file_content_changed(path, "Some other different content") # Still dirty

    assert file_manager.open_files_data[path]["is_dirty"] # Remains dirty
    file_manager.dirty_status_changed.emit.assert_not_called() # Signal not emitted if dirty state doesn't change

def test_update_file_content_non_tracked_file(file_manager):
    path = "untracked_file.txt"
    original_open_files_data = file_manager.open_files_data.copy()

    file_manager.update_file_content_changed(path, "some content")

    assert file_manager.open_files_data == original_open_files_data
    file_manager.dirty_status_changed.emit.assert_not_called()

# --- Tests for get_dirty_state ---

def test_get_dirty_state(file_manager):
    dirty_path = "dirty.txt"
    clean_path = "clean.txt"
    untracked_path = "untracked.txt"

    file_manager.open_files_data[dirty_path] = {"is_dirty": True, "content_hash": 123}
    file_manager.open_files_data[clean_path] = {"is_dirty": False, "content_hash": 456}

    assert file_manager.get_dirty_state(dirty_path)
    assert not file_manager.get_dirty_state(clean_path)
    assert not file_manager.get_dirty_state(untracked_path)

# --- Tests for file_closed_in_editor ---

def test_file_closed_in_editor_tracked(file_manager):
    path = "to_be_closed.txt"
    file_manager.open_files_data[path] = {"is_dirty": False, "content_hash": 0}

    file_manager.file_closed_in_editor(path)
    assert path not in file_manager.open_files_data

def test_file_closed_in_editor_untracked(file_manager):
    path = "never_opened.txt"
    original_data_len = len(file_manager.open_files_data)

    file_manager.file_closed_in_editor(path)
    assert len(file_manager.open_files_data) == original_data_len

# --- Tests for get_all_open_files_data ---

def test_get_all_open_files_data(file_manager):
    data = {"file1": {"is_dirty": True, "content_hash": 1}}
    file_manager.open_files_data = data.copy() # Set internal state
    assert file_manager.get_all_open_files_data() == data

# --- Tests for load_open_files_data ---

def test_load_open_files_data(file_manager):
    data_to_load = {"file1.txt": {"is_dirty": False, "content_hash": hash("abc")}}
    file_manager.load_open_files_data(data_to_load.copy()) # Load a copy
    assert file_manager.open_files_data == data_to_load

# --- Tests for rename_path_tracking ---

def test_rename_path_tracking_tracked_file(file_manager):
    old_path = "old_name.txt"
    new_path = "new_name.txt"
    file_data = {"is_dirty": False, "content_hash": hash("content")}
    file_manager.open_files_data[old_path] = file_data.copy()

    file_manager.rename_path_tracking(old_path, new_path)

    assert old_path not in file_manager.open_files_data
    assert new_path in file_manager.open_files_data
    assert file_manager.open_files_data[new_path] == file_data

def test_rename_path_tracking_untracked_file(file_manager):
    old_path = "untracked_old.txt"
    new_path = "untracked_new.txt"
    original_data = file_manager.open_files_data.copy()

    file_manager.rename_path_tracking(old_path, new_path)

    assert file_manager.open_files_data == original_data

def test_save_file_no_dirname(file_manager):
    widget_ref = QObject()
    path = "file_in_current_dir.txt" # No directory part in path
    content = "Content for file in current directory"

    # Ensure os.makedirs is not called when path has no directory component
    with patch("os.makedirs") as mock_makedirs,          patch("builtins.open", mock_open()) as mock_file:
        file_manager.save_file(widget_ref, content, path)

    mock_makedirs.assert_not_called() # Crucial check
    mock_file.assert_called_once_with(path, 'w', encoding='utf-8')
    mock_file().write.assert_called_once_with(content)
    assert_signal_emitted(file_manager.file_saved, widget_ref, path, content)
