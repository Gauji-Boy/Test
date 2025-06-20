"""
config.py

This module defines default configuration values for the Aether Editor.
These defaults are used by `ConfigManager` to populate the user's
`config.json` if specific settings are not already present or if the
config file is created for the first time.
"""
from typing import List, Dict, Any, Union

# --- Runner Configuration ---
# Defines commands for running and debugging different programming languages.
# Each language maps to a dictionary with "run" and "debug" keys,
# which in turn map to a list of command arguments.
# Placeholders like {file}, {class_name}, {output_file} are substituted at runtime.
RUNNER_CONFIG: Dict[str, Dict[str, List[str]]] = {
    "Python": {
        "run": ["python", "-u", "{file}"],
        "debug": ["python", "-m", "pdb", "{file}"]
    },
    "JavaScript": {
        "run": ["node", "{file}"],
        "debug": ["node", "--inspect-brk", "{file}"] # Placeholder for future implementation
    },
    "Java": {
        "run": ["javac", "{file}", "&&", "java", "{class_name}"],
        "debug": ["java", "-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5005", "{class_name}"] # Placeholder
    },
    "C++": {
        "run": ["g++", "{file}", "-o", "{output_file}", "&&", "{output_file}"],
        "debug": ["gdb", "{output_file}"] # Placeholder
    },
    "C": {
        "run": ["gcc", "{file}", "-o", "{output_file}", "&&", "{output_file}"],
        "debug": ["gdb", "{output_file}"] # Placeholder
    },
    "Ruby": {
        "run": ["ruby", "{file}"],
        "debug": ["ruby", "-r", "debug", "{file}"] # Placeholder
    }
}

# --- File Paths ---
# Default path for the editor's theme configuration file.
# Assumed relative to the application's root or a known config directory.
DEFAULT_THEME_FILE_PATH: str = "config/theme.json"

# --- Editor Settings ---
# Default settings for the code editor behavior and appearance.
DEFAULT_EDITOR_SETTINGS: Dict[str, Union[Dict[str, str], int, bool]] = {
    "auto_pairs": {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'", '<': '>'}, # Dict[str, str]
    "tab_stop_char_width_multiplier": 4, # int: Multiplier for average character width for tab stops
    "linter_interval_ms": 700 # int: Delay in milliseconds for the linter
}

# --- AI Assistant Settings ---
# Default configuration for the AI agent, including generation parameters
# and safety settings for content generation.
DEFAULT_AI_SETTINGS: Dict[str, Dict[str, Any]] = {
    "generation_config": { # Dict[str, Union[float, int]]
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 2048
    },
    "safety_settings": { # Dict[str, str]: String representations of HarmBlockThreshold enum members
        "HARM_CATEGORY_HARASSMENT": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
    }
}

# --- Language Mapping ---
# Default mapping from file extensions to programming language names.
# Used for syntax highlighting and potentially other language-specific features.
DEFAULT_EXTENSION_TO_LANGUAGE_MAP: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".cpp": "C++",
    ".cxx": "C++",
    ".c": "C",
    ".java": "Java",
    ".html": "HTML",
    ".css": "CSS",
    ".json": "JSON",
    ".xml": "XML",
    ".md": "Markdown",
    ".txt": "Plain Text",
    ".sh": "Shell Script",
    ".rb": "Ruby"
    # Add any other mappings that were in MainWindow or commonly used
}

# --- Main Window UI Defaults ---
# Default title and geometry (x, y, width, height) for the main application window.
DEFAULT_MAIN_WINDOW_TITLE: str = "Aether Editor"
DEFAULT_MAIN_WINDOW_GEOMETRY: List[int] = [100, 100, 1200, 800] # x, y, width, height

# --- User Session Defaults ---
# Default limit for the number of recent projects stored.
DEFAULT_RECENT_PROJECTS_LIMIT: int = 10

# --- Font Defaults ---
# Default font family and size for the code editor and interactive terminal.
DEFAULT_EDITOR_FONT_FAMILY: str = "Consolas"
DEFAULT_EDITOR_FONT_SIZE: int = 10
DEFAULT_TERMINAL_FONT_FAMILY: str = "Consolas"
DEFAULT_TERMINAL_FONT_SIZE: int = 10

# --- UI Component Defaults ---
# Default items for the language selector dropdown in the toolbar.
DEFAULT_LANGUAGE_SELECTOR_ITEMS: List[str] = ["Plain Text", "Python", "JavaScript", "HTML", "CSS", "JSON"]

# Default dimensions for editor gutter components.
DEFAULT_LINE_NUMBER_AREA_PADDING: int = 10 # Total padding (horizontal) for width calculation
DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING: int = 5 # Right-side padding for the line number text
DEFAULT_BREAKPOINT_GUTTER_WIDTH: int = 16 # Fixed width for the breakpoint gutter area
