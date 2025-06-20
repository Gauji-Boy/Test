from PySide6.QtCore import QObject, QRunnable, Signal, QThreadPool
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerateContentResponse
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerateContentResponse
from google.generativeai.protos import Part as GenAiPart
import logging
from config_manager import ConfigManager
from typing import Any, Dict, List, Optional # Python 3.9+ can use built-in list, dict

logger = logging.getLogger(__name__)

# Fallback AI settings if config.json is missing or corrupted
FALLBACK_AI_SETTINGS: Dict[str, Any] = {
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

class GeminiAgentWorkerSignals(QObject):
    new_message_received: Signal = Signal(str)
    tool_call_requested: Signal = Signal(str, dict)
    error_occurred: Signal = Signal(str)

class GeminiAgentWorker(QRunnable):
    signals: GeminiAgentWorkerSignals
    chat_session: genai.ChatSession
    user_message_text: Optional[str]
    tool_response_part: Optional[GenAiPart]

    def __init__(self,
                 chat_session: genai.ChatSession,
                 user_message_text: Optional[str] = None,
                 tool_response_part: Optional[GenAiPart] = None) -> None:
        super().__init__()
        logger.info(f"GeminiAgentWorker initialized. User message: '{str(user_message_text)[:100]}...', Tool part: {tool_response_part}")
        self.signals = GeminiAgentWorkerSignals()
        self.chat_session = chat_session
        self.user_message_text = user_message_text
        self.tool_response_part = tool_response_part

    def run(self) -> None:
        logger.info("GeminiAgentWorker run method started.")
        try:
            response: Optional[GenerateContentResponse] = None
            if self.tool_response_part:
                logger.info(f"Sending tool response part: {self.tool_response_part}")
                response = self.chat_session.send_message(self.tool_response_part)
                logger.debug(f"Raw API response received (after tool response): {response}")
            elif self.user_message_text:
                logger.info(f"Sending user message: '{self.user_message_text[:100]}...'")
                response = self.chat_session.send_message(self.user_message_text)
                logger.debug(f"Raw API response received (after user message): {response}")
            else:
                err_msg: str = "GeminiAgentWorker: Started without user message or tool response."
                self.signals.error_occurred.emit(err_msg)
                logger.error(err_msg)
                return

            if not response: # Should not happen if one of the above branches was taken
                logger.error("GeminiAgentWorker: No response from send_message.")
                self.signals.error_occurred.emit("No response from AI model.")
                return

            emitted_tool_call: bool = False
            if response.candidates and \
               response.candidates[0].content and \
               response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call and part.function_call.name:
                        function_call = part.function_call
                        tool_name: str = function_call.name
                        tool_params: Dict[str, Any] = {key: value for key, value in function_call.args.items()}
                        logger.info(f"Emitting tool_call_requested. Name: {tool_name}, Params: {tool_params}")
                        self.signals.tool_call_requested.emit(tool_name, tool_params)
                        emitted_tool_call = True
                        break 

            if hasattr(response, 'text') and response.text:
                response_text: str = response.text
                logger.info(f"Emitting new_message_received with text: '{response_text[:100]}...'")
                self.signals.new_message_received.emit(response_text)
            elif not emitted_tool_call: 
                logger.info("Response had no text and no tool call was emitted.")

            logger.info("GeminiAgentWorker run method finished processing.")

        except Exception as e:
            import traceback
            error_detail: str = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"ERROR during GeminiAgentWorker run: {error_detail}")
            self.signals.error_occurred.emit(f"Error in AI communication: {str(e)}")


class GeminiAgent(QObject):
    new_ai_message: Signal = Signal(str)
    tool_call_requested: Signal = Signal(str, dict)
    error_occurred: Signal = Signal(str)

    model_name: str
    chat_history: List[Dict[str, Any]]
    model: Optional[genai.GenerativeModel]
    chat_session: Optional[genai.ChatSession]
    api_key_is_valid: bool
    thread_pool: QThreadPool

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash-latest", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        logger.info(f"GeminiAgent initializing with model: {model_name}, API key ending: '...{api_key[-4:] if api_key else 'N/A'}'")
        self.model_name = model_name
        self.chat_history = []
        self.model = None
        self.chat_session = None
        self.api_key_is_valid = False

        config_mgr = ConfigManager()
        loaded_ai_settings: Dict[str, Any] = config_mgr.load_setting('ai_settings', FALLBACK_AI_SETTINGS)

        gen_config: Dict[str, Any] = loaded_ai_settings.get("generation_config", FALLBACK_AI_SETTINGS["generation_config"])
        safety_settings_str_map: Dict[str, str] = loaded_ai_settings.get("safety_settings", FALLBACK_AI_SETTINGS["safety_settings"])

        safety_settings_for_api: Dict[HarmCategory, HarmBlockThreshold] = {}
        if isinstance(safety_settings_str_map, dict):
            for cat_str, threshold_str in safety_settings_str_map.items():
                try:
                    harm_cat_member: Optional[HarmCategory] = getattr(HarmCategory, cat_str, None)
                    harm_threshold_member: Optional[HarmBlockThreshold] = getattr(HarmBlockThreshold, threshold_str, None)
                    if harm_cat_member and harm_threshold_member:
                        safety_settings_for_api[harm_cat_member] = harm_threshold_member
                    else:
                        logger.warning(f"Invalid HarmCategory ('{cat_str}') or HarmBlockThreshold ('{threshold_str}') string in AI config. Skipping.")
                except Exception as e:
                    logger.warning(f"Error converting AI safety setting '{cat_str}': {threshold_str} - {e}", exc_info=True)
        else:
            logger.warning(f"AI safety settings in config is not a dictionary: {safety_settings_str_map}. Using empty safety settings.")

        if not api_key:
            msg: str = "API key is missing. GeminiAgent cannot be initialized."
            logger.error(msg)
            self.error_occurred.emit(msg)
        else:
            try:
                logger.debug("Configuring genai with API key.")
                genai.configure(api_key=api_key)
                logger.debug("genai.configure successful.")
                
                logger.info(f"Initializing Gemini model: {self.model_name}")
                self.model = genai.GenerativeModel(
                    self.model_name,
                    generation_config=gen_config,
                    safety_settings=safety_settings_for_api
                )
                logger.debug(f"Model initialized: {self.model}")
                
                logger.info("Starting chat session.")
                self.chat_session = self.model.start_chat(history=self.get_formatted_history())
                logger.debug(f"Chat session started: {self.chat_session}")
                
                self.api_key_is_valid = True
                logger.info("GeminiAgent initialization successful.")
            except Exception as e:
                self.api_key_is_valid = False
                import traceback
                error_detail: str = f"{str(e)}\n{traceback.format_exc()}"
                logger.error(f"ERROR during GeminiAgent __init__: {error_detail}")
                self.error_occurred.emit(f"Gemini Agent initialization failed: {str(e)}")

        self.thread_pool = QThreadPool()
        logger.debug(f"GeminiAgent QThreadPool max threads: {self.thread_pool.maxThreadCount()}")

    def get_formatted_history(self) -> List[Dict[str, Any]]:
        return self.chat_history

    def send_message(self, user_text: str) -> None:
        logger.info(f"send_message called with: '{user_text[:100]}...'")
        if not self.model or not self.chat_session or not self.api_key_is_valid:
            error_msg: str = "Gemini model/chat session not initialized or API key invalid. Cannot send message."
            self.error_occurred.emit(error_msg)
            logger.error(f"ERROR in send_message: {error_msg}")
            return

        self.chat_history.append({'role': 'user', 'parts': [{'text': user_text}]})
        logger.debug(f"Added user message to history. Current history length for next call: {len(self.chat_history)}")
        
        # Type for chat_session is already Optional[genai.ChatSession], so this check is for mypy
        if self.chat_session is None:
            logger.error("Cannot start worker, chat_session is None.") # Should not happen if api_key_is_valid
            return

        worker = GeminiAgentWorker(chat_session=self.chat_session, user_message_text=user_text)
        logger.debug(f"Starting GeminiAgentWorker: {worker}")

        worker.signals.new_message_received.connect(self._handle_ai_response)
        worker.signals.tool_call_requested.connect(self._handle_tool_call_request) 
        worker.signals.error_occurred.connect(self.error_occurred) 

        self.thread_pool.start(worker)

    def _handle_ai_response(self, ai_text: str) -> None:
        self.chat_history.append({'role': 'model', 'parts': [{'text': ai_text}]})
        self.new_ai_message.emit(ai_text)
        logger.info(f"AI text response processed and added to history. History length: {len(self.chat_history)}")

    def _handle_tool_call_request(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        logger.info(f"Tool call requested: {tool_name}, Args: {tool_args}")
        self.chat_history.append({
            'role': 'model',
            'parts': [{'function_call': {'name': tool_name, 'args': tool_args}}]
        })
        self.tool_call_requested.emit(tool_name, tool_args)
        logger.debug(f"Tool call for '{tool_name}' added to history.")

    def add_tool_response_to_history(self, tool_name: str, response_data: Dict[str, Any], was_successful: bool = True) -> None:
        tool_response_part_content: Dict[str, Any]
        if not was_successful:
            tool_response_part_content = {"error": str(response_data)}
        else:
            tool_response_part_content = response_data

        tool_response_part: Dict[str, Any] = {
            "function_response": {
                "name": tool_name,
                "response": { # This 'response' field itself is a dict
                    "name": tool_name,
                    "content": tool_response_part_content,
                }
            }
        }
        self.chat_history.append({'role': 'user', 'parts': [tool_response_part]})
        logger.info(f"Added tool response for '{tool_name}' to history. Success: {was_successful}. History length: {len(self.chat_history)}")

    def send_tool_response(self, tool_name: str, result: Any, is_error: bool = False) -> None:
        logger.info(f"Sending tool response for '{tool_name}'. Is error: {is_error}")
        if not self.chat_session:
            err_msg: str = "Cannot send tool response: chat session not available."
            logger.error(err_msg)
            self.error_occurred.emit(err_msg)
            return

        response_content_dict: Dict[str, Any] = {}
        if is_error:
            response_content_dict["error"] = str(result)
        else:
            if isinstance(result, dict):
                response_content_dict = result
            else:
                response_content_dict = {"result": result}

        tool_response_part_to_send: GenAiPart = genai.types.Part(
            function_response=genai.types.FunctionResponse(
                name=tool_name,
                response=response_content_dict
            )
        )
        
        self.chat_history.append({'role': 'user', 'parts': [tool_response_part_to_send.to_dict()]})
        logger.debug(f"Added tool response part for '{tool_name}' to history before sending. History length: {len(self.chat_history)}")

        worker = GeminiAgentWorker(chat_session=self.chat_session,
                                     tool_response_part=tool_response_part_to_send)
        
        worker.signals.new_message_received.connect(self._handle_ai_response)
        worker.signals.tool_call_requested.connect(self._handle_tool_call_request)
        worker.signals.error_occurred.connect(self.error_occurred)

        self.thread_pool.start(worker)
        logger.info(f"Started GeminiAgentWorker to process response to tool call '{tool_name}'.")


if __name__ == '__main__':
    from PySide6.QtCore import QCoreApplication
    import sys
    import os

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    google_api_key: Optional[str] = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        logger.error("GOOGLE_API_KEY environment variable not set. Skipping GeminiAgent test.")
        sys.exit(0)

    app = QCoreApplication(sys.argv)

    logger.info(f"Using API Key ending: ...{google_api_key[-4:]}")
    agent: GeminiAgent = GeminiAgent(api_key=google_api_key)

    if not agent.api_key_is_valid:
        logger.error("Agent initialization failed. Exiting.")
        sys.exit(1)

    test_step: int = 1

    def on_new_message(msg: str) -> None:
        global test_step
        logger.info(f"MAIN_TEST (AI Message): {msg}")
        if test_step == 1:
            test_step = 2
            logger.info("\n--- Test 2: Ask for a tool use (hypothetical) ---")
            agent.send_message("What is the weather like in London?")
        elif test_step == 3:
             logger.info("\n--- Test 4: End of test ---")
             QThreadPool.globalInstance().waitForDone(2000)
             logger.info("Final History:")
             for item in agent.get_formatted_history():
                 logger.info(item)
             app.quit()

    def on_tool_call(name: str, args: Dict[str, Any]) -> None:
        global test_step
        logger.info(f"MAIN_TEST (Tool Call Requested): {name} with args {args}")
        if name == "get_weather":
            response_content: Dict[str, Any] = {"city": args.get("city", "unknown"), "temperature": "15°C", "condition": "Cloudy"}
            logger.info(f"MAIN_TEST: Simulating tool execution for '{name}'.")
            agent.send_tool_response(name, response_content, is_error=False)
            test_step = 3
        else:
            logger.warning(f"MAIN_TEST: Unknown tool '{name}' requested. Sending error back.")
            agent.send_tool_response(name, {"error": "Unknown tool requested"}, is_error=True)
            test_step = 3

    def on_error(err_msg: str) -> None:
        logger.error(f"MAIN_TEST (Error): {err_msg}")

    agent.new_ai_message.connect(on_new_message)
    agent.tool_call_requested.connect(on_tool_call)
    agent.error_occurred.connect(on_error)

    logger.info("\n--- Test 1: Simple message ---")
    agent.send_message("Hello AI!")

    sys.exit(app.exec())
