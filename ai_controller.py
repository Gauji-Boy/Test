from PySide6.QtCore import QObject, Slot

from ai_assistant_window import AIAssistantWindow
from ai_agent import GeminiAgent
import ai_tools as tools

class AIController(QObject):
    """
    Manages the AI assistant UI, the AI agent, and the communication between them
    and the main application.
    """
    def __init__(self, main_window=None, parent=None): # Added parent=None for QObject convention
        super().__init__(parent)
        self.main_window = main_window  # Reference to the main application window (optional)
        self.ai_agent = None  # Initialize ai_agent to None

        # Initialize AI Assistant Window
        # Pass main_window as parent if it's a QWidget, otherwise None
        # For QDialog, parent is usually a QWidget. If main_window is not, use None.
        # window_parent = main_window if isinstance(main_window, QWidget) else None # QWidget not imported here
        window_parent = main_window if hasattr(main_window, 'isWidgetType') and main_window.isWidgetType() else None
        self.ai_window = AIAssistantWindow(parent=window_parent)

        # Connect signals
        self._connect_signals()

    def _connect_signals(self):
        """Connects signals between UI, agent, and controller."""
        # UI to Controller
        self.ai_window.user_message_submitted.connect(self._handle_user_message)

        # Agent to Controller
        # Based on ai_agent.py, signals are directly on GeminiAgent instance
        # These will be connected if/when ai_agent is initialized.
        # self.ai_agent.new_ai_message.connect(self._handle_ai_message_received)
        # self.ai_agent.tool_call_requested.connect(self._handle_tool_call_requested)
        # self.ai_agent.error_occurred.connect(self._handle_error_occurred)
        
        # Connect AI Window signal for API key availability
        self.ai_window.api_key_available.connect(self._initialize_agent_with_key)
        
        print("LOG: AIController - __init__ complete. Signals connected. Waiting for API key.")

    def _initialize_agent_with_key(self, api_key: str):
        print(f"LOG: AIController - _initialize_agent_with_key called with API key: '{api_key[:10]}...'")
        if self.ai_agent: # If an old agent exists, clean it up (optional, depends on desired behavior)
            print("LOG: AIController - Disconnecting signals from old AI agent...")
            try:
                self.ai_agent.new_ai_message.disconnect(self._handle_ai_message_received)
                self.ai_agent.tool_call_requested.disconnect(self._handle_tool_call_requested)
                self.ai_agent.error_occurred.disconnect(self._handle_error_occurred)
            except RuntimeError as e: # Signals might not be connected if agent init failed previously
                 print(f"LOG: AIController - Error disconnecting signals (might be normal if agent wasn't fully up): {e}")
            self.ai_agent.deleteLater() # Schedule for deletion

        self.ai_agent = GeminiAgent(api_key=api_key, parent=self)
        print(f"LOG: AIController - GeminiAgent instance created: {self.ai_agent}")
        
        # Connect signals from the newly created agent
        self.ai_agent.new_ai_message.connect(self._handle_ai_message_received)
        self.ai_agent.tool_call_requested.connect(self._handle_tool_call_requested)
        self.ai_agent.error_occurred.connect(self._handle_error_occurred)
        print("LOG: AIController - GeminiAgent signals connected.")
        
        if self.ai_agent.api_key_is_valid: 
            # self.ai_window.add_message_to_history("System", "AI Agent initialized successfully and is ready.") # REMOVED
            print("LOG: AIController - GeminiAgent initialized successfully (api_key_is_valid is true).")
        else:
            # self.ai_window.add_message_to_history("System", "AI Agent initialization failed. Check API key or logs.") # REMOVED
            print("LOG: AIController - GeminiAgent initialization failed (api_key_is_valid is false).")


    def show_window(self):
        """Shows the AI assistant window."""
        self.ai_window.show()
        print("AIController: AI Assistant window shown.")

    @Slot(str)
    def _handle_user_message(self, message: str):
        """
        Handles user message submission from the AI window.
        Displays it and sends it to the AI agent.
        """
        print(f"LOG: AIController - _handle_user_message received: '{message[:100]}...'")
        if not self.ai_agent or not self.ai_agent.api_key_is_valid: 
            self.ai_window.add_message_to_history("Error", "AI Agent not initialized or API key invalid. Please set API Key via 'API Key Settings'.")
            print("LOG: AIController - Agent not ready or key invalid.")
            return
            
        print("LOG: AIController - Calling self.ai_agent.send_message")
        self.ai_agent.send_message(message)

    @Slot(str)
    def _handle_ai_message_received(self, response: str):
        """
        Handles new AI message from the agent and displays it in the UI.
        """
        print(f"LOG: AIController - _handle_ai_message_received: '{response[:100]}...'")
        self.ai_window.display_ai_response(response)

    @Slot(str, dict)
    def _handle_tool_call_requested(self, tool_name: str, tool_params: dict):
        """
        Handles a tool call request from the AI agent.
        """
        print(f"LOG: AIController - _handle_tool_call_requested: {tool_name}, Params: {tool_params}")
        
        tool_call_message = f"Attempting to use tool: {tool_name}(params={tool_params})"
        self.ai_window.add_message_to_history("System", tool_call_message)

        try:
            if hasattr(tools, tool_name):
                tool_function = getattr(tools, tool_name)
                # Note: The placeholder tools currently don't use MainWindow.
                # If they needed it, self.main_window would be passed.
                result = tool_function(**tool_params)
                
                result_display_message = f"Tool '{tool_name}' executed successfully." 
                # Avoid printing full result if it's very long or complex for the chat UI
                if isinstance(result, (str, int, float, bool)) or (isinstance(result, dict) and len(str(result)) < 100):
                    result_display_message += f" Result: {result}"
                else:
                    result_display_message += " Result (type: {type(result).__name__}) received."

                self.ai_window.add_message_to_history("System", result_display_message)
                print(f"AIController: Tool '{tool_name}' executed. Result: {result}")
                
                if self.ai_agent:
                    # The agent's add_tool_response_to_history and send_tool_response will handle history and next step.
                    self.ai_agent.send_tool_response(tool_name, result, is_error=False)
                else:
                    self.ai_window.add_message_to_history("Error", "Cannot send tool response, AI agent not available.")
            else:
                error_msg = f"Tool '{tool_name}' not found."
                self.ai_window.add_message_to_history("Error", error_msg)
                print(f"AIController: {error_msg}")
                if self.ai_agent:
                    self.ai_agent.send_tool_response(tool_name, {"error": error_msg}, is_error=True)
              
        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {str(e)}"
            self.ai_window.add_message_to_history("Error", error_msg)
            print(f"AIController: {error_msg}")
            if self.ai_agent:
                self.ai_agent.send_tool_response(tool_name, {"error": error_msg}, is_error=True)

    @Slot(str)
    def _handle_error_occurred(self, error_message: str):
        """
        Handles an error signal from the AI agent and displays it.
        """
        print(f"LOG: AIController - _handle_error_occurred: '{error_message[:200]}...'")
        self.ai_window.add_message_to_history("Error", error_message)


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    # Create a dummy main_window for testing if needed, or pass None
    # class DummyMainWindow(QWidget):
    #     def __init__(self):
    #         super().__init__()
    #         self.setWindowTitle("Dummy Main Window")
    # main_win = DummyMainWindow()

    controller = AIController(main_window=None) # Pass None if no actual main_window for this test
    controller.show_window()

    # Test message flow
    # Simulate user sending a message
    # controller.ai_window.user_input_lineedit.setText("Hello from test!")
    # controller.ai_window.send_button.click()

    # Simulate AI responding
    # controller.ai_agent.new_ai_message.emit("Hello user, I am AI (test).")

    # Simulate tool call
    # controller.ai_agent.tool_call_requested.emit("read_file", {"file_path": "test.txt"})
    
    # Simulate error
    # controller.ai_agent.error_occurred.emit("This is a test error from the agent.")

    sys.exit(app.exec())
