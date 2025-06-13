from PySide6.QtWidgets import QPlainTextEdit, QCompleter, QApplication, QTextEdit, QWidget, QHBoxLayout
from PySide6.QtGui import QTextCharFormat, QColor, QTextCursor, QKeyEvent, QFont, QSyntaxHighlighter, QPainter
from PySide6.QtCore import Qt, QTimer, QStringListModel, QRect, QRegularExpression, QFileInfo, Signal, Slot, QPoint
import json
import os
import sys
from PySide6.QtCore import QThreadPool # Import QThreadPool

# Import worker threads
from worker_threads import JediCompletionWorker, PyflakesLinterWorker, WorkerSignals

from python_highlighter import PythonHighlighter # Import the dedicated highlighter

class BreakpointGutter(QWidget):
    breakpoint_toggled = Signal(int)

    def __init__(self, text_edit_widget):
        super().__init__(text_edit_widget) # Pass parent
        self.text_edit = text_edit_widget
        self.breakpoints = set()
        self.setFixedWidth(16) # Gutter width

        # Connect signals
        self.text_edit.document().blockCountChanged.connect(self.update)
        # QPlainTextEdit.updateRequest is a signal that can be used.
        self.text_edit.updateRequest.connect(self._on_editor_update_request)
        # Also update when the editor's vertical scrollbar value changes, as this affects visible area
        self.text_edit.verticalScrollBar().valueChanged.connect(self.update)


    def _on_editor_update_request(self, rect, dy):
        # This slot is connected to QPlainTextEdit's updateRequest.
        # rect is the area to update in viewport coordinates.
        # dy is the amount of vertical shift.
        # We need to update the gutter if there's a vertical scroll or if the relevant part of the gutter needs repainting.
        if dy != 0:
            # If scrolled, the entire visible part of the gutter might need repaint.
            self.update()
        else:
            # If no scroll, update only the corresponding part of the gutter.
            # For simplicity, update the whole gutter. A more optimized version would translate 'rect'.
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#E0E0E0")) # Gutter background

        block = self.text_edit.firstVisibleBlock()

        while block.isValid():
            block_bounding_rect = self.text_edit.blockBoundingGeometry(block)
            # Translate block's top y to viewport coordinates relative to the text_edit widget
            block_top_y_in_editor_viewport = block_bounding_rect.translated(0, -self.text_edit.verticalScrollBar().value()).top()

            # If block is below the event rect's bottom (which is in gutter's coordinates), no need to paint further.
            # Assuming gutter and editor viewport y-coordinates are aligned.
            if block_top_y_in_editor_viewport > event.rect().bottom():
                break

            # Only draw if the block is actually visible within the current paint event's rectangle for the gutter
            if block_top_y_in_editor_viewport + block_bounding_rect.height() >= event.rect().top():
                line_num = block.blockNumber() + 1
                if line_num in self.breakpoints:
                    block_height = block_bounding_rect.height()
                    circle_radius = 4
                    circle_center_x = self.width() // 2
                    # Calculate circle_center_y relative to the gutter's coordinate system (same as editor's viewport y)
                    circle_center_y = block_top_y_in_editor_viewport + block_height // 2

                    painter.setBrush(Qt.red)
                    painter.setPen(Qt.NoPen) # No border for the circle
                    painter.drawEllipse(QPoint(circle_center_x, int(circle_center_y)), circle_radius, circle_radius)

            block = block.next()
            if not block.isValid():
                break

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            click_y_in_gutter_viewport = event.position().y()

            # Map this y-coordinate to a block number in the text_edit
            # cursorForPosition expects coordinates relative to the text_edit's viewport
            target_pos_in_editor_viewport = QPoint(5, int(click_y_in_gutter_viewport))
            cursor = self.text_edit.cursorForPosition(target_pos_in_editor_viewport)

            line_number = cursor.blockNumber() + 1
            self.breakpoint_toggled.emit(line_number)

    def update_breakpoints_display(self, new_breakpoints_set):
        self.breakpoints = new_breakpoints_set
        self.update()


class _InternalCodeEditor(QPlainTextEdit): # Renamed and inherits QPlainTextEdit
    cursor_position_changed_signal = Signal(int, int) # Line, Column
    language_changed_signal = Signal(str)
    control_reclaim_requested = Signal() # New signal for host to reclaim control

    def __init__(self, parent=None): # Parent will be the CodeEditor QWidget
        super().__init__(parent)
        self.setTabStopDistance(4 * self.fontMetrics().averageCharWidth())
        self.file_path = None # file_path attribute resides here
        self.current_language = "Plain Text"

        self.theme_config = self._load_theme_config()
        self._apply_editor_theme()

        self.highlighter = PythonHighlighter(self.document(), self.theme_config)
        self.thread_pool = QThreadPool.globalInstance()
        self.setup_linter()
        self.setup_completer()

        self.PAIRS = {
            '(': ')', '[': ']', '{': '}',
            '"': '"', "'": "'", '<': '>'
        }
        self.CLOSING_CHARS = set(self.PAIRS.values())

        # textChanged signal will be connected by the outer CodeEditor
        self.cursorPositionChanged.connect(self._emit_cursor_position)
        self._is_programmatic_change = False

    # All original CodeEditor methods that were QPlainTextEdit specific are moved here
    def _load_theme_config(self):
        print("LOG: CodeEditor._load_theme_config - Entry")
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'theme.json')
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            sys.stderr.write(f"Theme config file not found at {config_path}. Using default theme.\n")
            return {}
        except json.JSONDecodeError:
            sys.stderr.write(f"Error decoding theme config from {config_path}. Using default theme.\n")
            return {}
        except Exception as e:
            sys.stderr.write(f"An unexpected error occurred loading theme config from {config_path}: {e}\n")
            return {}
        finally:
            print("LOG: CodeEditor._load_theme_config - Exit")

    def _apply_editor_theme(self):
        print("LOG: CodeEditor._apply_editor_theme - Entry")
        editor_theme = self.theme_config.get("editor", {})
        bg_color = editor_theme.get("background", "#282c34")
        fg_color = editor_theme.get("foreground", "#abb2bf")
        selection_bg = editor_theme.get("selection_background", "#3e4451")
        line_num_fg = editor_theme.get("line_number_foreground", "#5c6370")

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {bg_color};
                color: {fg_color};
                selection-background-color: {selection_bg};
            }}
            QPlainTextEdit QAbstractScrollArea::corner {{
                background-color: {bg_color};
            }}
        """)
        print("LOG: CodeEditor._apply_editor_theme - Exit")

    def _update_language_and_highlighting(self):
        print("LOG: CodeEditor._update_language_and_highlighting - Entry")
        if self._is_programmatic_change:
            print("LOG: CodeEditor._update_language_and_highlighting - Programmatic change, skipping.")
            return

        old_language = self.current_language
        
        if self.file_path:
            self._is_programmatic_change = True # Set flag before programmatic change
            self.highlighter.set_lexer_for_filename(self.file_path, self.toPlainText())
            self._is_programmatic_change = False # Reset flag after programmatic change
            if self.highlighter.lexer:
                self.current_language = self.highlighter.lexer.name
            else:
                self.current_language = "Plain Text"
        else:
            self._is_programmatic_change = True # Set flag before programmatic change
            self.highlighter.lexer = None
            self.current_language = "Plain Text"
            self.highlighter.rehighlight()
            self._is_programmatic_change = False # Reset flag after programmatic change

        if self.current_language != old_language:
            self.language_changed_signal.emit(self.current_language)
        
        self.linter_timer.start()
        print("LOG: CodeEditor._update_language_and_highlighting - Exit")

    def set_file_path_and_update_language(self, file_path):
        """
        Sets the file path for the editor and triggers language detection and highlighting.
        This method should be called when a new file is opened or saved.
        """
        self.file_path = file_path
        self._update_language_and_highlighting()

    def _emit_cursor_position(self):
        print("LOG: CodeEditor._emit_cursor_position - Entry")
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber() + 1
        self.cursor_position_changed_signal.emit(line, column)
        print("LOG: CodeEditor._emit_cursor_position - Exit")

    def setup_completer(self):
        print("LOG: CodeEditor.setup_completer - Entry")
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setModel(QStringListModel())
        self.completer.activated.connect(self.insert_completion)

        self.cursorPositionChanged.connect(self.show_completion_if_dot)
        print("LOG: CodeEditor.setup_completer - Exit")

    def show_completion_if_dot(self):
        print("LOG: CodeEditor.show_completion_if_dot - Entry")
        cursor = self.textCursor()
        text_before_cursor = self.toPlainText()[:cursor.position()]
        if text_before_cursor and text_before_cursor[-1] == '.':
            self.request_completions()
        elif self.completer.popup().isVisible():
            self.completer.popup().hide()
        print("LOG: CodeEditor.show_completion_if_dot - Exit")

    def request_completions(self):
        print("LOG: CodeEditor.request_completions - Entry")
        text = self.toPlainText()
        line = self.textCursor().blockNumber() + 1
        column = self.textCursor().columnNumber()
        file_path = self.file_path if self.file_path else "untitled.py"

        worker = JediCompletionWorker(text, line, column, file_path)
        worker.signals.result.connect(self._handle_completions_result)
        worker.signals.error.connect(lambda msg: sys.stderr.write(f"Jedi error: {msg}\n"))
        self.thread_pool.start(worker)
        print("LOG: CodeEditor.request_completions - Exit")

    @Slot(list)
    def _handle_completions_result(self, words):
        print("LOG: CodeEditor._handle_completions_result - Entry")
        self.completer.model().setStringList(words)

        if words:
            cursor_rect = self.cursorRect(self.textCursor())
            self.completer.popup().setGeometry(
                self.mapToGlobal(cursor_rect.bottomLeft()).x(),
                self.mapToGlobal(cursor_rect.bottomLeft()).y(),
                self.completer.popup().sizeHint().width(),
                self.completer.popup().sizeHint().height()
            )
            self.completer.complete()
        else:
            self.completer.popup().hide()
        print("LOG: CodeEditor._handle_completions_result - Exit")

    def insert_completion(self, completion):
        print("LOG: CodeEditor.insert_completion - Entry")
        if self.completer.widget() is not self:
            print("LOG: CodeEditor.insert_completion - Completer widget mismatch, returning.")
            return

        tc = self.textCursor()
        extra = len(self.completer.completionPrefix())
        
        self._is_programmatic_change = True # Set flag before programmatic change
        tc.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, extra)
        tc.insertText(completion)
        self.setTextCursor(tc)
        self._is_programmatic_change = False # Reset flag after programmatic change
        print("LOG: CodeEditor.insert_completion - Exit")

    def setup_linter(self):
        print("LOG: CodeEditor.setup_linter - Entry")
        self.linter_timer = QTimer(self)
        self.linter_timer.setInterval(700)
        self.linter_timer.setSingleShot(True)
        self.linter_timer.timeout.connect(self.lint_code)
        print("LOG: CodeEditor.setup_linter - Exit")

    def lint_code(self):
        print("LOG: CodeEditor.lint_code - Entry")
        code = self.toPlainText()
        file_path = self.file_path if self.file_path else "untitled.py"
        worker = PyflakesLinterWorker(code)
        worker.signals.result.connect(self.apply_linting_highlights)
        worker.signals.error.connect(lambda msg: sys.stderr.write(f"Pyflakes error: {msg}\n"))
        self.thread_pool.start(worker)
        print("LOG: CodeEditor.lint_code - Exit")

    def apply_linting_highlights(self, errors):
        print("LOG: CodeEditor.apply_linting_highlights - Entry")
        self._is_programmatic_change = True # Set flag before programmatic change
        extra_selections = []
        error_format = QTextCharFormat()
        error_format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        error_format.setUnderlineColor(QColor("red"))

        for line_num, col_num, message in errors:
            block = self.document().findBlockByNumber(line_num - 1)
            if block.isValid():
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.StartOfBlock)
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

                selection = QTextEdit.ExtraSelection()
                selection.format = error_format
                selection.cursor = cursor
                extra_selections.append(selection)

        self.setExtraSelections(extra_selections)
        self._is_programmatic_change = False # Reset flag after programmatic change
        print("LOG: CodeEditor.apply_linting_highlights - Exit")

    def keyPressEvent(self, event: QKeyEvent):
        print(f"LOG: CodeEditor.keyPressEvent - Key: {event.key()}, Text: '{event.text()}' - Entry")
        
        # Host-side logic to reclaim control
        if self.isReadOnly(): # The host is currently a viewer
            # This means the host is trying to type while a client has control.
            # Instead of typing, emit the signal to reclaim control.
            self.control_reclaim_requested.emit()
            event.accept() # Consume the event so no character is typed yet.
            return
        
        cursor = self.textCursor()
        key = event.key()
        text = event.text()
        
        # Get character to the right of the cursor
        char_after_cursor = ''
        if cursor.position() < len(self.toPlainText()):
            char_after_cursor = self.toPlainText()[cursor.position()]

        # Get character to the left of the cursor
        char_before_cursor = ''
        if cursor.position() > 0:
            char_before_cursor = self.toPlainText()[cursor.position() - 1]

        # 1. Handle Tab for indentation
        if key == Qt.Key.Key_Tab:
            self._is_programmatic_change = True
            if cursor.hasSelection():
                # Indent selected lines
                start_block = cursor.blockNumber()
                end_block = self.document().findBlock(cursor.anchor()).blockNumber()
                if start_block > end_block:
                    start_block, end_block = end_block, start_block
                
                cursor.beginEditBlock()
                block = self.document().findBlockByNumber(start_block)
                while block.isValid() and block.blockNumber() <= end_block:
                    cursor_for_block = QTextCursor(block)
                    cursor_for_block.movePosition(QTextCursor.StartOfBlock)
                    cursor_for_block.insertText("    ") # 4 spaces for tab
                    block = block.next()
                cursor.endEditBlock()
            else:
                # Insert 4 spaces at cursor position
                cursor.insertText("    ")
            self._is_programmatic_change = False
            event.accept() # Consume the event
            print("LOG: CodeEditor.keyPressEvent - Tab handled, Exit")
            return

        # 2. Handle "Smart Over-Typing" for Closing Brackets
        if text in self.CLOSING_CHARS and not cursor.hasSelection():
            if char_after_cursor == text:
                self._is_programmatic_change = True
                cursor.movePosition(QTextCursor.NextCharacter)
                self.setTextCursor(cursor)
                self._is_programmatic_change = False
                event.accept() # Consume the event
                print("LOG: CodeEditor.keyPressEvent - Over-typing handled, Exit")
                return

        # 3. Handle Context-Aware Insertion for Opening Brackets (Auto-pairing)
        if text in self.PAIRS:
            if cursor.hasSelection():
                # Wrap selection
                selected_text = cursor.selectedText()
                self._is_programmatic_change = True
                cursor.insertText(text + selected_text + self.PAIRS[text])
                cursor.setPosition(cursor.position() - len(selected_text) - 1) # Move cursor back inside
                self.setTextCursor(cursor)
                self._is_programmatic_change = False
                event.accept() # Consume the event
                print("LOG: CodeEditor.keyPressEvent - Auto-pair wrap handled, Exit")
                return
            else:
                # Context-aware insertion
                should_auto_pair = False
                if not char_after_cursor or char_after_cursor.isspace() or char_after_cursor in self.CLOSING_CHARS:
                    should_auto_pair = True
                
                # Special case for quotes: don't auto-pair if char before is same quote
                if text in ['"', "'"] and char_before_cursor == text:
                    should_auto_pair = False

                if should_auto_pair:
                    self._is_programmatic_change = True
                    cursor.insertText(text + self.PAIRS[text])
                    cursor.movePosition(QTextCursor.PreviousCharacter) # Move cursor back inside
                    self.setTextCursor(cursor)
                    self._is_programmatic_change = False
                    event.accept() # Consume the event
                    print("LOG: CodeEditor.keyPressEvent - Context-aware auto-pair insert handled, Exit")
                    return
        
        # 4. Smart Backspace
        if key == Qt.Key.Key_Backspace and not cursor.hasSelection():
            if char_before_cursor in self.PAIRS and char_after_cursor == self.PAIRS[char_before_cursor]:
                self._is_programmatic_change = True
                cursor.beginEditBlock()
                cursor.deletePreviousChar() # Delete opening char
                cursor.deleteChar()         # Delete closing char
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                self._is_programmatic_change = False
                event.accept() # Consume the event
                print("LOG: CodeEditor.keyPressEvent - Smart Backspace handled, Exit")
                return

        # If none of the special cases are handled, call the default handler
        super().keyPressEvent(event)
        print("LOG: _InternalCodeEditor.keyPressEvent - Default handler, Exit")


class CodeEditor(QWidget): # Now inherits QWidget
    # Define signals that will be proxied from _InternalCodeEditor
    textChanged = Signal()
    cursor_position_changed_signal = Signal(int, int) # This is the custom one with line/col numbers
    language_changed_signal = Signal(str)
    control_reclaim_requested = Signal()
    breakpoint_toggled = Signal(int) # Signal for breakpoint toggles from the gutter
    cursorPositionChanged = Signal() # Standard Qt signal, proxied

    def __init__(self, parent=None):
        super().__init__(parent)

        self.text_edit = _InternalCodeEditor(self) # Create the internal editor
        self.gutter = BreakpointGutter(self.text_edit) # Pass the internal editor to the gutter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.gutter)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

        # Proxy signals from internal editor to CodeEditor's signals
        self.text_edit.textChanged.connect(self.textChanged)
        self.text_edit.cursor_position_changed_signal.connect(self.cursor_position_changed_signal)
        self.text_edit.language_changed_signal.connect(self.language_changed_signal)
        self.text_edit.control_reclaim_requested.connect(self.control_reclaim_requested)

        # Connect gutter's breakpoint_toggled signal to CodeEditor's breakpoint_toggled signal
        self.gutter.breakpoint_toggled.connect(self.breakpoint_toggled)

        # Connect the standard cursorPositionChanged signal
        self.text_edit.cursorPositionChanged.connect(self.cursorPositionChanged)

    # --- Proxy Methods to _InternalCodeEditor ---
    def toPlainText(self):
        return self.text_edit.toPlainText()

    def setPlainText(self, text):
        self.text_edit.setPlainText(text)

    def document(self): # MainWindow uses this for undo/redo
        return self.text_edit.document()

    def textCursor(self): # Might be needed if MainWindow interacts with cursor directly
        return self.text_edit.textCursor()

    def setTextCursor(self, cursor): # Might be needed
        self.text_edit.setTextCursor(cursor)

    def setReadOnly(self, readOnly):
        self.text_edit.setReadOnly(readOnly)

    def isReadOnly(self):
        return self.text_edit.isReadOnly()

    def set_file_path_and_update_language(self, file_path):
        self.text_edit.set_file_path_and_update_language(file_path)

    @property
    def file_path(self):
        return self.text_edit.file_path

    @file_path.setter
    def file_path(self, value):
        self.text_edit.file_path = value
        # The actual update of language/highlighting is handled within _InternalCodeEditor
        # when set_file_path_and_update_language is called, or by textChanged.
        # If direct setting of file_path should also trigger it, logic would be needed in _InternalCodeEditor's setter or here.

    @property
    def current_language(self):
        return self.text_edit.current_language

    @current_language.setter
    def current_language(self, value):
        self.text_edit.current_language = value
        # Potentially trigger a language_changed_signal if this setter is used externally
        # and needs to notify other components, though typically language changes via _update_language_and_highlighting.

    # Proxy any other methods that MainWindow or other components might call on CodeEditor
    # For example, if MainWindow used editor.clear(), you'd add:
    # def clear(self):
    #     self.text_edit.clear()

    # Ensure keyPressEvent is handled by the focused widget (the internal text_edit)
    # QWidget doesn't have keyPressEvent by default in the same way QPlainTextEdit does.
    # Focus is usually handled automatically. If specific top-level key events for CodeEditor(QWidget)
    # were needed, they'd be implemented here, but typing should go to self.text_edit.

    # Placeholder for breakpoint handling if managed internally by CodeEditor later
    # def handle_breakpoint_toggle(self, line_number):
    #     print(f"Breakpoint toggled in CodeEditor for line: {line_number}")
    #     if line_number in self.gutter.breakpoints:
    #         self.gutter.breakpoints.remove(line_number)
    #     else:
    #         self.gutter.breakpoints.add(line_number)
    #     self.gutter.update() # Or self.gutter.update_breakpoints_display(self.gutter.breakpoints)