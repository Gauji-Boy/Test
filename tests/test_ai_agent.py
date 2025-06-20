import pytest
from unittest.mock import MagicMock, patch, ANY, PropertyMock

# Adjust import path as necessary
from ai_agent import GeminiAgent, GeminiAgentWorker, FALLBACK_AI_SETTINGS
from config_manager import ConfigManager # For mocking
from PySide6.QtCore import Signal, QObject # For signal mocking

# Mock the google.generativeai library
# We need to mock specific classes and functions used by AIAgent
mock_genai = MagicMock()
mock_genai.GenerativeModel = MagicMock()
mock_genai.ChatSession = MagicMock() # This might not be directly used if model.start_chat is mocked
mock_genai.types = MagicMock()
mock_genai.types.HarmCategory = MagicMock()
mock_genai.types.HarmBlockThreshold = MagicMock()
mock_genai.types.Part = MagicMock()
mock_genai.types.FunctionResponse = MagicMock()
mock_genai.types.GenerateContentResponse = MagicMock() # For typing if needed

# Simulate specific HarmCategory and HarmBlockThreshold members if they are accessed directly by name
for category in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]:
    setattr(mock_genai.types.HarmCategory, category, category) # Value can be the string itself for mock

for threshold in ["BLOCK_ONLY_HIGH", "BLOCK_NONE", "BLOCK_MEDIUM_AND_ABOVE", "BLOCK_LOW_AND_ABOVE"]:
    setattr(mock_genai.types.HarmBlockThreshold, threshold, threshold)


@pytest.fixture
def mock_config_manager_valid_ai_settings():
    cm = MagicMock(spec=ConfigManager)
    # Provide a valid-looking AI settings structure
    cm.load_setting.return_value = {
        "generation_config": {"temperature": 0.5},
        "safety_settings": {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_ONLY_HIGH",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_LOW_AND_ABOVE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
    }
    return cm

@pytest.fixture
def mock_qthreadpool():
    with patch('ai_agent.QThreadPool') as MockQThreadPool:
        mock_pool_instance = MockQThreadPool.return_value
        mock_pool_instance.start = MagicMock()
        yield mock_pool_instance

@patch('ai_agent.genai', mock_genai) # Patch the imported genai in ai_agent module
@patch('ai_agent.ConfigManager') # Patch ConfigManager where AIAgent imports it
def get_agent(mock_config_manager_constructor, api_key="test_api_key", valid_init=True):
    # This helper sets up mocks for a typical agent instantiation
    # Use the fixture for valid AI settings, or fallback for invalid
    mock_cm_instance_settings = mock_config_manager_valid_ai_settings().load_setting.return_value if valid_init else FALLBACK_AI_SETTINGS

    # Ensure the ConfigManager instance returns the desired settings
    # The constructor is mocked, so we configure its return_value's methods
    cm_instance_mock = mock_config_manager_constructor.return_value
    cm_instance_mock.load_setting.return_value = mock_cm_instance_settings

    mock_model_instance = MagicMock()
    mock_chat_session_instance = MagicMock()

    # Reset mocks for genai that might be called during initialization
    mock_genai.configure.reset_mock()
    mock_genai.GenerativeModel.reset_mock()
    mock_model_instance.start_chat.reset_mock()

    if valid_init and api_key: # Only setup successful genai mocks if simulating valid init
        mock_genai.configure = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model_instance
        mock_model_instance.start_chat.return_value = mock_chat_session_instance
    elif not api_key:
        # No specific genai call should happen if API key is missing before configure is called
        pass
    else: # Simulate other init error for genai.GenerativeModel
        mock_genai.configure = MagicMock() # Assume configure is fine
        mock_genai.GenerativeModel.side_effect = Exception("Model init error from mock")


    agent = GeminiAgent(api_key=api_key if api_key else "") # Pass empty if None to match constructor
    # Mock signals on the created agent instance for assertions
    agent.new_ai_message = MagicMock(spec=Signal)
    agent.tool_call_requested = MagicMock(spec=Signal)
    agent.error_occurred = MagicMock(spec=Signal)
    return agent, mock_model_instance, mock_chat_session_instance


class TestGeminiAgentInitialization:

    def test_initialization_success(self, mock_qthreadpool):
        agent, model, chat_session = get_agent()
        mock_genai.configure.assert_called_once_with(api_key="test_api_key")
        mock_genai.GenerativeModel.assert_called_once()
        model.start_chat.assert_called_once()
        assert agent.api_key_is_valid is True
        assert agent.model == model
        assert agent.chat_session == chat_session
        agent.error_occurred.emit.assert_not_called()

    def test_initialization_no_api_key(self, mock_qthreadpool):
        agent, _, _ = get_agent(api_key=None)
        assert agent.api_key_is_valid is False
        mock_genai.configure.assert_not_called()
        agent.error_occurred.emit.assert_called_with("API key is missing. GeminiAgent cannot be initialized.")


    def test_initialization_genai_error(self, mock_qthreadpool):
        agent, _, _ = get_agent(valid_init=False)
        assert agent.api_key_is_valid is False
        # Configure would be called, but GenerativeModel would fail
        mock_genai.configure.assert_called_once()
        agent.error_occurred.emit.assert_called_with("Gemini Agent initialization failed: Model init error from mock")

class TestGeminiAgentMessaging:

    @pytest.fixture
    def initialized_agent(self, mock_qthreadpool):
        agent, model, chat_session = get_agent() # This already mocks signals on the agent

        # The worker setup needs to be part of this fixture to ensure
        # that the AIAgent instance uses the patched worker.
        with patch('ai_agent.GeminiAgentWorker') as MockWorker:
            mock_worker_instance = MockWorker.return_value
            # Simulate the worker's signals structure
            mock_worker_instance.signals = QObject() # Create a QObject to hold dynamic signals
            mock_worker_instance.signals.new_message_received = MagicMock(spec=Signal)
            mock_worker_instance.signals.tool_call_requested = MagicMock(spec=Signal)
            mock_worker_instance.signals.error_occurred = MagicMock(spec=Signal)

            yield agent, model, chat_session, MockWorker, mock_worker_instance


    def test_send_message_success_text_response(self, initialized_agent, mock_qthreadpool):
        agent, _, chat_session, MockWorker, mock_worker_instance = initialized_agent
        user_text = "Hello AI"
        ai_response_text = "Hello User!"

        agent.send_message(user_text)

        MockWorker.assert_called_once_with(chat_session=chat_session, user_message_text=user_text, tool_response_part=None)
        mock_qthreadpool.start.assert_called_once_with(mock_worker_instance)

        # Simulate worker emitting new_message_received by calling the connected slot
        # The connection is made in AIAgent.send_message
        # We need to capture the slot connected to mock_worker_instance.signals.new_message_received
        # This is a bit indirect. A simpler way for testing is to assume the connection works
        # and directly call the agent's handler if the worker is fully mocked.
        # However, here we test the connection by triggering the mocked signal.

        # Assuming GeminiAgent connects its methods like _on_worker_new_message directly.
        # We can simulate the signal emission from the worker and check agent's reaction.
        mock_worker_instance.signals.new_message_received.emit(ai_response_text)
        # Manually call the slot if the signal connection is tricky to simulate directly
        # agent._on_worker_new_message(ai_response_text)


        agent.new_ai_message.emit.assert_called_once_with(ai_response_text)
        assert agent.chat_history[-2] == {'role': 'user', 'parts': [{'text': user_text}]}
        assert agent.chat_history[-1] == {'role': 'model', 'parts': [{'text': ai_response_text}]}

    def test_send_message_tool_call_request(self, initialized_agent, mock_qthreadpool):
        agent, _, chat_session, MockWorker, mock_worker_instance = initialized_agent
        user_text = "What's the weather?"
        tool_name = "get_weather"
        tool_args = {"location": "London"}

        agent.send_message(user_text)

        # Simulate worker emitting tool_call_requested
        mock_worker_instance.signals.tool_call_requested.emit(tool_name, tool_args)
        # agent._on_worker_tool_call_requested(tool_name, tool_args)

        agent.tool_call_requested.emit.assert_called_once_with(tool_name, tool_args)
        assert agent.chat_history[-1]['parts'][0]['function_call'] == {'name': tool_name, 'args': tool_args}


    def test_send_tool_response_success(self, initialized_agent, mock_qthreadpool):
        agent, _, chat_session, MockWorker, mock_worker_instance = initialized_agent
        tool_name = "get_weather"
        tool_result = {"temperature": "15C"}
        ai_final_response = "The weather is 15C."

        agent.chat_history.append({'role': 'model', 'parts': [{'function_call': {'name': tool_name, 'args': {}}}]})

        # Mock the Part creation, as it's an external type
        mock_created_part = MagicMock()
        mock_genai.types.Part.return_value = mock_created_part

        agent.send_tool_response(tool_name, tool_result, is_error=False)

        MockWorker.assert_called_once_with(chat_session=chat_session, user_message_text=None, tool_response_part=mock_created_part)
        mock_qthreadpool.start.assert_called_once_with(mock_worker_instance)

        # Simulate worker emitting new_message_received after tool response
        mock_worker_instance.signals.new_message_received.emit(ai_final_response)
        # agent._on_worker_new_message(ai_final_response)

        agent.new_ai_message.emit.assert_called_once_with(ai_final_response)
        assert agent.chat_history[-2]['parts'][0]['function_response']['name'] == tool_name
        assert agent.chat_history[-1]['parts'][0]['text'] == ai_final_response

    def test_send_message_worker_emits_error(self, initialized_agent, mock_qthreadpool):
        agent, _, _, MockWorker, mock_worker_instance = initialized_agent
        error_message = "Worker failed"

        agent.send_message("test")

        # Simulate worker emitting error
        mock_worker_instance.signals.error_occurred.emit(error_message)
        # agent._on_worker_error(error_message)

        agent.error_occurred.emit.assert_called_once_with(error_message)

# --- Tests for GeminiAgentWorker ---

@patch('ai_agent.genai', mock_genai)
def test_gemini_agent_worker_text_response():
    mock_chat_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "AI response text"
    # Simulate a valid candidates structure even if not strictly checked by worker for text
    mock_candidate = MagicMock()
    mock_candidate.content.parts = [] # No tool calls
    mock_response.candidates = [mock_candidate]

    mock_chat_session.send_message.return_value = mock_response

    worker = GeminiAgentWorker(chat_session=mock_chat_session, user_message_text="Hi")
    worker.signals = MagicMock(spec=GeminiAgentWorker.WorkerSignals) # Mock signals object

    worker.run()

    mock_chat_session.send_message.assert_called_once_with("Hi", stream=False)
    worker.signals.new_message_received.emit.assert_called_once_with("AI response text")
    worker.signals.tool_call_requested.emit.assert_not_called()
    worker.signals.error_occurred.emit.assert_not_called()


@patch('ai_agent.genai', mock_genai)
def test_gemini_agent_worker_tool_call():
    mock_chat_session = MagicMock()
    mock_response = MagicMock()

    mock_function_call_part = MagicMock()
    # Use PropertyMock for attributes that are themselves mocks with further attributes
    type(mock_function_call_part).function_call = PropertyMock()
    mock_function_call_part.function_call.name = "my_tool"
    mock_function_call_part.function_call.args = {"param": "value"}

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_function_call_part]
    mock_response.candidates = [mock_candidate]
    mock_response.text = None

    mock_chat_session.send_message.return_value = mock_response

    worker = GeminiAgentWorker(chat_session=mock_chat_session, user_message_text="Use tool")
    worker.signals = MagicMock(spec=GeminiAgentWorker.WorkerSignals)

    worker.run()

    worker.signals.tool_call_requested.emit.assert_called_once_with("my_tool", {"param": "value"})
    worker.signals.new_message_received.emit.assert_not_called()


@patch('ai_agent.genai', mock_genai)
def test_gemini_agent_worker_send_message_api_error():
    mock_chat_session = MagicMock()
    mock_chat_session.send_message.side_effect = Exception("API communication error")

    worker = GeminiAgentWorker(chat_session=mock_chat_session, user_message_text="Trigger error")
    worker.signals = MagicMock(spec=GeminiAgentWorker.WorkerSignals)

    worker.run()

    worker.signals.error_occurred.emit.assert_called_once_with("Error in AI communication: API communication error")

```
