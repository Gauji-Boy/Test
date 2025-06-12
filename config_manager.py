import os
import json

class ConfigManager:
    """
    Manages the application's configuration, such as API keys,
    stored in a JSON file in the user's home directory.
    """

    def _get_config_path(self) -> str:
        """
        Constructs the path to the config.json file.
        Ensures the configuration directory exists.
        ~/.aether_editor/config.json
        """
        dir_path = os.path.join(os.path.expanduser('~'), '.aether_editor')
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, 'config.json')

    def save_api_key(self, api_key: str):
        """
        Saves the API key to the configuration file.
        """
        config_path = self._get_config_path()
        data = {}
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"ConfigManager: Error reading existing config file at {config_path}: {e}. Starting fresh.")
            data = {} # Start with an empty dict if file is corrupted or unreadable

        data['api_key'] = api_key

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            print(f"ConfigManager: API key saved to {config_path}")
        except IOError as e:
            print(f"ConfigManager: Error writing config file to {config_path}: {e}")

    def load_api_key(self) -> str | None:
        """
        Loads the API key from the configuration file.
        Returns the API key string if found, otherwise None.
        """
        config_path = self._get_config_path()

        if not os.path.exists(config_path):
            print(f"ConfigManager: Config file not found at {config_path}")
            return None

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            api_key = data.get('api_key')
            if api_key:
                print(f"ConfigManager: API key loaded from {config_path}")
            else:
                print(f"ConfigManager: 'api_key' not found in {config_path}")
            return api_key
        except json.JSONDecodeError as e:
            print(f"ConfigManager: Error decoding JSON from {config_path}: {e}")
            return None
        except IOError as e:
            print(f"ConfigManager: Error reading file {config_path}: {e}")
            return None
        except Exception as e: # Catch any other potential errors
            print(f"ConfigManager: An unexpected error occurred while loading API key: {e}")
            return None

if __name__ == '__main__':
    # Test the ConfigManager
    manager = ConfigManager()

    # Test saving
    test_key = "test_api_key_12345"
    print(f"\nAttempting to save API key: {test_key}")
    manager.save_api_key(test_key)

    # Test loading
    print("\nAttempting to load API key...")
    loaded_key = manager.load_api_key()
    if loaded_key:
        print(f"Loaded API key: {loaded_key}")
        assert loaded_key == test_key, "Mismatch between saved and loaded key!"
    else:
        print("Failed to load API key or key not set.")

    # Test loading when no key is present (first clear the file or save a different structure)
    print("\nTesting loading when API key might be absent or file corrupted...")
    config_file_path = manager._get_config_path()
    
    # Simulate corrupted JSON
    if os.path.exists(config_file_path):
        with open(config_file_path, 'w', encoding='utf-8') as f:
            f.write("this is not json")
    loaded_key = manager.load_api_key()
    print(f"Loaded API key after simulated corruption: {loaded_key}")
    assert loaded_key is None

    # Simulate file with no API key
    manager.save_api_key("another_key_temp") # Save normally first
    with open(config_file_path, 'r', encoding='utf-8') as f:
        temp_data = json.load(f)
    if 'api_key' in temp_data:
        del temp_data['api_key'] # Remove the key
        temp_data['other_setting'] = 'some_value'
        with open(config_file_path, 'w', encoding='utf-8') as f:
            json.dump(temp_data, f, indent=4) # Save without api_key
            
    loaded_key = manager.load_api_key()
    print(f"Loaded API key after removing 'api_key' field: {loaded_key}")
    assert loaded_key is None
    
    # Test saving again to ensure it recovers
    print(f"\nAttempting to save API key again: {test_key}")
    manager.save_api_key(test_key)
    loaded_key = manager.load_api_key()
    print(f"Loaded API key after re-saving: {loaded_key}")
    assert loaded_key == test_key

    # Clean up the test file
    # if os.path.exists(config_file_path):
    #     os.remove(config_file_path)
    #     print(f"\nCleaned up test config file: {config_file_path}")

    print("\nConfigManager tests completed.")
