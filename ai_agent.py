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
        self.signals = GeminiAgentWorkerSignals()
        self.chat_session = chat_session
        self.user_message_text = user_message_text
        self.tool_response_part = tool_response_part

    def run(self):
        try:
            if self.tool_response_part:
                print(f"GeminiAgentWorker: Sending tool response to Gemini: {self.tool_response_part}")
                response = self.chat_session.send_message(self.tool_response_part)
            elif self.user_message_text:
                print(f"GeminiAgentWorker: Sending user message to Gemini: '{self.user_message_text[:50]}...'")
                response = self.chat_session.send_message(self.user_message_text)
            else:
                self.signals.error_occurred.emit("GeminiAgentWorker: Started without user message or tool response.")
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
                        # Convert FunctionCall.Args (which is a MapComposite) to a Python dict
                        tool_params = {key: value for key, value in function_call.args.items()}

                        self.signals.tool_call_requested.emit(tool_name, tool_params)
                        print(f"GeminiAgentWorker: Emitted tool_call_requested for '{tool_name}'")
                        emitted_tool_call = True
                        break # Assuming one tool call per response part for now

            # If there was a tool call, the model might also have explanatory text.
            # Or if no tool call, then it's a direct text response.
            # The response.text attribute usually contains the textual part of the response.
            if response.text:
                self.signals.new_message_received.emit(response.text)
                print(f"GeminiAgentWorker: Emitted new_message_received with text: {response.text[:50]}...")
            elif not emitted_tool_call:
                # This case might happen if there's no text and no tool call, which is unusual.
                # Or if the model only returns a tool call without any accompanying text part.
                print("GeminiAgentWorker: Response had no text and no tool call was emitted.")
                # Optionally, emit an empty message or a specific signal if this state needs handling.
                # self.signals.new_message_received.emit("") # Or handle as an error/unexpected response

            print("GeminiAgentWorker: Finished processing.")

        except Exception as e:
            # More specific error handling for API errors is good.
            # For example, google.api_core.exceptions.GoogleAPIError or specific genai errors
            error_msg = f"GeminiAgentWorker: API Error: {str(e)}"
            print(error_msg) # Log the error
            self.signals.error_occurred.emit(error_msg)


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
        self.model_name = model_name
        self.chat_history = []  # Stores {'role': 'user'/'model', 'parts': [content]}
                                # Content can be text or function call/response parts
        self.model = None
        self.chat_session = None
        self.api_key_is_valid = False # Flag to track API key validity

        if not api_key:
            msg = "API key is missing. GeminiAgent cannot be initialized."
            print(f"GeminiAgent: {msg}")
            self.error_occurred.emit(msg) # Emit error if key is missing
            # self.model and self.chat_session will remain None
        else:
            try:
                genai.configure(api_key=api_key)
                # TODO: Add tool function declarations here eventually
                # from ai_tools_specs import tool_declarations # Example
                # self.model = genai.GenerativeModel(
                #     self.model_name,
                #     generation_config=DEFAULT_GENERATION_CONFIG,
                #     safety_settings=DEFAULT_SAFETY_SETTINGS,
                #     tools=tool_declarations # Pass tool declarations here
                # )
                self.model = genai.GenerativeModel(
                    self.model_name,
                    generation_config=DEFAULT_GENERATION_CONFIG,
                    safety_settings=DEFAULT_SAFETY_SETTINGS
                    # tools will be added later if function calling is fully implemented
                )
                self.chat_session = self.model.start_chat(history=self.get_formatted_history())
                self.api_key_is_valid = True # Assume valid if no immediate error
                print(f"GeminiAgent: Initialized and configured GenerativeModel with {self.model_name}")
            except Exception as e:
                error_msg = f"GeminiAgent: Error initializing GenerativeModel or configuring API key: {e}"
                print(error_msg)
                self.error_occurred.emit(error_msg)
                # self.model and self.chat_session might be None or partially initialized

        self.thread_pool = QThreadPool()
        print(f"GeminiAgent: QThreadPool max threads: {self.thread_pool.maxThreadCount()}")

    def get_formatted_history(self):
        """Returns the chat history in the format expected by the Gemini API."""
        # Gemini API expects a list of Content objects (dictionaries)
        # [{'role': 'user', 'parts': [{'text': 'Hello'}]}, {'role': 'model', 'parts': [{'text': 'Hi there!'}]}]
        return self.chat_history


    def send_message(self, user_text: str):
        """
        Sends a user's message to the Gemini model via a worker thread.
        """
        if not self.model or not self.chat_session or not self.api_key_is_valid:
            error_msg = "Gemini model/chat session not initialized or API key invalid. Cannot send message."
            self.error_occurred.emit(error_msg)
            print(f"GeminiAgent: {error_msg}")
            return

        # Add user message to history before sending
        # Ensure history is compatible with what model.start_chat() and chat.send_message() expect
        self.chat_history.append({'role': 'user', 'parts': [{'text': user_text}]})
        # The chat_session should maintain its own history internally after being started.
        # Re-starting chat with updated history for every turn:
        # self.chat_session = self.model.start_chat(history=self.get_formatted_history())
        # For now, let's assume the existing self.chat_session updates its history.
        # If issues arise, explicitly managing history by restarting chat might be needed.

        print(f"GeminiAgent: Added user message to history. Current history length for next call: {len(self.chat_history)}")

        # Pass the current chat session and the user's text to the worker
        worker = GeminiAgentWorker(chat_session=self.chat_session, user_message_text=user_text)

        # Connect worker signals to agent's forwarding signals or internal slots
        worker.signals.new_message_received.connect(self._handle_ai_response) # Connect to the correct handler
        worker.signals.tool_call_requested.connect(self._handle_tool_call_request) # Renamed for clarity
        worker.signals.error_occurred.connect(self.error_occurred) # Forward directly

        self.thread_pool.start(worker)
        print(f"GeminiAgent: Started GeminiAgentWorker for user message: '{user_text[:50]}...'")

    def _handle_ai_response(self, ai_text: str):
        """Handles new message from AI, adds to history, and emits signal."""
        self.chat_history.append({'role': 'model', 'parts': [{'text': ai_text}]})
        self.new_ai_message.emit(ai_text)
        print(f"GeminiAgent: AI response processed. History length: {len(self.chat_history)}")

    def _handle_tool_call_request(self, tool_name: str, tool_args: dict):
        """Handles tool call request from AI and emits signal."""
        # The Gemini API expects the history to be an alternating sequence.
        # If the AI made a function call, the 'model' role part will contain that function_call.
        # We must not add that textual representation to history if it's already part of the structured call.
        # The worker now sends response.text, which should be the textual part.
        # If a tool call also occurred, that's handled by _handle_tool_call_request.
        self.chat_history.append({'role': 'model', 'parts': [{'text': ai_text}]})
        self.new_ai_message.emit(ai_text)
        print(f"GeminiAgent: AI text response processed. History length: {len(self.chat_history)}")

    def _handle_tool_call_request(self, tool_name: str, tool_args: dict):
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
