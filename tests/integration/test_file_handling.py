import pytest
import os
from unittest.mock import MagicMock, patch, mock_open

from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox, QTextEdit
from PySide6.QtCore import Signal, Qt

# Classes under test
from editor_file_coordinator import EditorFileCoordinator
from file_manager import FileManager
from code_editor import CodeEditor # For type checks and mocking editor instances

# --- Fixtures ---

@pytest.fixture
def file_manager_instance():
    fm = FileManager()
    # We can mock signals if we want to assert their emission during integration tests,
    # though the primary focus is the interaction and state changes.
    fm.file_opened = MagicMock(spec=Signal)
    fm.file_saved = MagicMock(spec=Signal)
    fm.file_open_error = MagicMock(spec=Signal)
    fm.file_save_error = MagicMock(spec=Signal)
    fm.dirty_status_changed = MagicMock(spec=Signal)
    return fm

@pytest.fixture
def mock_main_window_for_efc_integration():
    mw = MagicMock(spec=[
        'tab_widget', 'file_manager', 'collaboration_service',
        'status_bar', 'file_explorer', 'editor_file_coordinator',
        'execution_coordinator', 'initialize_project',
        'on_text_editor_changed', '_update_cursor_position_label',
        '_update_language_label', '_update_status_bar_and_language_selector_on_tab_change',
        'update_editor_read_only_state', '_update_undo_redo_actions',
        '_handle_dirty_status_changed', '_get_current_code_editor' # Added _get_current_code_editor
    ])

    mw.tab_widget = MagicMock(spec=QWidget)
    mw.tab_widget.widget = MagicMock(return_value=None) # Will be set by tests
    mw.tab_widget.indexOf = MagicMock(return_value=0)
    mw.tab_widget.currentIndex = MagicMock(return_value=0)
    mw.tab_widget.addTab = MagicMock(return_value=0)
    mw.tab_widget.setTabText = MagicMock()
    mw.tab_widget.setTabToolTip = MagicMock()
    mw.tab_widget.tabText = MagicMock(return_value="filename.txt")

    # FileManager will be a real instance in these tests
    # mw.file_manager will be replaced by the real file_manager_instance

    mw.collaboration_service = MagicMock()
    mw.collaboration_service.is_updating_from_network = False

    mw.status_bar = MagicMock()
    mw.status_bar.showMessage = MagicMock()

    mw.file_explorer = MagicMock()
    mw.file_explorer.refresh_tree = MagicMock()

    mw.execution_coordinator = MagicMock()
    mw.execution_coordinator._handle_breakpoint_toggled = MagicMock()

    mw.editor_to_path = {}
    mw.path_to_editor = {}

    mw._get_current_code_editor = MagicMock(return_value=None) # Will be set by tests
    mw._handle_dirty_status_changed = MagicMock() # EFC might call this directly or indirectly
    # Mock methods that MainWindow would have, which EFC might call or rely on signals from
    mw.on_text_editor_changed = MagicMock()
    mw._update_cursor_position_label = MagicMock()
    mw._update_language_label = MagicMock()
    mw.update_editor_read_only_state = MagicMock()
    mw._update_undo_redo_actions = MagicMock()


    return mw

@pytest.fixture
def efc_with_real_fm(mock_main_window_for_efc_integration, file_manager_instance):
    # Replace the mocked file_manager on MainWindow with the real one
    mock_main_window_for_efc_integration.file_manager = file_manager_instance

    coordinator = EditorFileCoordinator()
    coordinator.set_main_window_ref(mock_main_window_for_efc_integration)

    # Connect signals from the real FileManager to EFC's slots
    # This is crucial for testing the integration.
    file_manager_instance.file_opened.connect(coordinator._handle_file_opened)
    file_manager_instance.file_open_error.connect(coordinator._handle_file_open_error)
    file_manager_instance.file_saved.connect(coordinator._handle_file_saved)
    file_manager_instance.file_save_error.connect(coordinator._handle_file_save_error)

    # MainWindow also connects to dirty_status_changed. EFC doesn't have a direct slot for it,
    # but relies on MainWindow's _handle_dirty_status_changed.
    # We can mock this on MainWindow and verify EFC's actions lead to it being called.
    file_manager_instance.dirty_status_changed.connect(mock_main_window_for_efc_integration._handle_dirty_status_changed)

    return coordinator, file_manager_instance # Return both for direct interaction

# --- Integration Tests ---

@patch('editor_file_coordinator.CodeEditor') # Mock CodeEditor instantiation within EFC
@patch('os.path.exists', return_value=True)
@patch('os.path.isfile', return_value=True)
@patch('builtins.open', new_callable=mock_open, read_data="file content")
def test_open_file_flow(mock_fs_open, mock_isfile, mock_exists, MockCodeEditorClass, efc_with_real_fm, mock_main_window_for_efc_integration):
    efc, fm = efc_with_real_fm
    file_path = "/test/file.txt"

    mock_editor_instance = MockCodeEditorClass.return_value
    # Simulate a file_path attribute for the mocked editor instance, CodeEditor expects this.
    # Using PropertyMock to allow setting it after instantiation if needed, or just direct assignment.
    type(mock_editor_instance).file_path = "" # Initial value, will be updated by EFC

    # Mock signals on the editor instance that EFC connects to
    mock_editor_instance.textChanged = MagicMock(spec=Signal)
    mock_editor_instance.cursor_position_changed_signal = MagicMock(spec=Signal)
    mock_editor_instance.language_changed_signal = MagicMock(spec=Signal)
    mock_editor_instance.control_reclaim_requested = MagicMock(spec=Signal) # If CodeEditor has this
    mock_editor_instance.breakpoint_toggled = MagicMock(spec=Signal) # If CodeEditor has this
    mock_editor_instance.set_file_path_and_update_language = MagicMock() # Mock this method


    # Simulate EFC's open_new_tab being called (e.g., from user action or session load)
    # This will trigger fm.open_file, which then signals back to efc._handle_file_opened
    efc.open_new_tab(file_path)

    # --- Assertions for FileManager interaction ---
    # fm.open_file was called by efc.open_new_tab
    # This now happens inside the real fm.open_file, so we check its effects (signal)
    fm.file_opened.emit.assert_called_once_with(file_path, "file content")

    # --- Assertions for EFC handling FileManager's signal ---
    # _handle_file_opened should have been called by fm.file_opened signal
    MockCodeEditorClass.assert_called_once_with(mock_main_window_for_efc_integration)
    mock_editor_instance.setPlainText.assert_called_once_with("file content")

    # Check that EFC sets the file_path on the editor instance via the method
    mock_editor_instance.set_file_path_and_update_language.assert_called_with(file_path)
    # We also need to ensure EFC's internal mapping uses the editor instance where file_path is correctly set.
    # The mock_editor_instance's file_path property should reflect this.
    # This depends on how EFC sets it. If it's direct assignment:
    # assert mock_editor_instance.file_path == file_path
    # If it's via a method that also updates language, that method call is checked above.

    mock_main_window_for_efc_integration.tab_widget.addTab.assert_called_with(mock_editor_instance, os.path.basename(file_path))

    assert efc.path_to_editor[file_path] == mock_editor_instance
    assert efc.editor_to_path[mock_editor_instance] == file_path

    # Check signals on the created editor were connected
    mock_editor_instance.textChanged.connect.assert_called_with(mock_main_window_for_efc_integration.on_text_editor_changed)
    mock_editor_instance.cursor_position_changed_signal.connect.assert_called_with(mock_main_window_for_efc_integration._update_cursor_position_label)
    # ... other signal connection assertions


@patch('PySide6.QtWidgets.QFileDialog.getSaveFileName')
@patch('os.makedirs')
@patch('builtins.open', new_callable=mock_open)
@patch('editor_file_coordinator.CodeEditor') # Mock CodeEditor created by EFC for untitled tab
def test_save_new_untitled_file_flow(MockCodeEditorClassUntitled, mock_fs_open, mock_os_makedirs, mock_qfiledialog_save, efc_with_real_fm, mock_main_window_for_efc_integration):
    efc, fm = efc_with_real_fm

    # 1. Create an untitled tab first
    mock_untitled_editor = MockCodeEditorClassUntitled.return_value
    mock_untitled_editor.toPlainText.return_value = "new file content"
    # Simulate EFC creating an untitled tab
    # Ensure the correct mock is used for CodeEditor instantiation within open_new_tab
    with patch('editor_file_coordinator.CodeEditor', MockCodeEditorClassUntitled):
        efc.open_new_tab(None)

    untitled_path_placeholder = next(iter(efc.path_to_editor.keys()))
    mock_main_window_for_efc_integration.tab_widget.widget.return_value = mock_untitled_editor
    mock_main_window_for_efc_integration._get_current_code_editor.return_value = mock_untitled_editor
    # EFC updates main_window's editor_to_path directly.
    mock_main_window_for_efc_integration.editor_to_path[mock_untitled_editor] = untitled_path_placeholder


    # 2. Simulate saving this untitled tab
    saved_file_path = "/saved/new_file.txt"
    mock_qfiledialog_save.return_value = (saved_file_path, "Text Files (*.txt)")

    efc.save_current_file()

    # --- Assertions for FileManager interaction ---
    # fm.save_file would have been called by efc._save_file
    # We check the signal that fm.save_file emits
    fm.file_saved.emit.assert_called_once_with(mock_untitled_editor, saved_file_path, "new file content")

    # --- Assertions for EFC handling FileManager's signal ---
    # _handle_file_saved should have updated mappings and UI
    assert efc.editor_to_path[mock_untitled_editor] == saved_file_path
    assert efc.path_to_editor[saved_file_path] == mock_untitled_editor
    assert untitled_path_placeholder not in efc.path_to_editor

    mock_main_window_for_efc_integration.tab_widget.setTabText.assert_called_with(ANY, os.path.basename(saved_file_path))
    mock_main_window_for_efc_integration.file_explorer.refresh_tree.assert_called_once()


@patch('builtins.open', new_callable=mock_open)
def test_dirty_status_propagation(mock_fs_open, efc_with_real_fm, mock_main_window_for_efc_integration):
    efc, fm = efc_with_real_fm
    file_path = "/test/dirty_test.txt"
    original_content = "original"
    new_content = "changed content"

    # 1. Open a file (it's initially clean)
    mock_fs_open.return_value.read.return_value = original_content # Configure mock for read

    # Mock CodeEditor instantiation for this open operation
    with patch('editor_file_coordinator.CodeEditor') as MockEditorForOpen:
        mock_editor_instance_for_open = MockEditorForOpen.return_value
        mock_editor_instance_for_open.toPlainText.return_value = original_content
        mock_editor_instance_for_open.set_file_path_and_update_language = MagicMock() # Mock this method
        # Mock signals for this instance
        mock_editor_instance_for_open.textChanged = MagicMock(spec=Signal)
        mock_editor_instance_for_open.cursor_position_changed_signal = MagicMock(spec=Signal)


        with patch('os.path.exists', return_value=True), patch('os.path.isfile', return_value=True):
            efc.open_new_tab(file_path)

    # FileManager should have marked it clean.
    # If file_opened implies clean, dirty_status_changed might not be emitted for initial open.
    # Let's check the state directly first.
    assert not fm.get_dirty_state(file_path)
    # Reset call count for dirty_status_changed for subsequent checks
    fm.dirty_status_changed.emit.reset_mock()


    # 2. Simulate editor content changing (making it dirty)
    mock_current_editor = efc.path_to_editor[file_path]
    mock_current_editor.toPlainText.return_value = new_content

    fm.update_file_content_changed(file_path, new_content)

    assert fm.get_dirty_state(file_path) is True
    fm.dirty_status_changed.emit.assert_called_with(file_path, True)
    mock_main_window_for_efc_integration._handle_dirty_status_changed.assert_called_with(file_path, True)

    # 3. Save the file (should become clean)
    mock_fs_open.reset_mock()

    mock_main_window_for_efc_integration.tab_widget.widget.return_value = mock_current_editor
    mock_main_window_for_efc_integration._get_current_code_editor.return_value = mock_current_editor

    with patch('os.makedirs'):
        efc.save_current_file()

    assert fm.get_dirty_state(file_path) is False
    fm.dirty_status_changed.emit.assert_called_with(file_path, False)
    mock_main_window_for_efc_integration._handle_dirty_status_changed.assert_called_with(file_path, False)

```
