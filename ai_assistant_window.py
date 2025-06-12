from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit, QPushButton, QInputDialog
from PySide6.QtCore import Signal, QTimer # Added QTimer
from PySide6.QtGui import QIcon # For optional icon setting

# Assuming config_manager.py is in the same directory or accessible in PYTHONPATH
try:
    from config_manager import ConfigManager
except ImportError:
    # Fallback for environments where direct import might fail (e.g. if not run as part of a package)
    # This assumes config_manager.py is in the same directory.
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from config_manager import ConfigManager
    # from markdown_renderer import render_markdown # Moved import to dedicated block

import html # Ensure html is imported at module level for robust fallback

# Enhanced import for markdown_renderer
try:
    from markdown_renderer import render_markdown
    print("LOG: AIAssistantWindow - Successfully imported render_markdown from markdown_renderer.")
    if not callable(render_markdown):
        print("LOG_ERROR: AIAssistantWindow - render_markdown imported from markdown_renderer is NOT CALLABLE. Using fallback.")
        # Fallback to a dummy version if not callable
        def render_markdown(text: str, error_source="Imported but not callable"):
            return f"<pre>{html.escape(text)}</pre>"
except ImportError as e_import:
    print(f"LOG_ERROR: AIAssistantWindow - FAILED to import render_markdown from markdown_renderer: {e_import}. Using fallback rendering function.")
    # Define the dummy render_markdown function if import fails
    def render_markdown(text: str, error_source="ImportError in AIAssistantWindow"):
        return f"<pre>{html.escape(text)}</pre>"
except Exception as e_general_import:
    print(f"LOG_ERROR: AIAssistantWindow - UNEXPECTED ERROR during import of render_markdown: {e_general_import}. Using fallback.")
    def render_markdown(text: str, error_source="Unexpected Import Error"):
        return f"<pre>{html.escape(text)}</pre>"


class AIAssistantWindow(QDialog):
    """
    A dialog window for the AI Assistant chat interface.
    """
    user_message_submitted = Signal(str)
    api_key_available = Signal(str) # New signal for when a key is confirmed available

    CSS_STYLES = """
    body {
        font-family: Segoe UI, sans-serif;
        font-size: 14px;
        line-height: 1.6;
        background-color: #2b2b2b; /* Dark background for the body of the text browser */
        color: #d3d3d3; /* Light grey text */
    }
    h1, h2, h3, h4, h5, h6 { /* Added h4, h5, h6 for completeness */
        color: #58a6ff; /* Light blue for headings */
        border-bottom: 1px solid #444;
        padding-bottom: 5px;
        margin-top: 10px; /* Added margin for spacing */
        margin-bottom: 5px; /* Added margin for spacing */
    }
    strong, b {
        color: #c9d1d9; /* Slightly brighter for emphasis */
    }
    em, i {
        color: #c9d1d9; /* Consistent emphasis color */
        font-style: italic;
    }
    ul, ol {
        padding-left: 20px;
        margin-top: 5px; /* Added margin */
        margin-bottom: 5px; /* Added margin */
    }
    li {
        margin-bottom: 4px; /* Spacing between list items */
    }
    p { /* Added paragraph styling */
        margin-top: 0px;
        margin-bottom: 8px; 
    }
    code { /* Styling for inline code */
        background-color: #1e1e1e;
        padding: 2px 4px;
        border-radius: 3px;
        font-family: Consolas, 'Courier New', monospace;
        font-size: 0.9em; /* Slightly smaller for inline */
        color: #ce9178; /* A common color for inline code */
    }
    /* This is the styling for the Pygments code block (div.highlight > pre) */
    /* Pygments usually wraps in <div class="highlight"><pre>...</pre></div> */
    div.highlight { 
        background: #1e1e1e; /* Background for the div container */
        padding: 10px;
        border-radius: 5px;
        margin-top: 5px;
        margin-bottom: 10px; /* Space around the code block */
        overflow-x: auto; /* Allow horizontal scrolling for long lines */
    }
    div.highlight > pre {
        background: transparent; /* Pre should be transparent if div has background */
        padding: 0; /* Reset padding if div.highlight handles it */
        margin: 0; /* Reset margin */
        font-family: Consolas, 'Courier New', monospace;
        font-size: 13px;
        line-height: 1.5;
        white-space: pre; /* Ensure preformatting is maintained */
        overflow-x: visible; /* Let div.highlight handle scrolling */
        /* Pygments will add its own color styles within this pre for tokens */
    }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Assistant")
        self.setGeometry(300, 300, 500, 400)

        self.main_layout = QVBoxLayout(self)

        # Chat history display
        self.chat_history_browser = QTextBrowser(self)
        self.chat_history_browser.setReadOnly(True)
        self.chat_history_browser.document().setDefaultStyleSheet(AIAssistantWindow.CSS_STYLES)
        self.main_layout.addWidget(self.chat_history_browser)

        # Input area layout (horizontal)
        self.input_layout = QHBoxLayout()

        # User input field
        self.user_input_lineedit = QLineEdit(self)
        self.user_input_lineedit.setPlaceholderText("Type your message here...")
        self.input_layout.addWidget(self.user_input_lineedit)

        # Send button
        self.send_button = QPushButton("Send", self)
        self.send_button.setIcon(QIcon.fromTheme("mail-send")) # Example icon
        self.send_button.clicked.connect(self._on_send_button_clicked)
        self.input_layout.addWidget(self.send_button)
        
        # API Key Button
        self.api_key_button = QPushButton("API Key Settings", self)
        self.api_key_button.setIcon(QIcon.fromTheme("configure")) # Example icon
        self.api_key_button.clicked.connect(self._prompt_for_api_key_slot)
        self.input_layout.addWidget(self.api_key_button)

        self.main_layout.addLayout(self.input_layout) # Add the horizontal layout to the main vertical layout
        self.setLayout(self.main_layout)
        
        self.config_manager = ConfigManager()
        self.current_api_key = None # Initialize attribute

        # Initial check for API key on startup
        self._on_key_updated() # Call this to set initial UI state based on stored key

        # --- SIMULATION HOOK FOR TESTING (DISABLED) ---
        # QTimer.singleShot(100, self._simulate_api_key_and_send_message)
        # --- END SIMULATION HOOK ---

    # def _simulate_api_key_and_send_message(self):
    #     print("LOG_SIMULATE: _simulate_api_key_and_send_message called.")
    #     if not self.current_api_key:
    #         print("LOG_SIMULATE: No current API key, simulating setting one.")
    #         self._simulate_prompt_for_api_key()
    #     QTimer.singleShot(100, self._simulate_send_message)

    # def _simulate_prompt_for_api_key(self):
    #     api_key = "TEST_API_KEY_FOR_LOGGING"
    #     ok = True
    #     print(f"LOG_SIMULATE: Simulating API key entry in _simulate_prompt_for_api_key with: {api_key}")
    #     if ok and api_key:
    #         self.config_manager.save_api_key(api_key)
    #         self.add_message_to_history("System", "API Key saved successfully (Simulated).")
    #         self._on_key_updated()
    #     elif ok and not api_key:
    #         self.config_manager.save_api_key("")
    #         self.add_message_to_history("System", "API Key cleared (Simulated).")
    #         self._on_key_updated()
    #     else:
    #         self.add_message_to_history("System", "API Key setup cancelled (Simulated).")

    # def _simulate_send_message(self):
    #     print("LOG_SIMULATE: _simulate_send_message called.")
    #     if self.user_input_lineedit.isEnabled():
    #         self.user_input_lineedit.setText("Hello AI, this is a test for logs.")
    #         self._on_send_button_clicked()
    #         print("LOG_SIMULATE: Simulated message sent.")
    #     else:
    #         print("LOG_SIMULATE: Could not send message, input is disabled. API key likely not processed in time or invalid.")


    def _prompt_for_api_key_slot(self):
        current_api_key = self.config_manager.load_api_key()
        api_key, ok = QInputDialog.getText(
            self,
            "API Key",
            "Enter your Google Gemini API Key:",
            QLineEdit.EchoMode.Password,
            current_api_key if current_api_key else ""
        )
        print(f"LOG: AIAssistantWindow - _prompt_for_api_key_slot: User provided API key, ok={ok}")
        if ok and api_key:
            self.config_manager.save_api_key(api_key)
            # self.add_message_to_history("System", "API Key saved successfully.") # Removed as per request
            self._on_key_updated()
        elif ok and not api_key:
            self.config_manager.save_api_key("")
            # self.add_message_to_history("System", "API Key cleared.") # Removed as per request
            self._on_key_updated()
        else:
            # self.add_message_to_history("System", "API Key setup cancelled.") # Removed as per request
            pass # No message for cancellation

    def _on_key_updated(self):
        self.current_api_key = self.config_manager.load_api_key()
        print(f"LOG: AIAssistantWindow - _on_key_updated: Current API key is '{self.current_api_key[:10] if self.current_api_key else None}'. UI Enabled: {bool(self.current_api_key)}")
        if self.current_api_key:
            self.user_input_lineedit.setEnabled(True)
            self.send_button.setEnabled(True)
            print(f"LOG: AIAssistantWindow - _on_key_updated: Emitting api_key_available with key '{self.current_api_key[:10]}...' via QTimer.")
            QTimer.singleShot(0, lambda: self.api_key_available.emit(self.current_api_key))
        else:
            self.user_input_lineedit.setEnabled(False)
            self.send_button.setEnabled(False)
            # self.add_message_to_history("System", "API Key is not set. Please use 'API Key Settings' to set your Google Gemini API key.") # Removed as per request

    def _on_send_button_clicked(self):
        """
        Handles the send button click event.
        Emits the user_message_submitted signal with the input text.
        """
        user_message = self.user_input_lineedit.text().strip()
        if user_message:
            print(f"LOG: AIAssistantWindow - Emitting user_message_submitted with: '{user_message[:100]}...'")
            self.user_message_submitted.emit(user_message)
            self.add_message_to_history("You", user_message) # Display user's message
            self.user_input_lineedit.clear()

    def add_message_to_history(self, sender: str, message: str):
        """
        Adds a message to the chat history browser.
        This is used for User messages and System messages which should be plain text (escaped).
        """
        # Escape the message content to prevent HTML injection from user/system messages
        import html
        escaped_message = html.escape(message)
        self.chat_history_browser.append(f"<b>{sender}:</b> {escaped_message}")
        self.chat_history_browser.ensureCursorVisible() # Scroll to the bottom

    def display_ai_response(self, response: str):
        """
        Displays the AI's response in the chat history, rendering it from Markdown to HTML.
        Includes detailed logging and error handling for the rendering process.
        """
        print(f"LOG: display_ai_response - Raw AI response received: '{response[:200]}...'")
        
        formatted_html = "" # Ensure formatted_html is defined
        try:
            # Ensure render_markdown is available (it would be the dummy if import failed)
            # The import for render_markdown is at the top of the file with a try-except block.
            # If it failed there, render_markdown would not be defined.
            if 'render_markdown' not in globals() and 'render_markdown' not in locals():
                import html # Ensure html is imported for fallback
                print("LOG_ERROR: display_ai_response - render_markdown function not found globally or locally!")
                # This error implies a problem with the import at the top of the file.
                # The fallback import within markdown_renderer itself might not have worked,
                # or markdown_renderer.py itself is missing.
                formatted_html = f"<p><b>AI Assistant (Render Setup Error):</b></p><pre>{html.escape(response)}</pre><p><small>Error: Markdown rendering function is not available.</small></p>"
            else:
                formatted_html = render_markdown(response) # Call the (potentially dummy) render_markdown
                
        except Exception as e:
            import traceback
            import html # Ensure html is imported for fallback
            error_str = traceback.format_exc()
            print(f"LOG_ERROR: display_ai_response - Error during render_markdown call: {error_str}")
            # Fallback to showing raw (escaped) response with error message
            formatted_html = f"<pre>{html.escape(response)}</pre>"
        
        print(f"LOG: display_ai_response - Formatted HTML (or fallback): '{formatted_html[:300]}...'")
        
        # Construct final HTML to append
        final_html_output = f"<p><b>AI Assistant:</b></p>{formatted_html}"
        # For consistency, the current final_html_output is fine.

        print("LOG: display_ai_response - About to append to chat_history_browser.")
        self.chat_history_browser.append(final_html_output)
        self.chat_history_browser.ensureCursorVisible()

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    ai_window = AIAssistantWindow()
    ai_window.show()
    sys.exit(app.exec())
