from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QLineEdit, QPushButton
from PySide6.QtCore import Signal

class AIAssistantWindow(QDialog):
    """
    A dialog window for the AI Assistant chat interface.
    """
    user_message_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Assistant")
        self.setGeometry(300, 300, 500, 400)

        self.layout = QVBoxLayout(self)

        # Chat history display
        self.chat_history_browser = QTextBrowser(self)
        self.chat_history_browser.setReadOnly(True)
        self.layout.addWidget(self.chat_history_browser)

        # User input field
        self.user_input_lineedit = QLineEdit(self)
        self.user_input_lineedit.setPlaceholderText("Type your message here...")
        self.layout.addWidget(self.user_input_lineedit)

        # Send button
        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self._on_send_button_clicked)
        self.layout.addWidget(self.send_button)

        self.setLayout(self.layout)

    def _on_send_button_clicked(self):
        """
        Handles the send button click event.
        Emits the user_message_submitted signal with the input text.
        """
        user_message = self.user_input_lineedit.text().strip()
        if user_message:
            self.user_message_submitted.emit(user_message)
            self.add_message_to_history("You", user_message) # Display user's message
            self.user_input_lineedit.clear()

    def add_message_to_history(self, sender: str, message: str):
        """
        Adds a message to the chat history browser.
        """
        self.chat_history_browser.append(f"<b>{sender}:</b> {message}")

    def display_ai_response(self, response: str):
        """
        Displays the AI's response in the chat history.
        """
        self.add_message_to_history("AI Assistant", response)

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    ai_window = AIAssistantWindow()
    ai_window.show()
    sys.exit(app.exec())
