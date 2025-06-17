import pytest
import os
import json
from pathlib import Path # For tmp_path usage
from config_manager import ConfigManager # Assumes config_manager.py is in root
# Import default configs to verify against them
from config import (
    DEFAULT_RUNNER_CONFIG,
    DEFAULT_EDITOR_SETTINGS,
    DEFAULT_AI_SETTINGS,
    DEFAULT_EXTENSION_TO_LANGUAGE_MAP
)

@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    config_dir = tmp_path / ".aether_editor"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"

@pytest.fixture
def manager(temp_config_file: Path, monkeypatch: pytest.MonkeyPatch) -> ConfigManager:
    # Ensure the temp_config_file does not exist before ConfigManager instance is created for a test
    if temp_config_file.exists():
        temp_config_file.unlink()

    monkeypatch.setattr(ConfigManager, "_get_config_path", lambda self: str(temp_config_file))
    # The ConfigManager.__init__ calls _initialize_default_... methods,
    # which will create and populate the temp_config_file if it doesn't exist.
    return ConfigManager()

def test_load_api_key_file_not_exist(temp_config_file: Path, monkeypatch: pytest.MonkeyPatch):
    # Test before ConfigManager() is even called, to ensure file not found is handled
    if temp_config_file.exists():
        temp_config_file.unlink()
    monkeypatch.setattr(ConfigManager, "_get_config_path", lambda self: str(temp_config_file))
    cm = ConfigManager() # This will now try to load a non-existent file for defaults
    assert cm.load_api_key() is None

def test_save_and_load_api_key(manager: ConfigManager, temp_config_file: Path):
    test_key = "test_api_key_123"
    manager.save_api_key(test_key)
    assert manager.load_api_key() == test_key

    with temp_config_file.open('r') as f:
        data = json.load(f)
    assert data.get("api_key") == test_key

def test_save_and_load_generic_setting(manager: ConfigManager, temp_config_file: Path):
    manager.save_setting("my_setting", "my_value")
    assert manager.load_setting("my_setting") == "my_value"
    manager.save_setting("my_int_setting", 123)
    assert manager.load_setting("my_int_setting") == 123

    with temp_config_file.open('r') as f:
        data = json.load(f)
    assert data.get("my_setting") == "my_value"
    assert data.get("my_int_setting") == 123

def test_load_generic_setting_with_default_value(manager: ConfigManager):
    assert manager.load_setting("non_existent_key", "default_string") == "default_string"
    assert manager.load_setting("non_existent_int_key", 100) == 100

def test_default_settings_are_initialized(manager: ConfigManager, temp_config_file: Path):
    # ConfigManager's __init__ should have initialized defaults if file was empty.
    # The 'manager' fixture ensures the file is empty before ConfigManager is created.
    assert temp_config_file.exists(), "Config file should be created by ConfigManager init."

    with temp_config_file.open('r') as f:
        data = json.load(f)

    assert data.get("runner_config") == DEFAULT_RUNNER_CONFIG
    assert data.get("editor_settings") == DEFAULT_EDITOR_SETTINGS
    assert data.get("ai_settings") == DEFAULT_AI_SETTINGS
    assert data.get("extension_to_language_map") == DEFAULT_EXTENSION_TO_LANGUAGE_MAP

def test_overwriting_setting(manager: ConfigManager):
    manager.save_setting("test_overwrite", "initial_value")
    assert manager.load_setting("test_overwrite") == "initial_value"
    manager.save_setting("test_overwrite", "new_value")
    assert manager.load_setting("test_overwrite") == "new_value"

def test_load_setting_non_existent_returns_default(manager: ConfigManager):
    assert manager.load_setting("absolutely_not_there", "fallback") == "fallback"
    assert manager.load_setting("absolutely_not_there_either", None) is None
