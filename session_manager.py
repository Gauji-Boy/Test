import json
import os
from pathlib import Path

class SessionManager:
    def _get_config_path(self) -> Path:
        # Determine the user's config directory
        if os.name == 'nt':  # Windows
            config_dir = Path(os.getenv('APPDATA')) / 'AetherEditor'
        else:  # macOS, Linux
            config_dir = Path.home() / '.config' / 'AetherEditor'

        # Create the config directory if it doesn't exist
        config_dir.mkdir(parents=True, exist_ok=True)

        return config_dir / 'session.json'

    def save_session(self, state_dict: dict) -> None:
        config_path = self._get_config_path()
        try:
            with open(config_path, 'w') as f:
                json.dump(state_dict, f, indent=4)
        except IOError as e:
            # Handle potential I/O errors during save
            print(f"Error saving session: {e}")

    def load_session(self) -> dict:
        config_path = self._get_config_path()
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}
        except IOError as e:
            # Handle potential I/O errors during load
            print(f"Error loading session: {e}")
            return {}
