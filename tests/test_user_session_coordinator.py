import pytest
from unittest.mock import MagicMock, patch, call, PropertyMock

from PySide6.QtWidgets import QMessageBox, QLineEdit # For mocking QInputDialog

# Adjust import path as necessary
from user_session_coordinator import UserSessionCoordinator
# Assuming EditorFileCoordinator might be needed for type hints or complex interactions if not fully mocked
# from editor_file_coordinator import EditorFileCoordinator

@pytest.fixture
def mock_main_window():
    mw = MagicMock(spec=[
        'file_manager', 'session_manager', 'editor_file_coordinator',
        'status_bar', 'welcome_page', '_update_recent_menu',
        'initialize_project', 'recent_projects', 'tab_widget', # Added tab_widget
        '_handle_pending_initial_path_after_session_load' # Added for session load
    ])

    mw.file_manager = MagicMock()
    mw.file_manager.get_all_open_files_data = MagicMock(return_value={})
    mw.file_manager.load_open_files_data = MagicMock()

    mw.session_manager = MagicMock()
    mw.session_manager.save_session = MagicMock()
    mw.session_manager.load_session = MagicMock() # Though USC connects to its signals mostly

    mw.editor_file_coordinator = MagicMock()
    mw.editor_file_coordinator.get_active_file_path = MagicMock(return_value=None)
    mw.editor_file_coordinator.open_new_tab = MagicMock()
    mw.editor_file_coordinator.path_to_editor = {} # Simulate this attribute

    mw.status_bar = MagicMock()
    mw.status_bar.showMessage = MagicMock()

    mw.welcome_page = MagicMock(spec=['update_list']) # Mock welcome_page if methods are called
    mw._update_recent_menu = MagicMock()
    mw.initialize_project = MagicMock()

    # UserSessionCoordinator modifies MainWindow's recent_projects list directly
    mw.recent_projects = []

    mw.tab_widget = MagicMock() # For active tab restoration logic
    mw.tab_widget.count = MagicMock(return_value=0)
    mw.tab_widget.setCurrentIndex = MagicMock()
    mw.tab_widget.indexOf = MagicMock(return_value=-1)

    mw._handle_pending_initial_path_after_session_load = MagicMock()


    # Mock file_explorer attribute on main_window if it's accessed
    # This is for the root_path_to_save logic in save_session
    mw.file_explorer = MagicMock()
    type(mw.file_explorer).model = PropertyMock(spec=True) # Make 'model' a mock itself
    mw.file_explorer.model.rootPath = MagicMock(return_value="/mock/root/path")


    return mw

@pytest.fixture
def usc(mock_main_window):
    coordinator = UserSessionCoordinator()
    coordinator.set_main_window_ref(mock_main_window)
    # Ensure USC uses the list from the mocked MainWindow
    assert coordinator.recent_projects is mock_main_window.recent_projects
    return coordinator

# --- Test save_session ---
def test_save_session_with_root_path_from_explorer(usc, mock_main_window):
    open_files_data = {"/mock/root/path/file.py": {"is_dirty": False, "content_hash": 123}}
    active_file = "/mock/root/path/file.py"

    mock_main_window.file_manager.get_all_open_files_data.return_value = open_files_data
    mock_main_window.editor_file_coordinator.get_active_file_path.return_value = active_file
    mock_main_window.recent_projects = ["/mock/root/path"] # Example recent project

    usc.save_session()

    mock_main_window.session_manager.save_session.assert_called_once_with(
        open_files_data,
        ["/mock/root/path"], # USC's recent_projects list
        "/mock/root/path",   # from file_explorer.model.rootPath()
        active_file
    )

def test_save_session_root_path_from_active_file_if_no_explorer_model(usc, mock_main_window):
    # Simulate file_explorer.model being None
    type(mock_main_window.file_explorer).model = PropertyMock(return_value=None)

    open_files_data = {"/some/other/path/file.py": {"is_dirty": False, "content_hash": 456}}
    active_file = "/some/other/path/file.py"

    mock_main_window.file_manager.get_all_open_files_data.return_value = open_files_data
    mock_main_window.editor_file_coordinator.get_active_file_path.return_value = active_file

    with patch('os.path.exists', return_value=True),          patch('os.path.dirname', return_value="/some/other/path"): # Mock os.path.dirname
        usc.save_session()

    mock_main_window.session_manager.save_session.assert_called_once_with(
        open_files_data,
        mock_main_window.recent_projects, # Should be the list from mock_main_window
        "/some/other/path", # Derived from active_file
        active_file
    )

# --- Test _handle_session_loaded ---
def test_handle_session_loaded_full_data(usc, mock_main_window):
    session_data = {
        "recent_projects": ["/proj1", "/proj2"],
        "root_path": "/proj1",
        "open_files_data": {"/proj1/fileA.py": {"is_dirty": False, "content_hash": 111}},
        "active_file_path": "/proj1/fileA.py"
    }

    # Simulate the editor for the active file exists and can be found
    mock_editor_for_active_file = MagicMock()
    mock_main_window.editor_file_coordinator.path_to_editor = {"/proj1/fileA.py": mock_editor_for_active_file}
    mock_main_window.tab_widget.indexOf.return_value = 0 # Assume it's the first tab

    with patch('os.path.exists', return_value=True): # Assume all paths exist
        usc._handle_session_loaded(session_data)

    assert mock_main_window.recent_projects == ["/proj1", "/proj2"]
    mock_main_window._update_recent_menu.assert_called_once()
    mock_main_window.file_manager.load_open_files_data.assert_called_once_with(session_data["open_files_data"])
    mock_main_window.initialize_project.assert_called_once_with("/proj1", add_to_recents=False)
    mock_main_window.editor_file_coordinator.open_new_tab.assert_called_once_with("/proj1/fileA.py")
    mock_main_window._handle_pending_initial_path_after_session_load.assert_called_once_with(session_data)
    mock_main_window.tab_widget.setCurrentIndex.assert_called_once_with(0)
    mock_main_window.status_bar.showMessage.assert_called_with("Session loaded.", 2000)

def test_handle_session_loaded_file_not_exists(usc, mock_main_window):
    session_data = {
        "open_files_data": {"/non/existent.py": {"hash": 1}},
        # ... other fields
    }
    with patch('os.path.exists', return_value=False): # File does not exist
        usc._handle_session_loaded(session_data)

    # open_new_tab should not be called for non-existent file
    mock_main_window.editor_file_coordinator.open_new_tab.assert_not_called()

# --- Test _handle_session_saved_confirmation ---
def test_handle_session_saved_confirmation(usc, mock_main_window):
    usc._handle_session_saved_confirmation()
    mock_main_window.status_bar.showMessage.assert_called_with("Session saved.", 2000)

# --- Test _handle_session_error ---
@patch('PySide6.QtWidgets.QMessageBox.warning')
def test_handle_session_error(mock_msgbox_warning, usc, mock_main_window):
    error_msg = "Failed to save session."
    usc._handle_session_error(error_msg)
    mock_msgbox_warning.assert_called_once_with(mock_main_window, "Session Error", error_msg)
    mock_main_window.status_bar.showMessage.assert_called_with(f"Session error: {error_msg}", 5000)

# --- Test add_recent_project ---
def test_add_recent_project_new(usc, mock_main_window):
    new_project_path = "/new/project"
    usc.add_recent_project(new_project_path)

    assert mock_main_window.recent_projects == [new_project_path]
    mock_main_window._update_recent_menu.assert_called_once()
    # save_session is called by add_recent_project
    assert mock_main_window.session_manager.save_session.call_count > 0

def test_add_recent_project_existing_moves_to_front(usc, mock_main_window):
    mock_main_window.recent_projects = ["/old/project1", "/existing/project", "/old/project2"]

    usc.add_recent_project("/existing/project")

    assert mock_main_window.recent_projects[0] == "/existing/project"
    assert len(mock_main_window.recent_projects) == 3 # Length should be preserved

def test_add_recent_project_list_limit(usc, mock_main_window):
    mock_main_window.recent_projects = [f"/proj{i}" for i in range(10)] # Already 10 projects

    usc.add_recent_project("/new_proj11")

    assert len(mock_main_window.recent_projects) == 10
    assert "/new_proj11" == mock_main_window.recent_projects[0]
    assert "/proj0" not in mock_main_window.recent_projects # Oldest should be removed

# --- Test perform_clear_recent_projects_action ---
def test_perform_clear_recent_projects_action(usc, mock_main_window):
    mock_main_window.recent_projects = ["/proj1", "/proj2"]

    usc.perform_clear_recent_projects_action()

    assert mock_main_window.recent_projects == []
    mock_main_window._update_recent_menu.assert_called()
    if mock_main_window.welcome_page: # Check if welcome_page mock was setup/called
        mock_main_window.welcome_page.update_list.assert_called_with([])
    mock_main_window.status_bar.showMessage.assert_called_with("Recent projects list cleared.", 3000)
    assert mock_main_window.session_manager.save_session.call_count > 0

# --- Test handle_rename_recent_project ---
@patch('PySide6.QtWidgets.QInputDialog.getText')
def test_handle_rename_recent_project_success(mock_input_dialog, usc, mock_main_window):
    old_path = "/project/alpha"
    new_path = "/project/beta"
    mock_main_window.recent_projects = ["/other", old_path]
    mock_input_dialog.return_value = (new_path, True) # User enters new_path and clicks OK

    usc.handle_rename_recent_project(old_path)

    assert mock_main_window.recent_projects == ["/other", new_path]
    mock_main_window._update_recent_menu.assert_called()
    if mock_main_window.welcome_page:
         mock_main_window.welcome_page.update_list.assert_called_with(mock_main_window.recent_projects)
    assert mock_main_window.session_manager.save_session.call_count > 0

@patch('PySide6.QtWidgets.QInputDialog.getText')
def test_handle_rename_recent_project_cancel(mock_input_dialog, usc, mock_main_window):
    old_path = "/project/alpha"
    mock_main_window.recent_projects = [old_path]
    original_list = list(mock_main_window.recent_projects)
    mock_input_dialog.return_value = (old_path, False) # User cancels

    usc.handle_rename_recent_project(old_path)

    assert mock_main_window.recent_projects == original_list # List should not change
    mock_main_window.session_manager.save_session.assert_not_called() # Save not called

# --- Test handle_remove_recent_project_with_confirmation ---
def test_handle_remove_recent_project_with_confirmation(usc, mock_main_window):
    path_to_remove = "/project/to_remove"
    mock_main_window.recent_projects = ["/other", path_to_remove, "/another"]

    usc.handle_remove_recent_project_with_confirmation(path_to_remove)

    assert mock_main_window.recent_projects == ["/other", "/another"]
    mock_main_window._update_recent_menu.assert_called()
    if mock_main_window.welcome_page:
         mock_main_window.welcome_page.update_list.assert_called_with(mock_main_window.recent_projects)
    assert mock_main_window.session_manager.save_session.call_count > 0

# --- Test update_recent_projects_from_welcome ---
def test_update_recent_projects_from_welcome(usc, mock_main_window):
    updated_list = ["/new/path1", "/new/path2"]
    usc.update_recent_projects_from_welcome(updated_list)

    assert mock_main_window.recent_projects == updated_list
    mock_main_window._update_recent_menu.assert_called()
    assert mock_main_window.session_manager.save_session.call_count > 0
