from PySide6.QtCore import QObject, QRunnable, Signal, QThreadPool
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold # For safety settings

# Default Generation Config
DEFAULT_GENERATION_CONFIG = {
    "temperature": 0.7, # Adjusted for a balance of creativity and predictability
    "top_p": 0.95,       # Adjusted top_p
    "top_k": 40,        # Adjusted top_k
    "max_output_tokens": 2048, # Increased for potentially longer responses
}

# Default Safety Settings - blocking less to allow more responses for now
# Adjust these based on application requirements.
DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
}


class GeminiAgentWorkerSignals(QObject):
    """
    Defines signals for the GeminiAgentWorker.
    """
    new_message_received = Signal(str)  # Emits the AI's text response
    tool_call_requested = Signal(str, dict)  # Emits tool name and arguments
    error_occurred = Signal(str)  # Emits error messages


class GeminiAgentWorker(QRunnable):
    """
    Worker thread for handling Gemini API interactions.
    """
    def __init__(self, chat_session, user_message_text: str = None, tool_response_part=None):
        super().__init__()
        print(f"LOG: GeminiAgentWorker - __init__ called. User message: '{str(user_message_text)[:100]}...', Tool part: {tool_response_part}")
        self.signals = GeminiAgentWorkerSignals()
        self.chat_session = chat_session
        self.user_message_text = user_message_text
        self.tool_response_part = tool_response_part

    def run(self):
        print("LOG: GeminiAgentWorker - run method started.")
        try:
            response = None # Ensure response is defined
            if self.tool_response_part:
                print(f"LOG: GeminiAgentWorker - Sending tool response part: {self.tool_response_part}")
                print("LOG: GeminiAgentWorker - About to call chat_session.send_message (with tool response)")
                response = self.chat_session.send_message(self.tool_response_part)
                print(f"LOG: GeminiAgentWorker - Raw API response received (after tool response): {response}")
            elif self.user_message_text:
                print(f"LOG: GeminiAgentWorker - Sending user message: '{self.user_message_text[:100]}...'")
                print("LOG: GeminiAgentWorker - About to call chat_session.send_message (with user message)")
                response = self.chat_session.send_message(self.user_message_text)
                print(f"LOG: GeminiAgentWorker - Raw API response received (after user message): {response}")
            else:
                self.signals.error_occurred.emit("GeminiAgentWorker: Started without user message or tool response.")
                print("LOG: GeminiAgentWorker - ERROR: Worker started without user message or tool response.")
                return

            # Check for tool calls (as per Gemini API structure for function calling)
            # A response can have text AND a function call.
            # The model might say "Okay, I'll use the tool X" and then provide the function_call part.
            
            emitted_tool_call = False
            if response.candidates and \
               response.candidates[0].content and \
               response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call and part.function_call.name:
                        function_call = part.function_call
                        tool_name = function_call.name
                        tool_params = {key: value for key, value in function_call.args.items()}
                        print(f"LOG: GeminiAgentWorker - Emitting tool_call_requested. Name: {tool_name}, Params: {tool_params}")
                        self.signals.tool_call_requested.emit(tool_name, tool_params)
                        emitted_tool_call = True
                        break 

            if hasattr(response, 'text') and response.text:
                response_text = response.text # Ensure response_text is defined
                print(f"LOG: GeminiAgentWorker - Emitting new_message_received with text: '{response_text[:100]}...'")
                self.signals.new_message_received.emit(response_text)
            elif not emitted_tool_call: 
                print("LOG: GeminiAgentWorker - Response had no text and no tool call was emitted.")

            print("LOG: GeminiAgentWorker - run method finished processing.")

        except Exception as e:
            import traceback
            error_detail = f"{str(e)}\n{traceback.format_exc()}"
            print(f"LOG: GeminiAgentWorker - ERROR during run: {error_detail}")
            self.signals.error_occurred.emit(f"Error in AI communication: {str(e)}")


class GeminiAgent(QObject):
    """
    Manages interactions with the Gemini model and worker threads.
    """
    # Signals to forward from worker or for agent's own status
    new_ai_message = Signal(str)
    tool_call_requested = Signal(str, dict)
    error_occurred = Signal(str)

    def __init__(self, api_key: str, model_name="gemini-1.5-flash-latest", parent=None):
        super().__init__(parent)
        print(f"LOG: GeminiAgent - __init__ called with API key: '{api_key[:10]}...'")
        self.model_name = model_name
        self.chat_history = []
        self.model = None
        self.chat_session = None
        self.api_key_is_valid = False 

        if not api_key:
            msg = "API key is missing. GeminiAgent cannot be initialized."
            print(f"LOG: GeminiAgent - {msg}")
            self.error_occurred.emit(msg)
        else:
            try:
                print("LOG: GeminiAgent - Calling genai.configure")
                genai.configure(api_key=api_key)
                print("LOG: GeminiAgent - genai.configure successful.")
                
                print(f"LOG: GeminiAgent - Initializing model: {self.model_name}")
                self.model = genai.GenerativeModel(
                    self.model_name,
                    generation_config=DEFAULT_GENERATION_CONFIG,
                    safety_settings=DEFAULT_SAFETY_SETTINGS
                )
                print(f"LOG: GeminiAgent - Model initialized: {self.model}")
                
                print("LOG: GeminiAgent - Starting chat session.")
                self.chat_session = self.model.start_chat(history=self.get_formatted_history())
                print(f"LOG: GeminiAgent - Chat session started: {self.chat_session}")
                
                self.api_key_is_valid = True
                print("LOG: GeminiAgent - Initialization successful.")
            except Exception as e:
                self.api_key_is_valid = False
                import traceback
                error_detail = f"{str(e)}\n{traceback.format_exc()}"
                print(f"LOG: GeminiAgent - ERROR during __init__: {error_detail}")
                self.error_occurred.emit(f"Gemini Agent initialization failed: {str(e)}")

        self.thread_pool = QThreadPool()
        print(f"LOG: GeminiAgent - QThreadPool max threads: {self.thread_pool.maxThreadCount()}")

    def get_formatted_history(self):
        """Returns the chat history in the format expected by the Gemini API."""
        # Gemini API expects a list of Content objects (dictionaries)
        # [{'role': 'user', 'parts': [{'text': 'Hello'}]}, {'role': 'model', 'parts': [{'text': 'Hi there!'}]}]
        return self.chat_history


    def send_message(self, user_text: str):
        """
        Sends a user's message to the Gemini model via a worker thread.
        """
        print(f"LOG: GeminiAgent - send_message called with: '{user_text[:100]}...'")
        if not self.model or not self.chat_session or not self.api_key_is_valid:
            error_msg = "Gemini model/chat session not initialized or API key invalid. Cannot send message."
            self.error_occurred.emit(error_msg)
            print(f"LOG: GeminiAgent - ERROR in send_message: {error_msg}")
            return

        self.chat_history.append({'role': 'user', 'parts': [{'text': user_text}]})
        print(f"LOG: GeminiAgent - Added user message to history. Current history length for next call: {len(self.chat_history)}")
        
        worker = GeminiAgentWorker(chat_session=self.chat_session, user_message_text=user_text)
        print(f"LOG: GeminiAgent - Starting GeminiAgentWorker: {worker}")

        worker.signals.new_message_received.connect(self._handle_ai_response)
        worker.signals.tool_call_requested.connect(self._handle_tool_call_request) 
        worker.signals.error_occurred.connect(self.error_occurred) 

        self.thread_pool.start(worker)

    def _handle_ai_response(self, ai_text: str): # This handler is for text part of model's response
        """Handles new message from AI, adds to history, and emits signal."""
        self.chat_history.append({'role': 'model', 'parts': [{'text': ai_text}]})
        self.new_ai_message.emit(ai_text)
        print(f"LOG: GeminiAgent - AI text response processed and added to history. History length: {len(self.chat_history)}")

    def _handle_tool_call_request(self, tool_name: str, tool_args: dict): # This handler is for function_call part
        """Handles tool call request from AI, adds to history, and emits signal."""
        # Add the model's function call to history.
        # This is important so the model knows it made a call.
        self.chat_history.append({
            'role': 'model',
            'parts': [{'function_call': {'name': tool_name, 'args': tool_args}}]
        })
        self.tool_call_requested.emit(tool_name, tool_args)
        print(f"GeminiAgent: Tool call request for '{tool_name}' processed and added to history.")

    def add_tool_response_to_history(self, tool_name: str, response_data: dict, was_successful: bool = True):
        """
        Adds the result of a tool execution back to the chat history.
        This is crucial for the model to understand the outcome of the tool call.
        """
        # Gemini API expects a specific format for tool responses
        # See: https://ai.google.dev/docs/function_calling#provide_function_response
        tool_response_part = {
            "function_response": {
                "name": tool_name,
                "response": {
                    "name": tool_name, # Function name
                    "content": response_data, # Result of the function call
                }
            }
        }
        # If it was an error, the content might be structured differently, e.g. {"error": "message"}
        if not was_successful:
             tool_response_part["function_response"]["response"]["content"] = {"error": str(response_data)}


        self.chat_history.append({'role': 'user', 'parts': [tool_response_part]}) # Role is 'user' for function/tool responses
        print(f"GeminiAgent: Added tool response for '{tool_name}' to history. History length: {len(self.chat_history)}")

        # After adding the tool response, the chat history is updated.
        # The next call to send_message (likely triggered by the AIController)
        # will use this updated history to get the model's next response.
        # Example in AIController:
        # self.ai_agent.add_tool_response_to_history(...)
        # self.ai_agent.send_message("Proceed based on the tool's output.") or similar.
        # However, the send_tool_response below now triggers the next turn.

    def send_tool_response(self, tool_name: str, result: any, is_error: bool = False):
        """
        Sends the result of a tool execution back to the Gemini model and triggers
        the next turn of conversation from the AI.
        """
        if not self.chat_session:
            self.error_occurred.emit("Cannot send tool response: chat session not available.")
            return

        response_content_dict = {}
        if is_error:
            response_content_dict["error"] = str(result) # Ensure result is stringified for error
        else:
            # Gemini expects the 'content' for a tool response to be the actual result,
            # which could be a string, number, dict, etc.
            # The 'response' field in FunctionResponse should be a dict.
            # So, if result is a simple type, wrap it. If it's already a dict, use it.
            # Based on Gemini examples, it's usually a dict.
            if isinstance(result, dict):
                response_content_dict = result
            else:
                response_content_dict = {"result": result}


        tool_response_part_to_send = genai.types.Part(
            function_response=genai.types.FunctionResponse(
                name=tool_name,
                response=response_content_dict
            )
        )
        
        # Add this part to history before sending. The role is 'user' for function responses.
        self.chat_history.append({'role': 'user', 'parts': [tool_response_part_to_send.to_dict()]}) # Store the dict representation
        print(f"GeminiAgent: Added tool response for '{tool_name}' to history. History length: {len(self.chat_history)}")


        # The worker will send this tool_response_part and get the AI's next message.
        worker = GeminiAgentWorker(chat_session=self.chat_session,
                                     tool_response_part=tool_response_part_to_send)
        
        # Connect signals for this specific worker instance
        worker.signals.new_message_received.connect(self._handle_ai_response)
        worker.signals.tool_call_requested.connect(self._handle_tool_call_request)
        worker.signals.error_occurred.connect(self.error_occurred) # Forward general errors

        self.thread_pool.start(worker)
        print(f"GeminiAgent: Started GeminiAgentWorker to process response to tool call '{tool_name}'.")


if __name__ == '__main__':
    from PySide6.QtCore import QCoreApplication
    import sys
    import os # For environment variable

    # This test requires a GOOGLE_API_KEY environment variable to be set.
    # Example: export GOOGLE_API_KEY="YOUR_API_KEY"
    # Or pass it directly for testing if you modify the GeminiAgent call below.
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("Error: GOOGLE_API_KEY environment variable not set. Skipping GeminiAgent test.")
        sys.exit(0) # Exit gracefully if key is not set

    app = QCoreApplication(sys.argv)

    print(f"Using API Key: ...{google_api_key[-4:]}") # Print last 4 chars for confirmation
    agent = GeminiAgent(api_key=google_api_key)

    if not agent.api_key_is_valid: # Check if agent initialized correctly
        print("Agent initialization failed (likely API key or model issue). Exiting.")
        sys.exit(1)

    test_step = 1

    def on_new_message(msg):
        global test_step
        print(f"MAIN_TEST (AI Message): {msg}")
        if test_step == 1: # Response to "Hello AI!"
            test_step = 2
            print("\n--- Test 2: Ask for a tool use (hypothetical) ---")
            agent.send_message("What is the weather like in London?") # This might trigger a tool if model was trained for it
        elif test_step == 3: # Response after tool call
             print("\n--- Test 4: End of test ---")
             QThreadPool.globalInstance().waitForDone(2000)
             print("Final History:")
             for item in agent.get_formatted_history():
                 print(item)
             app.quit()


    def on_tool_call(name, args):
        global test_step
        print(f"MAIN_TEST (Tool Call Requested): {name} with args {args}")
        # Simulate tool execution and add response
        if name == "get_weather": # Example tool name
            response_content = {"city": args.get("city", "unknown"), "temperature": "15°C", "condition": "Cloudy"}
            agent.add_tool_response_to_history(name, response_content, was_successful=True)
            print(f"MAIN_TEST: Added tool response for '{name}'. Now sending this back to the model.")
            # Send a message to the agent to process the tool response
            # This message content isn't strictly necessary if the history is correctly managed by the chat session
            # but can sometimes help guide the model.
            # agent.send_message(f"Tool {name} executed. Here is the result.") # This is now handled by send_tool_response
            # The send_tool_response itself will trigger the next AI turn.
            test_step = 3
        else:
            print(f"MAIN_TEST: Unknown tool '{name}' requested. Sending error back.")
            # Use the new send_tool_response method with is_error=True
            agent.send_tool_response(name, {"error": "Unknown tool requested"}, is_error=True)
            test_step = 3


    def on_error(err_msg):
        print(f"MAIN_TEST (Error): {err_msg}")
        # app.quit() # Don't quit immediately on error during testing unless fatal

    agent.new_ai_message.connect(on_new_message)
    agent.tool_call_requested.connect(on_tool_call)
    agent.error_occurred.connect(on_error)

    print("\n--- Test 1: Simple message ---")
    agent.send_message("Hello AI!") # Start the conversation

    sys.exit(app.exec())
