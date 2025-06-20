import os
import json
import logging
from typing import Any # Added for type hints

logger = logging.getLogger(__name__)

# Attempt to import the default runner config for initialization
try:
    from config import RUNNER_CONFIG as DEFAULT_RUNNER_CONFIG
    from config import DEFAULT_EDITOR_SETTINGS
    from config import DEFAULT_AI_SETTINGS
    from config import DEFAULT_EXTENSION_TO_LANGUAGE_MAP
    from config import DEFAULT_THEME_FILE_PATH
    # Added for new defaults
    from config import DEFAULT_MAIN_WINDOW_TITLE
    from config import DEFAULT_MAIN_WINDOW_GEOMETRY
    from config import DEFAULT_RECENT_PROJECTS_LIMIT
    from config import DEFAULT_EDITOR_FONT_FAMILY
    from config import DEFAULT_EDITOR_FONT_SIZE
    from config import DEFAULT_TERMINAL_FONT_FAMILY
    from config import DEFAULT_TERMINAL_FONT_SIZE
    from config import DEFAULT_LANGUAGE_SELECTOR_ITEMS
    # Added for editor layout defaults
    from config import DEFAULT_LINE_NUMBER_AREA_PADDING
    from config import DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING
    from config import DEFAULT_BREAKPOINT_GUTTER_WIDTH
except ImportError as e:
    logger.warning(f"Could not import default configurations from config.py: {e}. Initialization might be skipped if not present.")
    DEFAULT_RUNNER_CONFIG = None
    DEFAULT_EDITOR_SETTINGS = None
    DEFAULT_AI_SETTINGS = None
    DEFAULT_EXTENSION_TO_LANGUAGE_MAP = None
    DEFAULT_THEME_FILE_PATH = None
    # Added for new defaults
    DEFAULT_MAIN_WINDOW_TITLE = None
    DEFAULT_MAIN_WINDOW_GEOMETRY = None
    DEFAULT_RECENT_PROJECTS_LIMIT = None
    DEFAULT_EDITOR_FONT_FAMILY = None
    DEFAULT_EDITOR_FONT_SIZE = None
    DEFAULT_TERMINAL_FONT_FAMILY = None
    DEFAULT_TERMINAL_FONT_SIZE = None
    DEFAULT_LANGUAGE_SELECTOR_ITEMS = None
    # Added for editor layout defaults
    DEFAULT_LINE_NUMBER_AREA_PADDING = None
    DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING = None
    DEFAULT_BREAKPOINT_GUTTER_WIDTH = None

class ConfigManager:
    """
    Manages the application's configuration, such as API keys and runner configurations,
    stored in a JSON file in the user's home directory.
    """
    def __init__(self) -> None:
        self._initialize_default_runner_config()
        self._initialize_default_editor_settings()
        self._initialize_default_ai_settings()
        self._initialize_default_extension_map()
        self._initialize_default_theme_path()
        # Added for new defaults
        self._initialize_main_window_defaults()
        self._initialize_font_defaults()
        self._initialize_misc_defaults()
        self._initialize_language_selector_defaults()
        self._initialize_editor_layout_defaults() # Added

    def _initialize_editor_layout_defaults(self) -> None: # Added method
        """Initializes editor layout default values if not present."""
        if DEFAULT_LINE_NUMBER_AREA_PADDING is not None:
            if self.load_setting('editor_line_number_area_padding') is None:
                self.save_setting('editor_line_number_area_padding', DEFAULT_LINE_NUMBER_AREA_PADDING)
                logger.info("Initialized default editor_line_number_area_padding in config.json")
        else:
            logger.warning("DEFAULT_LINE_NUMBER_AREA_PADDING not available, skipping initialization.")

        if DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING is not None:
            if self.load_setting('editor_line_number_area_text_right_padding') is None:
                self.save_setting('editor_line_number_area_text_right_padding', DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING)
                logger.info("Initialized default editor_line_number_area_text_right_padding in config.json")
        else:
            logger.warning("DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING not available, skipping initialization.")

        if DEFAULT_BREAKPOINT_GUTTER_WIDTH is not None:
            if self.load_setting('editor_breakpoint_gutter_width') is None:
                self.save_setting('editor_breakpoint_gutter_width', DEFAULT_BREAKPOINT_GUTTER_WIDTH)
                logger.info("Initialized default editor_breakpoint_gutter_width in config.json")
        else:
            logger.warning("DEFAULT_BREAKPOINT_GUTTER_WIDTH not available, skipping initialization.")

    def _initialize_language_selector_defaults(self) -> None:
        """Initializes language selector items if not present."""
        if DEFAULT_LANGUAGE_SELECTOR_ITEMS is not None:
            if self.load_setting('language_selector_items') is None:
                self.save_setting('language_selector_items', DEFAULT_LANGUAGE_SELECTOR_ITEMS)
                logger.info("Initialized default language_selector_items in config.json")
        else:
            logger.warning("DEFAULT_LANGUAGE_SELECTOR_ITEMS not available, skipping initialization.")

    def _initialize_main_window_defaults(self) -> None:
        """Initializes main window title and geometry if not present."""
        if DEFAULT_MAIN_WINDOW_TITLE is not None:
            if self.load_setting('main_window_title') is None:
                self.save_setting('main_window_title', DEFAULT_MAIN_WINDOW_TITLE)
                logger.info("Initialized default main_window_title in config.json")
        else:
            logger.warning("DEFAULT_MAIN_WINDOW_TITLE not available, skipping initialization.")

        if DEFAULT_MAIN_WINDOW_GEOMETRY is not None:
            if self.load_setting('main_window_geometry') is None:
                self.save_setting('main_window_geometry', DEFAULT_MAIN_WINDOW_GEOMETRY)
                logger.info("Initialized default main_window_geometry in config.json")
        else:
            logger.warning("DEFAULT_MAIN_WINDOW_GEOMETRY not available, skipping initialization.")

    def _initialize_font_defaults(self) -> None:
        """Initializes editor and terminal font settings if not present."""
        if DEFAULT_EDITOR_FONT_FAMILY is not None:
            if self.load_setting('editor_font_family') is None:
                self.save_setting('editor_font_family', DEFAULT_EDITOR_FONT_FAMILY)
                logger.info("Initialized default editor_font_family in config.json")
        else:
            logger.warning("DEFAULT_EDITOR_FONT_FAMILY not available, skipping initialization.")

        if DEFAULT_EDITOR_FONT_SIZE is not None:
            if self.load_setting('editor_font_size') is None:
                self.save_setting('editor_font_size', DEFAULT_EDITOR_FONT_SIZE)
                logger.info("Initialized default editor_font_size in config.json")
        else:
            logger.warning("DEFAULT_EDITOR_FONT_SIZE not available, skipping initialization.")

        if DEFAULT_TERMINAL_FONT_FAMILY is not None:
            if self.load_setting('terminal_font_family') is None:
                self.save_setting('terminal_font_family', DEFAULT_TERMINAL_FONT_FAMILY)
                logger.info("Initialized default terminal_font_family in config.json")
        else:
            logger.warning("DEFAULT_TERMINAL_FONT_FAMILY not available, skipping initialization.")

        if DEFAULT_TERMINAL_FONT_SIZE is not None:
            if self.load_setting('terminal_font_size') is None:
                self.save_setting('terminal_font_size', DEFAULT_TERMINAL_FONT_SIZE)
                logger.info("Initialized default terminal_font_size in config.json")
        else:
            logger.warning("DEFAULT_TERMINAL_FONT_SIZE not available, skipping initialization.")

    def _initialize_misc_defaults(self) -> None:
        """Initializes miscellaneous settings like recent projects limit if not present."""
        if DEFAULT_RECENT_PROJECTS_LIMIT is not None:
            if self.load_setting('recent_projects_limit') is None:
                self.save_setting('recent_projects_limit', DEFAULT_RECENT_PROJECTS_LIMIT)
                logger.info("Initialized default recent_projects_limit in config.json")
        else:
            logger.warning("DEFAULT_RECENT_PROJECTS_LIMIT not available, skipping initialization.")

    def _initialize_default_theme_path(self) -> None:
        """
        Initializes the 'theme_file_path' in config.json if it doesn't exist.
        """
        if DEFAULT_THEME_FILE_PATH is not None:
            current_theme_path: str | None = self.load_setting('theme_file_path')
            if current_theme_path is None:
                logger.info("Initializing default theme_file_path in config.json...")
                self.save_setting('theme_file_path', DEFAULT_THEME_FILE_PATH)
            else:
                logger.debug("theme_file_path already present in config.json.")
        else:
            logger.warning("DEFAULT_THEME_FILE_PATH is not available, skipping its initialization in config.json.")

    def _initialize_default_runner_config(self) -> None:
        """
        Initializes the 'runner_config' in config.json if it doesn't exist.
        """
        if DEFAULT_RUNNER_CONFIG is not None:
            current_runner_config: dict[str, Any] | None = self.load_setting('runner_config')
            if current_runner_config is None:
                logger.info("Initializing default RUNNER_CONFIG in config.json...")
                self.save_setting('runner_config', DEFAULT_RUNNER_CONFIG)
            else:
                logger.debug("RUNNER_CONFIG already present in config.json.")
        else:
            logger.warning("DEFAULT_RUNNER_CONFIG is not available, skipping runner_config initialization in config.json.")

    def _initialize_default_editor_settings(self) -> None:
        """
        Initializes the 'editor_settings' in config.json if it doesn't exist.
        """
        if DEFAULT_EDITOR_SETTINGS is not None:
            current_editor_settings: dict[str, Any] | None = self.load_setting('editor_settings')
            if current_editor_settings is None:
                logger.info("Initializing default editor_settings in config.json...")
                self.save_setting('editor_settings', DEFAULT_EDITOR_SETTINGS)
            else:
                logger.debug("editor_settings already present in config.json.")
        else:
            logger.warning("DEFAULT_EDITOR_SETTINGS is not available, skipping editor_settings initialization in config.json.")

    def _initialize_default_ai_settings(self) -> None:
        """
        Initializes the 'ai_settings' in config.json if it doesn't exist.
        """
        if DEFAULT_AI_SETTINGS is not None:
            current_ai_settings: dict[str, Any] | None = self.load_setting('ai_settings')
            if current_ai_settings is None:
                logger.info("Initializing default ai_settings in config.json...")
                self.save_setting('ai_settings', DEFAULT_AI_SETTINGS)
            else:
                logger.debug("ai_settings already present in config.json.")
        else:
            logger.warning("DEFAULT_AI_SETTINGS is not available, skipping ai_settings initialization in config.json.")

    def _initialize_default_extension_map(self) -> None:
        """
        Initializes the 'extension_to_language_map' in config.json if it doesn't exist.
        """
        if DEFAULT_EXTENSION_TO_LANGUAGE_MAP is not None:
            current_map: dict[str, Any] | None = self.load_setting('extension_to_language_map')
            if current_map is None:
                logger.info("Initializing default extension_to_language_map in config.json...")
                self.save_setting('extension_to_language_map', DEFAULT_EXTENSION_TO_LANGUAGE_MAP)
            else:
                logger.debug("extension_to_language_map already present in config.json.")
        else:
            logger.warning("DEFAULT_EXTENSION_TO_LANGUAGE_MAP is not available, skipping its initialization in config.json.")

    def _get_config_path(self) -> str:
        """
        Constructs the path to the config.json file.
        Ensures the configuration directory exists.
        ~/.aether_editor/config.json
        """
        dir_path: str = os.path.join(os.path.expanduser('~'), '.aether_editor')
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, 'config.json')

    def _load_config_data(self) -> dict[str, Any]:
        """
        Reads the entire JSON configuration file.
        Handles file not found and JSON decode errors.
        """
        config_path: str = self._get_config_path()
        if not os.path.exists(config_path):
            logger.info(f"Config file not found at {config_path}. Returning empty data.")
            return {}
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data: dict[str, Any] = json.load(f)
            logger.debug(f"Config data loaded from {config_path}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {config_path}: {e}. Returning empty data.")
            return {}
        except IOError as e:
            logger.error(f"Error reading file {config_path}: {e}. Returning empty data.")
            return {}
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading config from {config_path}: {e}", exc_info=True)
            return {}

    def _save_config_data(self, data: dict[str, Any]) -> None:
        """
        Writes the given data dictionary to the JSON configuration file.
        Handles IOErrors during writing.
        """
        config_path: str = self._get_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.debug(f"Config data saved to {config_path}")
        except IOError as e:
            logger.error(f"Error writing config file to {config_path}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred while saving config to {config_path}: {e}", exc_info=True)

    def save_setting(self, key: str, value: Any) -> None:
        """
        Saves a specific setting (key-value pair) to the configuration file.
        """
        logger.info(f"Saving setting: '{key}' = '{str(value)[:50]}...'")
        data: dict[str, Any] = self._load_config_data()
        data[key] = value
        self._save_config_data(data)

    def load_setting(self, key: str, default_value: Any = None) -> Any:
        """
        Loads a specific setting by key from the configuration file.
        Returns the default_value if the key is not found.
        """
        data: dict[str, Any] = self._load_config_data()
        value: Any = data.get(key, default_value)
        if value is not default_value:
            logger.debug(f"Loaded setting: '{key}'")
        else:
            logger.debug(f"Setting '{key}' not found, returning default value.")
        return value

    def save_api_key(self, api_key: str) -> None:
        """
        Saves the API key using the generic save_setting method.
        """
        self.save_setting('api_key', api_key)
        logger.info("API key saved.")

    def load_api_key(self) -> str | None:
        """
        Loads the API key using the generic load_setting method.
        Returns the API key string if found, otherwise None.
        """
        api_key: str | None = self.load_setting('api_key', None)
        if api_key:
            logger.info("API key loaded.")
        else:
            logger.info("API key not found in config.")
        return api_key

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("Starting ConfigManager tests...")
    manager = ConfigManager()

    # Test generic settings
    logger.info("\nTesting generic save_setting and load_setting...")
    manager.save_setting('test_setting', 'test_value')
    loaded_setting: Any = manager.load_setting('test_setting')
    logger.info(f"Loaded test_setting: {loaded_setting}")
    assert loaded_setting == 'test_value'

    manager.save_setting('test_number', 123)
    loaded_number: Any = manager.load_setting('test_number')
    logger.info(f"Loaded test_number: {loaded_number}")
    assert loaded_number == 123

    loaded_nonexistent: Any = manager.load_setting('nonexistent_key', 'default_for_nonexistent')
    logger.info(f"Loaded nonexistent_key: {loaded_nonexistent}")
    assert loaded_nonexistent == 'default_for_nonexistent'

    # Test saving API key via new method
    test_key: str = "test_api_key_54321"
    logger.info(f"\nAttempting to save API key: {test_key}")
    manager.save_api_key(test_key)

    # Test loading API key via new method
    logger.info("\nAttempting to load API key...")
    loaded_key: str | None = manager.load_api_key()
    if loaded_key:
        logger.info(f"Loaded API key: {loaded_key}")
        assert loaded_key == test_key, "Mismatch between saved and loaded API key!"
    else:
        logger.error("Failed to load API key or key not set.")

    # Test loading when no key is present (by saving an empty dict or dict without api_key)
    logger.info("\nTesting loading API key when it's absent...")
    manager._save_config_data({'other_setting': 'some_value'})
    loaded_key = manager.load_api_key()
    logger.info(f"Loaded API key after removing 'api_key' field: {loaded_key}")
    assert loaded_key is None
    
    # Simulate corrupted JSON for _load_config_data
    logger.info("\nTesting _load_config_data with corrupted JSON...")
    config_file_path: str = manager._get_config_path()
    if os.path.exists(config_file_path):
        with open(config_file_path, 'w', encoding='utf-8') as f:
            f.write("this is not json")
    corrupted_data: dict[str, Any] = manager._load_config_data()
    logger.info(f"Data loaded after simulated corruption: {corrupted_data}")
    assert corrupted_data == {}

    # Test saving again to ensure it recovers
    logger.info(f"\nAttempting to save API key again: {test_key}")
    manager.save_api_key(test_key)
    loaded_key = manager.load_api_key()
    logger.info(f"Loaded API key after re-saving: {loaded_key}")
    assert loaded_key == test_key

    logger.info("\nConfigManager tests completed.")
    # Note: Test does not clean up the config file by default to allow inspection.
    # To clean up, uncomment the os.remove line in a real test suite.
    # config_file_path = manager._get_config_path()
    # if os.path.exists(config_file_path):
    #     os.remove(config_file_path)
    #     logger.info(f"Cleaned up test config file: {config_file_path}")

# Ensure a newline at the end of the file
