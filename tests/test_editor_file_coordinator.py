import pytest
import os
from unittest.mock import MagicMock, patch, call, PropertyMock

from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox, QTextEdit, QLineEdit # Added QLineEdit
from PySide6.QtCore import Signal, Qt # Added Qt

# Adjust import path as necessary
from editor_file_coordinator import EditorFileCoordinator
from code_editor import CodeEditor # Assuming CodeEditor is needed for type checks

# Helper for signal assertion
def assert_signal_emitted(signal_mock, *args, **kwargs):
    # This is a simplified version. For more complex scenarios,
    # you might need to check call_args_list more thoroughly.
    if args and kwargs:
        signal_mock.emit.assert_any_call(*args, **kwargs)
    elif args:
        signal_mock.emit.assert_any_call(*args)
    elif kwargs:
        found = False
        for call_args_tuple in signal_mock.emit.call_args_list:
            actual_args, actual_kwargs = call_args_tuple
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
def mock_main_window():
    mw = MagicMock(spec=['tab_widget', 'file_manager', 'collaboration_service',
                         'status_bar', 'file_explorer', 'editor_file_coordinator',
                         'execution_coordinator', 'initialize_project',
                         'on_text_editor_changed', '_update_cursor_position_label',
                         '_update_language_label', '_update_status_bar_and_language_selector_on_tab_change',
                         'update_editor_read_only_state', '_update_undo_redo_actions',
                         '_handle_dirty_status_changed'])

    # Mock UI elements and services that EFC interacts with
    mw.tab_widget = MagicMock(spec=QWidget) # Using QWidget as a generic base for tab_widget
    mw.tab_widget.widget = MagicMock(return_value=MagicMock(spec=CodeEditor))
    mw.tab_widget.indexOf = MagicMock(return_value=0)
    mw.tab_widget.currentIndex = MagicMock(return_value=0)
    mw.tab_widget.addTab = MagicMock(return_value=0) # Returns new tab index
    mw.tab_widget.setTabText = MagicMock()
    mw.tab_widget.setTabToolTip = MagicMock()
    mw.tab_widget.tabText = MagicMock(return_value="filename.txt") # For dirty checking logic in EFC

    mw.file_manager = MagicMock()
    mw.file_manager.open_file = MagicMock()
    mw.file_manager.save_file = MagicMock()
    mw.file_manager.get_dirty_state = MagicMock(return_value=False)
    mw.file_manager.file_closed_in_editor = MagicMock()

    mw.collaboration_service = MagicMock()
    mw.collaboration_service.is_updating_from_network = False # Default state

    mw.status_bar = MagicMock()
    mw.status_bar.showMessage = MagicMock()

    mw.file_explorer = MagicMock()
    mw.file_explorer.refresh_tree = MagicMock()

    mw.execution_coordinator = MagicMock() # For breakpoint connections
    mw.execution_coordinator._handle_breakpoint_toggled = MagicMock()


    # EFC directly accesses these dictionaries from MainWindow
    # So, the mock MainWindow must also have them.
    mw.editor_to_path = {}
    mw.path_to_editor = {}

    return mw

@pytest.fixture
def efc(mock_main_window):
    coordinator = EditorFileCoordinator()
    coordinator.set_main_window_ref(mock_main_window) # Crucial step
    return coordinator

# --- Tests for _save_file ---

@patch('PySide6.QtWidgets.QFileDialog.getSaveFileName')
@patch('black.format_str')
def test_save_file_new_untitled(mock_format_str, mock_get_save_file_name, efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    mock_editor.toPlainText.return_value = "print('hello')"
    type(mock_editor).file_path = PropertyMock(return_value="untitled:Untitled-1") # Simulate untitled

    mock_main_window.tab_widget.widget.return_value = mock_editor
    efc.editor_to_path[mock_editor] = "untitled:Untitled-1" # Setup internal mapping
    efc.path_to_editor["untitled:Untitled-1"] = mock_editor

    mock_get_save_file_name.return_value = ("/path/to/new_file.py", "Python Files (*.py)")
    mock_format_str.return_value = "print('hello')" # No formatting change

    with patch('PySide6.QtCore.QStandardPaths.writableLocation', return_value="/fake/docs"):
        result = efc._save_file(index=0, save_as=False) # save_as=False, but untitled forces dialog

    assert result is True
    mock_get_save_file_name.assert_called_once()
    mock_main_window.file_manager.save_file.assert_called_once_with(mock_editor, "print('hello')", "/path/to/new_file.py")
    mock_format_str.assert_called_once_with("print('hello')", mode=mock_format_str.call_args[1]['mode']) # black.FileMode() is complex to mock directly

@patch('black.format_str')
def test_save_file_existing_py_with_formatting(mock_format_str, efc, mock_main_window):
    original_code = "print ('hello')"
    formatted_code = "print(\"hello\")\n" # Black adds newline by default
    mock_editor = MagicMock(spec=CodeEditor)
    mock_editor.toPlainText.return_value = original_code
    mock_editor.textCursor.return_value.position.return_value = 0 # For cursor restoration
    type(mock_editor).file_path = PropertyMock(return_value="/path/to/existing.py")

    mock_main_window.tab_widget.widget.return_value = mock_editor
    efc.editor_to_path[mock_editor] = "/path/to/existing.py"
    efc.path_to_editor["/path/to/existing.py"] = mock_editor

    mock_format_str.return_value = formatted_code

    result = efc._save_file(index=0, save_as=False)

    assert result is True
    mock_format_str.assert_called_once_with(original_code, mode=mock_format_str.call_args[1]['mode'])
    mock_editor.setPlainText.assert_called_once_with(formatted_code)
    mock_main_window.file_manager.save_file.assert_called_once_with(mock_editor, formatted_code, "/path/to/existing.py")

@patch('PySide6.QtWidgets.QFileDialog.getSaveFileName')
def test_save_file_cancelled_by_user(mock_get_save_file_name, efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    type(mock_editor).file_path = PropertyMock(return_value="untitled:Untitled-1")
    mock_main_window.tab_widget.widget.return_value = mock_editor
    efc.editor_to_path[mock_editor] = "untitled:Untitled-1"

    mock_get_save_file_name.return_value = ("", "") # User cancels dialog

    with patch('PySide6.QtCore.QStandardPaths.writableLocation', return_value="/fake/docs"):
        result = efc._save_file(index=0, save_as=True)

    assert result is False
    mock_main_window.status_bar.showMessage.assert_called_with("Save cancelled.", 3000)
    mock_main_window.file_manager.save_file.assert_not_called()

# --- Tests for _handle_file_saved ---

def test_handle_file_saved_new_name(efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    old_path = "untitled:Untitled-1"
    new_path = "/saved/file.py"

    # Simulate editor was initially untitled
    efc.editor_to_path[mock_editor] = old_path
    efc.path_to_editor[old_path] = mock_editor

    efc._handle_file_saved(mock_editor, new_path, "content")

    assert efc.editor_to_path[mock_editor] == new_path
    assert efc.path_to_editor[new_path] == mock_editor
    assert old_path not in efc.path_to_editor
    assert mock_editor.file_path == new_path # Check CodeEditor's internal path too
    mock_main_window.tab_widget.setTabText.assert_called_with(mock_main_window.tab_widget.indexOf.return_value, os.path.basename(new_path))
    mock_main_window.tab_widget.setTabToolTip.assert_called_with(mock_main_window.tab_widget.indexOf.return_value, new_path)
    mock_main_window.status_bar.showMessage.assert_called_with(f"File '{os.path.basename(new_path)}' saved.", 3000)
    mock_main_window.file_explorer.refresh_tree.assert_called_once()

# --- Tests for _handle_file_save_error ---
@patch('PySide6.QtWidgets.QMessageBox.critical')
def test_handle_file_save_error(mock_msgbox_critical, efc, mock_main_window):
    efc._handle_file_save_error(MagicMock(spec=CodeEditor), "/path/file.txt", "Disk full")
    mock_msgbox_critical.assert_called_once()
    mock_main_window.status_bar.showMessage.assert_called_with("Save error for /path/file.txt", 5000)

# --- Tests for open_file (action from menu) ---
@patch('PySide6.QtWidgets.QFileDialog.exec')
@patch('PySide6.QtWidgets.QFileDialog.selectedFiles')
def test_open_file_action_selects_file(mock_selected_files, mock_dialog_exec, efc, mock_main_window):
    mock_dialog_exec.return_value = True # User selected a file
    selected_path = "/path/to/opened_file.txt"
    mock_selected_files.return_value = [selected_path]

    # Mock open_new_tab as it's tested separately
    with patch.object(efc, 'open_new_tab') as mock_open_new_tab:
        efc.open_file()

    mock_main_window.initialize_project.assert_called_once_with(selected_path)
    mock_open_new_tab.assert_called_once_with(selected_path)

# --- Tests for open_new_tab ---

@patch('editor_file_coordinator.CodeEditor') # Patch where CodeEditor is imported in efc
def test_open_new_tab_new_file(MockCodeEditorClass, efc, mock_main_window):
    file_path = "/newly/opened.txt"
    mock_editor_instance = MockCodeEditorClass.return_value # Instance of mocked CodeEditor

    # Simulate file is not already open
    efc.path_to_editor.clear()

    efc.open_new_tab(file_path)

    mock_main_window.file_manager.open_file.assert_called_once_with(file_path)
    # Further effects of open_file (like _handle_file_opened creating the tab) are tested separately

@patch('editor_file_coordinator.CodeEditor')
def test_open_new_tab_untitled(MockCodeEditorClass, efc, mock_main_window):
    mock_editor_instance = MockCodeEditorClass.return_value

    efc.open_new_tab(None) # Open untitled

    MockCodeEditorClass.assert_called_once_with(mock_main_window)
    # Tab creation and signal connections
    mock_main_window.tab_widget.addTab.assert_called_once_with(mock_editor_instance, "Untitled-1")
    # Verify signal connections on the new editor instance
    mock_editor_instance.textChanged.connect.assert_called_with(mock_main_window.on_text_editor_changed)
    mock_editor_instance.cursor_position_changed_signal.connect.assert_called_with(mock_main_window._update_cursor_position_label)
    # ... and other signal connections

    assert "untitled:Untitled-1" in efc.path_to_editor
    assert efc.path_to_editor["untitled:Untitled-1"] == mock_editor_instance
    assert mock_editor_instance.file_path == "untitled:Untitled-1"

def test_open_new_tab_already_open(efc, mock_main_window):
    file_path = "/already/open.txt"
    mock_existing_editor = MagicMock(spec=CodeEditor)
    efc.path_to_editor[file_path] = mock_existing_editor
    mock_main_window.tab_widget.indexOf.return_value = 1 # Simulate it's in tab 1

    efc.open_new_tab(file_path)

    mock_main_window.tab_widget.setCurrentIndex.assert_called_with(1)
    mock_main_window.file_manager.open_file.assert_not_called() # Should not try to re-open

# --- Tests for _handle_file_opened ---
@patch('editor_file_coordinator.CodeEditor') # Patch where CodeEditor is imported in efc
def test_handle_file_opened(MockCodeEditorClass, efc, mock_main_window):
    path = "/test.py"
    content = "print('test')"
    mock_editor_instance = MockCodeEditorClass.return_value

    efc._handle_file_opened(path, content)

    MockCodeEditorClass.assert_called_once_with(mock_main_window)
    mock_editor_instance.setPlainText.assert_called_once_with(content)
    assert mock_editor_instance.file_path == path # Check internal path of editor
    mock_editor_instance.set_file_path_and_update_language.assert_called_once_with(path)
    mock_main_window.tab_widget.addTab.assert_called_once_with(mock_editor_instance, os.path.basename(path))
    # Assertions for signal connections on mock_editor_instance
    # ... (e.g., textChanged, cursor_position_changed_signal)
    assert efc.path_to_editor[path] == mock_editor_instance
    assert efc.editor_to_path[mock_editor_instance] == path

# --- Tests for _handle_file_open_error ---
@patch('PySide6.QtWidgets.QMessageBox.critical')
def test_handle_file_open_error(mock_msgbox_critical, efc, mock_main_window):
    efc._handle_file_open_error("/path/file.txt", "Cannot open")
    mock_msgbox_critical.assert_called_once()
    mock_main_window.status_bar.showMessage.assert_called_with("Error opening /path/file.txt", 5000)

# --- Tests for get_active_file_path ---
def test_get_active_file_path(efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    active_path = "/active/file.py"
    mock_main_window._get_current_code_editor = MagicMock(return_value=mock_editor) # Mock helper in MainWindow
    efc.editor_to_path[mock_editor] = active_path

    assert efc.get_active_file_path() == active_path

    efc.editor_to_path[mock_editor] = "untitled:Untitled-1"
    assert efc.get_active_file_path() is None # Untitled should return None

    mock_main_window._get_current_code_editor.return_value = None # No active editor
    assert efc.get_active_file_path() is None

# --- Tests for close_tab ---
@patch('PySide6.QtWidgets.QMessageBox.question')
def test_close_tab_dirty_save(mock_msgbox_question, efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    path = "/dirty/file.txt"
    mock_main_window.tab_widget.widget.return_value = mock_editor
    mock_main_window.tab_widget.currentIndex.return_value = 0
    efc.editor_to_path[mock_editor] = path
    efc.path_to_editor[path] = mock_editor
    mock_main_window.file_manager.get_dirty_state.return_value = True # File is dirty

    mock_msgbox_question.return_value = QMessageBox.Save # User chooses to save

    # Mock _save_file to return True (save successful)
    with patch.object(efc, '_save_file', return_value=True) as mock_internal_save:
        efc.close_tab(0)

    mock_internal_save.assert_called_once_with(0)
    mock_main_window.file_manager.file_closed_in_editor.assert_called_once_with(path)
    mock_main_window.tab_widget.removeTab.assert_called_once_with(0)
    assert mock_editor not in efc.editor_to_path
    assert path not in efc.path_to_editor

@patch('PySide6.QtWidgets.QMessageBox.question')
def test_close_tab_dirty_discard(mock_msgbox_question, efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    path = "/dirty/file.txt"
    mock_main_window.tab_widget.widget.return_value = mock_editor
    mock_main_window.tab_widget.currentIndex.return_value = 0
    efc.editor_to_path[mock_editor] = path
    efc.path_to_editor[path] = mock_editor
    mock_main_window.file_manager.get_dirty_state.return_value = True

    mock_msgbox_question.return_value = QMessageBox.Discard # User chooses to discard

    with patch.object(efc, '_save_file') as mock_internal_save: # Ensure _save_file is not called
        efc.close_tab(0)

    mock_internal_save.assert_not_called()
    mock_main_window.file_manager.file_closed_in_editor.assert_called_once_with(path)
    mock_main_window.tab_widget.removeTab.assert_called_once_with(0)


@patch('PySide6.QtWidgets.QMessageBox.question')
def test_close_tab_dirty_cancel(mock_msgbox_question, efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    path = "/dirty/file.txt"
    mock_main_window.tab_widget.widget.return_value = mock_editor
    efc.editor_to_path[mock_editor] = path
    mock_main_window.file_manager.get_dirty_state.return_value = True

    mock_msgbox_question.return_value = QMessageBox.Cancel # User chooses to cancel

    efc.close_tab(0)

    mock_main_window.file_manager.file_closed_in_editor.assert_not_called()
    mock_main_window.tab_widget.removeTab.assert_not_called()

def test_close_tab_clean(efc, mock_main_window):
    mock_editor = MagicMock(spec=CodeEditor)
    path = "/clean/file.txt"
    mock_main_window.tab_widget.widget.return_value = mock_editor
    efc.editor_to_path[mock_editor] = path
    efc.path_to_editor[path] = mock_editor
    mock_main_window.file_manager.get_dirty_state.return_value = False # File is clean

    efc.close_tab(0)

    mock_main_window.file_manager.file_closed_in_editor.assert_called_once_with(path)
    mock_main_window.tab_widget.removeTab.assert_called_once_with(0)

# --- Tests for create_new_file ---
@patch('PySide6.QtWidgets.QInputDialog.getText')
@patch('os.path.exists')
@patch('builtins.open', new_callable=mock_open) # Mock the global open
def test_create_new_file_success(mock_builtin_open, mock_path_exists, mock_input_dialog_gettext, efc, mock_main_window):
    mock_main_window.file_explorer.selectionModel.return_value.currentIndex.return_value.isValid.return_value = True
    target_dir = "/target/directory"
    mock_main_window.file_explorer.model.filePath.return_value = target_dir # Selected item is a directory
    # Simulate os.path.isdir for the selected path
    with patch('os.path.isdir', return_value=True):
        mock_input_dialog_gettext.return_value = ("new_file.txt", True) # User enters name and clicks OK
        mock_path_exists.return_value = False # New file does not exist yet

        # Mock open_new_tab as it's tested separately
        with patch.object(efc, 'open_new_tab') as mock_efc_open_new_tab:
            efc.create_new_file()

    expected_new_path = os.path.join(target_dir, "new_file.txt")
    mock_builtin_open.assert_called_once_with(expected_new_path, 'w', encoding='utf-8')
    mock_efc_open_new_tab.assert_called_once_with(expected_new_path)
    mock_main_window.status_bar.showMessage.assert_called_with(f"Created: {expected_new_path}", 3000)

@patch('PySide6.QtWidgets.QInputDialog.getText')
def test_create_new_file_cancelled(mock_input_dialog_gettext, efc, mock_main_window):
    mock_main_window.file_explorer.selectionModel.return_value.currentIndex.return_value.isValid.return_value = False
    mock_main_window.file_explorer.model.rootPath.return_value = "/root/path"

    mock_input_dialog_gettext.return_value = ("", False) # User cancels dialog

    with patch('builtins.open') as mock_builtin_open: # Ensure open is not called
        efc.create_new_file()
        mock_builtin_open.assert_not_called()
