import pytest
from unittest.mock import MagicMock, patch, ANY

# Adjust import path as necessary
from ai_controller import AIController
# Mock classes that AIController interacts with
from ai_assistant_window import AIAssistantWindow
from ai_agent import GeminiAgent
# Mock the actual tool functions
import ai_tools
from PySide6.QtCore import Signal # For specing signals

@pytest.fixture
def mock_main_window_for_aic(): # AIC needs a main_window ref for dialog parent
    mw = MagicMock()
    # Mock any attributes of main_window that AIController might access, if any
    # For now, a generic MagicMock might suffice if it's just for parenting dialogs.
    return mw

@pytest.fixture
def mock_ai_assistant_window():
    # This will be patched during AIController instantiation
    # but we can define a fixture for it if we need to make assertions on it later.
    # For now, patching at instantiation is simpler.
    pass

@pytest.fixture
def mock_gemini_agent():
    # Similar to AIAssistantWindow, this is patched at AIController instantiation.
    # The mock instance will be available via the patch object.
    pass

@patch('ai_controller.AIAssistantWindow')
@patch('ai_controller.GeminiAgent')
@patch.dict('os.environ', {'GOOGLE_API_KEY': 'fake_key'}) # Ensure API key env var is set for agent init
def aic_fixture(MockGeminiAgent, MockAIAssistantWindow, mock_main_window_for_aic):
    # This fixture provides an AIController instance with mocked dependencies
    mock_agent_instance = MockGeminiAgent.return_value
    mock_agent_instance.api_key_is_valid = True # Assume valid key for controller tests
    # Mock signals on the agent instance
    # Use spec=Signal for stricter mocking if PySide6.QtCore.Signal is appropriate
    mock_agent_instance.new_ai_message = MagicMock(spec=Signal)
    mock_agent_instance.tool_call_requested = MagicMock(spec=Signal)
    mock_agent_instance.error_occurred = MagicMock(spec=Signal)

    mock_window_instance = MockAIAssistantWindow.return_value
    # Mock methods on the window instance that AIController calls
    mock_window_instance.append_message = MagicMock()
    mock_window_instance.set_input_enabled = MagicMock()
    mock_window_instance.show_tool_call_indicator = MagicMock()
    mock_window_instance.hide_tool_call_indicator = MagicMock()
    mock_window_instance.get_api_key_from_user = MagicMock(return_value="user_provided_key")
    # Mock signals from the window instance
    mock_window_instance.send_button_clicked = MagicMock(spec=Signal)
    mock_window_instance.api_key_submitted = MagicMock(spec=Signal)


    controller = AIController(main_window=mock_main_window_for_aic)

    # The actual agent and window instances are controller.agent and controller.window
    # MockGeminiAgent and MockAIAssistantWindow are the mock *classes*
    # controller.agent is mock_agent_instance
    # controller.window is mock_window_instance

    return controller, mock_agent_instance, mock_window_instance


class TestAIControllerInitialization:

    def test_controller_initialization_with_api_key(self, aic_fixture, mock_main_window_for_aic):
        # Test case where GOOGLE_API_KEY is present
        controller, agent, window = aic_fixture

        # AIController constructor should have been called by the fixture
        # Check that GeminiAgent was initialized (implicitly, agent instance exists)
        assert controller.agent is not None
        assert controller.agent.api_key_is_valid is True # As set in fixture

        # Check that AIAssistantWindow was initialized and signals connected
        assert controller.window is not None
        controller.window.send_button_clicked.connect.assert_called_with(controller._handle_send_message)
        controller.window.api_key_submitted.connect.assert_called_with(controller._handle_api_key_submission)

        # Check agent signals connected
        controller.agent.new_ai_message.connect.assert_called_with(controller._handle_new_ai_message)
        controller.agent.tool_call_requested.connect.assert_called_with(controller._handle_tool_call_request)
        controller.agent.error_occurred.connect.assert_called_with(controller._handle_agent_error)

    @patch('ai_controller.AIAssistantWindow')
    @patch('ai_controller.GeminiAgent')
    @patch.dict('os.environ', {}, clear=True) # No GOOGLE_API_KEY
    def test_controller_initialization_no_api_key_prompts_user(
            self, MockGeminiAgentNoKey, MockAIAssistantWindowNoKey, mock_main_window_for_aic):

        mock_agent_instance_no_key = MockGeminiAgentNoKey.return_value
        mock_agent_instance_no_key.api_key_is_valid = False # Simulate agent knows key is missing
        # Mock signals for this agent instance
        mock_agent_instance_no_key.new_ai_message = MagicMock(spec=Signal)
        mock_agent_instance_no_key.tool_call_requested = MagicMock(spec=Signal)
        mock_agent_instance_no_key.error_occurred = MagicMock(spec=Signal)


        mock_window_instance_no_key = MockAIAssistantWindowNoKey.return_value
        mock_window_instance_no_key.get_api_key_from_user.return_value = None # User cancels
        # Mock signals for this window instance
        mock_window_instance_no_key.send_button_clicked = MagicMock(spec=Signal)
        mock_window_instance_no_key.api_key_submitted = MagicMock(spec=Signal)


        controller = AIController(main_window=mock_main_window_for_aic)

        assert controller.agent is not None # Agent is still created
        assert controller.agent.api_key_is_valid is False
        controller.window.get_api_key_from_user.assert_called_once()
        # If user cancels, agent should not be re-initialized with new key
        assert MockGeminiAgentNoKey.call_count == 1 # Initial call only


class TestAIControllerUserInteractions:

    def test_handle_send_message(self, aic_fixture):
        controller, agent, window = aic_fixture
        user_message = "Tell me a joke"
        window.get_input_text.return_value = user_message # User types this
        window.clear_input = MagicMock()

        controller._handle_send_message()

        window.append_message.assert_called_with(user_message, is_user=True)
        window.clear_input.assert_called_once()
        agent.send_message.assert_called_once_with(user_message)
        window.set_input_enabled.assert_called_with(False) # Input disabled while waiting

    def test_handle_api_key_submission_valid_key(self, aic_fixture):
        controller, old_agent, window = aic_fixture
        new_api_key = "new_valid_key"

        # Mock the re-initialization of GeminiAgent
        # The controller creates a new agent instance.
        with patch('ai_controller.GeminiAgent') as MockNewGeminiAgent:
            new_mock_agent_instance = MockNewGeminiAgent.return_value
            new_mock_agent_instance.api_key_is_valid = True # Simulate new key is valid
            # Mock signals for the new agent instance
            new_mock_agent_instance.new_ai_message = MagicMock(spec=Signal)
            new_mock_agent_instance.tool_call_requested = MagicMock(spec=Signal)
            new_mock_agent_instance.error_occurred = MagicMock(spec=Signal)


            controller._handle_api_key_submission(new_api_key)

            MockNewGeminiAgent.assert_called_once_with(api_key=new_api_key, model_name=ANY, parent=controller)
            assert controller.agent == new_mock_agent_instance # Agent should be updated
            # Signals should be reconnected to the new agent
            new_mock_agent_instance.new_ai_message.connect.assert_called_with(controller._handle_new_ai_message)
            new_mock_agent_instance.tool_call_requested.connect.assert_called_with(controller._handle_tool_call_request)
            new_mock_agent_instance.error_occurred.connect.assert_called_with(controller._handle_agent_error)


            window.append_message.assert_any_call("API Key accepted.", is_user=False) # Check for this message
            window.set_input_enabled.assert_called_with(True)


class TestAIControllerAgentSignalHandling:

    def test_handle_new_ai_message(self, aic_fixture):
        controller, agent, window = aic_fixture
        ai_message = "Here's a joke..."

        controller._handle_new_ai_message(ai_message)

        window.append_message.assert_called_with(ai_message, is_user=False)
        window.set_input_enabled.assert_called_with(True)
        window.hide_tool_call_indicator.assert_called_once()


    @patch('ai_tools.execute_tool') # Mock the actual tool execution function
    def test_handle_tool_call_request_known_tool_success(self, mock_execute_tool, aic_fixture):
        controller, agent, window = aic_fixture
        tool_name = "get_current_file_content"
        tool_args = {}
        tool_result = "print('Hello from file')"

        mock_execute_tool.return_value = tool_result # Simulate successful tool execution

        controller._handle_tool_call_request(tool_name, tool_args)

        window.show_tool_call_indicator.assert_called_with(f"Executing tool: {tool_name}...")
        mock_execute_tool.assert_called_once_with(tool_name, tool_args, main_window=ANY)
        agent.send_tool_response.assert_called_once_with(tool_name, tool_result, is_error=False)
        # hide_tool_call_indicator is called by _handle_new_ai_message after agent responds to tool result.

    @patch('ai_tools.execute_tool')
    def test_handle_tool_call_request_known_tool_failure(self, mock_execute_tool, aic_fixture):
        controller, agent, window = aic_fixture
        tool_name = "get_current_file_content"
        tool_args = {}
        # error_result = {"error": "File not open"} # This would be if tool returns structured error

        mock_execute_tool.side_effect = Exception("Tool execution failed")

        controller._handle_tool_call_request(tool_name, tool_args)

        agent.send_tool_response.assert_called_once_with(tool_name, "Error executing tool get_current_file_content: Tool execution failed", is_error=True)


    def test_handle_tool_call_request_unknown_tool(self, aic_fixture):
        controller, agent, window = aic_fixture
        tool_name = "unknown_fantasy_tool"
        tool_args = {}

        controller._handle_tool_call_request(tool_name, tool_args)

        expected_error_message = f"Unknown tool requested: {tool_name}"
        # This message is sent back to the AI, not necessarily appended directly to window by controller for unknown tool.
        # The AI might respond with this error, which then gets appended.
        # window.append_message.assert_called_with(f"Error: {expected_error_message}", is_user=False)
        agent.send_tool_response.assert_called_once_with(tool_name, expected_error_message, is_error=True)


    def test_handle_agent_error(self, aic_fixture):
        controller, agent, window = aic_fixture
        error_message = "AI API limit reached"

        controller._handle_agent_error(error_message)

        window.append_message.assert_called_with(f"AI Error: {error_message}", is_user=False)
        window.set_input_enabled.assert_called_with(True) # Re-enable input on error
        window.hide_tool_call_indicator.assert_called_once()

```
