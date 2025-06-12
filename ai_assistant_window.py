# Add to imports: 
from PySide6.QtCore import Signal, Slot

# Add these methods to AIAssistantWindow class:
    @Slot(str)
    def append_message_to_history(self, message: str):
        self.chat_history_browser.append(message)

    @Slot(str)
    def show_tool_call_activity(self, activity_message: str):
        self.chat_history_browser.append(f"<i>{activity_message}</i>")

    @Slot(str)
    def display_error(self, error_message: str):
        self.chat_history_browser.append(f"<font color='red'><b>Error:</b> {error_message}</font>")
