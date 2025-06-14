from PySide6.QtCore import QObject, Signal, Slot, QThread, QRunnable, QThreadPool, QMetaObject
import openai # Assuming use of OpenAI, will need configuration
import os
import time # For simulating network delay if used

# Add other necessary imports for specific AI tasks later, e.g., for different models or APIs

# --- AI Worker (for running OpenAI calls in a separate thread) ---
class AIWorker(QRunnable):
    def __init__(self, controller_instance, api_key: str, prompt: str, model: str = "gpt-3.5-turbo"):
        super().__init__()
        self.controller = controller_instance # Store reference to the controller
        self.api_key = api_key
        self.prompt = prompt
        self.model = model

    @Slot()
    def run(self):
        # This method contains the actual OpenAI API call.
        # For now, it's a placeholder/simulation.
        response_text = None
        error_message = None
        try:
            # Simulate API call setup
            if not self.api_key:
                raise ValueError("OpenAI API key not provided to worker.")

            # print(f"AIWorker: Simulating OpenAI call with prompt: '{self.prompt[:50]}...' for model {self.model}") # Debug
            # Simulate network delay
            # time.sleep(2) # Make sure 'time' is imported if using this

            # Placeholder: Replace with actual openai.ChatCompletion.create() or similar
            # For testing, we'll just echo the prompt or return a fixed response.
            if self.prompt.startswith("error_test"):
                raise Exception("Simulated API error")

            response_text = f"AI response to: '{self.prompt}'"
            # In a real scenario:
            # client = openai.OpenAI(api_key=self.api_key)
            # completion = client.chat.completions.create(
            #    model=self.model,
            #    messages=[{"role": "user", "content": self.prompt}]
            # )
            # response_text = completion.choices[0].message.content

        except ValueError as ve:
            error_message = str(ve)
        # except openai.APIError as apie: # openai might not be fully imported/mocked here
        #     error_message = f"OpenAI API Error: {apie}"
        except Exception as e:
            error_message = f"AI task failed: {e}"
        finally:
            # Call back to the main thread via the controller instance's slot
            # QMetaObject.invokeMethod ensures the slot is called in the controller's thread
            QMetaObject.invokeMethod(
                self.controller,
                "_process_worker_result",
                Qt.QueuedConnection, # Ensure it's queued to run in the controller's thread
                QGenericArgument("QString", response_text if response_text is not None else ""),
                QGenericArgument("QString", error_message if error_message is not None else "")
            )


class AIControllerRefactored(QObject):
    ai_response_received = Signal(str)
    ai_error_occurred = Signal(str)
    ai_task_started = Signal()
    ai_task_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)
        if not self.api_key:
            print("Warning: OPENAI_API_KEY environment variable not set. AI features may not work.")
            # No need to emit ai_error_occurred here, is_api_key_configured can be checked by UI

    def is_api_key_configured(self) -> bool:
        return bool(self.api_key)

    @Slot(str, str)
    def request_ai_completion(self, prompt: str, model: str = "gpt-3.5-turbo"):
        if not self.is_api_key_configured():
            self.ai_error_occurred.emit("AI API key is not configured.")
            self.ai_task_finished.emit() # Ensure task finished is emitted
            return
        if self.thread_pool.activeThreadCount() >= self.thread_pool.maxThreadCount():
            self.ai_error_occurred.emit("AI task queue is full. Please try again later.")
            self.ai_task_finished.emit() # Ensure task finished is emitted
            return

        self.ai_task_started.emit()
        # Pass 'self' (the controller instance) to the worker for the callback
        worker = AIWorker(self, self.api_key, prompt, model)
        self.thread_pool.start(worker)

    @Slot(list, str)
    def request_ai_chat_completion(self, messages: list, model: str = "gpt-3.5-turbo"):
        if not self.is_api_key_configured():
            self.ai_error_occurred.emit("AI API key is not configured.")
            self.ai_task_finished.emit() # Ensure task finished is emitted
            return
        if self.thread_pool.activeThreadCount() >= self.thread_pool.maxThreadCount():
            self.ai_error_occurred.emit("AI task queue is full. Please try again later.")
            self.ai_task_finished.emit() # Ensure task finished is emitted
            return

        simplified_prompt = ""
        if isinstance(messages, list) and all(isinstance(m, dict) and "content" in m for m in messages):
            simplified_prompt = " ".join([m["content"] for m in messages if "content" in m and m["content"]])
        else:
            self.ai_error_occurred.emit("Invalid format for messages in chat completion.")
            self.ai_task_finished.emit()
            return

        if not simplified_prompt.strip():
            self.ai_error_occurred.emit("Cannot process empty chat message list.")
            self.ai_task_finished.emit()
            return

        self.ai_task_started.emit()
        worker = AIWorker(self, self.api_key, simplified_prompt, model)
        self.thread_pool.start(worker)

    @Slot(str, str)
    def _process_worker_result(self, response_text: str, error_message: str):
        # Ensure that empty strings are treated as None for error/response logic
        effective_response = response_text if response_text else None
        effective_error = error_message if error_message else None

        if effective_error:
            self.ai_error_occurred.emit(effective_error)
        elif effective_response is not None:
            self.ai_response_received.emit(effective_response)
        else:
            self.ai_error_occurred.emit("AI task completed with no response and no error.")
        self.ai_task_finished.emit()

    @Slot(str)
    def explain_code_snippet(self, code_snippet: str):
        prompt = f"Explain the following code snippet:\n\n```\n{code_snippet}\n```"
        self.request_ai_completion(prompt)

    @Slot(str, str)
    def suggest_code_improvements(self, code_snippet: str, language: str):
        prompt = f"Suggest improvements for the following {language} code snippet:\n\n```\n{code_snippet}\n```"
        self.request_ai_completion(prompt)

    @Slot(str)
    def generate_code_from_query(self, natural_language_query: str):
        prompt = f"Generate Python code based on the following query: {natural_language_query}"
        self.request_ai_completion(prompt)

    def __del__(self):
        self.thread_pool.clear()
        self.thread_pool.waitForDone(-1)
