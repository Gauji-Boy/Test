# config.py

RUNNER_CONFIG = {
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

DEFAULT_EDITOR_SETTINGS = {
    "auto_pairs": {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'", '<': '>'},
    "tab_stop_char_width_multiplier": 4, # For `4 * fontMetrics().averageCharWidth()`
    "linter_interval_ms": 700
}

DEFAULT_AI_SETTINGS = {
    "generation_config": {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 2048
    },
    "safety_settings": { # Store string representations of Enum members
        "HARM_CATEGORY_HARASSMENT": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
    }
}

DEFAULT_EXTENSION_TO_LANGUAGE_MAP = {
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