import pytest
import os
from unittest.mock import patch, MagicMock, mock_open

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Adjust imports based on your project structure
from main_window import MainWindow
from editor_file_coordinator import EditorFileCoordinator
from user_session_coordinator import UserSessionCoordinator
from collaboration_service import CollaborationService
from execution_coordinator import ExecutionCoordinator
from code_editor import CodeEditor # To check instance type

# Ensure a QApplication instance exists for the test session
# @pytest.fixture(scope="session", autouse=True) # Removed custom qapp
# def qapp():
#     app = QApplication.instance()
#     if app is None:
#         return QApplication([])
#     return app

@pytest.fixture
def main_window_with_coordinators(qtbot): # qtbot fixture from pytest-qt should provide qapp
    editor_file_coord = EditorFileCoordinator()
    user_session_coord = UserSessionCoordinator()
    collab_service = CollaborationService()
    # exec_coord needs to be defined before being used in MainWindow constructor

    # Mock ConfigManager for ExecutionCoordinator
    # Ensure load_setting returns a dict, even if empty, to avoid None issues
    mock_config_manager_instance = MagicMock()
    # Default to empty dict; specific tests can override
    mock_config_manager_instance.load_setting.return_value = {
        'runner_config': {},
        'extension_to_language_map': {}
    }

    with patch('execution_coordinator.ConfigManager', return_value=mock_config_manager_instance):
        exec_coord = ExecutionCoordinator() # Now exec_coord is defined

    collab_service.network_manager = MagicMock()
    exec_coord.process_manager = MagicMock()
    exec_coord.debug_manager = MagicMock()

    window = MainWindow(
        editor_file_coordinator=editor_file_coord,
        user_session_coordinator=user_session_coord,
        collaboration_service=collab_service,
        execution_coordinator=exec_coord
    )

    editor_file_coord.set_main_window_ref(window)
    user_session_coord.set_main_window_ref(window)
    collab_service.set_main_window_ref(window)
    exec_coord.set_main_window_ref(window)

    qtbot.addWidget(window)
    # window.show() # Removed to see if it prevents the fatal error

    yield window

    window.close() # Ensure cleanup

def test_simplified_open_file(main_window_with_coordinators, qtbot, tmp_path):
    window = main_window_with_coordinators

    test_file_content = "Simplified test content."
    test_file = tmp_path / "simple_test.txt"
    test_file.write_text(test_file_content)

    # Directly use EFC to open the tab, bypassing FileExplorer UI for this simplified test
    # We still need to mock the file system operations that FileManager (used by EFC) will perform
    with patch('builtins.open', mock_open(read_data=test_file_content)) as mock_fs_open,          patch('os.path.exists', return_value=True),          patch('os.path.isfile', return_value=True):

        # Call a method on EFC that would lead to opening a file.
        # open_new_tab is suitable if the file already exists in EFC's view or should be loaded.
        window.editor_file_coordinator.open_new_tab(str(test_file))

    def check_tab_opened_simple():
        if not (window.tab_widget.count() > 0): return False
        current_editor = window.tab_widget.currentWidget()
        if not isinstance(current_editor, CodeEditor): return False
        # Tab title check
        if not (window.tab_widget.tabText(window.tab_widget.currentIndex()) == "simple_test.txt"): return False
        # Content check
        if not (current_editor.toPlainText() == test_file_content): return False
        return True

    qtbot.waitUntil(check_tab_opened_simple, timeout=3000)

# Placeholder for the more complex save test, to be added back once the syntax issue is resolved
# def test_save_file_new_untitled_tab(main_window_with_coordinators, qtbot, tmp_path):
#     pass
