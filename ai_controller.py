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

        # Initialize AI Agent
        self.ai_agent = GeminiAgent(parent=self) # Set parent for QObject management

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
        # Based on ai_agent.py, signals are directly on GeminiAgent instance, not worker_signals
        self.ai_agent.new_ai_message.connect(self._handle_ai_message_received)
        self.ai_agent.tool_call_requested.connect(self._handle_tool_call_requested)
        self.ai_agent.error_occurred.connect(self._handle_error_occurred)

        print("AIController: Signals connected.")

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
        print(f"AIController: User message received: '{message[:50]}...'")
        # self.ai_window.add_message_to_history("User", message) # User message already added by UI
        self.ai_agent.send_message(message)

    @Slot(str)
    def _handle_ai_message_received(self, response: str):
        """
        Handles new AI message from the agent and displays it in the UI.
        """
        print(f"AIController: AI message received: '{response[:50]}...'")
        self.ai_window.display_ai_response(response) # Use the specific method from AIAssistantWindow

    @Slot(str, dict)
    def _handle_tool_call_requested(self, tool_name: str, tool_params: dict):
        """
        Handles a tool call request from the AI agent.
        (Placeholder: logs and displays in UI. Actual execution will be more complex).
        """
        print(f"AIController: Tool call requested: {tool_name} with params {tool_params}")

        # Display in UI
        tool_call_message = f"Attempting to use tool: {tool_name}(params={tool_params})"
        self.ai_window.add_message_to_history("System", tool_call_message)

        # Placeholder for actual tool execution logic
        try:
            if hasattr(tools, tool_name):
                tool_function = getattr(tools, tool_name)

                # Simplistic parameter passing; real implementation needs robust arg mapping
                if isinstance(tool_params, dict):
                    result = tool_function(**tool_params)
                else: # Or if params are not a dict, adapt as needed
                    result = tool_function(tool_params) # This might fail if params not simple string

                result_message = f"Tool '{tool_name}' executed. Result: {str(result)[:100]}..."
                self.ai_window.add_message_to_history("System", result_message)
                print(f"AIController: Tool '{tool_name}' executed with placeholder. Result: {result}")

                # Send the result back to the agent
                self.ai_agent.add_tool_response_to_history(tool_name, {"result": result}, was_successful=True)
                # After adding tool response, tell the agent to continue
                # This will make the agent process the tool's output and generate the next response.
                self.ai_agent.send_message("Okay, the tool execution is complete. What is the next step based on the tool's output?")


            else:
                error_msg = f"Tool '{tool_name}' not found in ai_tools.py."
                print(f"AIController: {error_msg}")
                self.ai_window.add_message_to_history("Error", error_msg)
                self.ai_agent.add_tool_response_to_history(tool_name, {"error": error_msg}, was_successful=False)
                self.ai_agent.send_message("There was an error trying to use that tool. Please advise.")


        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {e}"
            print(f"AIController: {error_msg}")
            self.ai_window.add_message_to_history("Error", error_msg)
            self.ai_agent.add_tool_response_to_history(tool_name, {"error": str(e)}, was_successful=False)
            self.ai_agent.send_message("There was an error during tool execution. Please advise.")


    @Slot(str)
    def _handle_error_occurred(self, error_message: str):
        """
        Handles an error signal from the AI agent and displays it.
        """
        print(f"AIController: Error received: {error_message}")
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
