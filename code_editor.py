from PySide6.QtWidgets import (QPlainTextEdit, QCompleter, QApplication, QTextEdit,
                               QWidget, QHBoxLayout, QStyle) # Added QStyle for future use potentially
from PySide6.QtGui import (QTextCharFormat, QColor, QTextCursor, QKeyEvent, QFont,
                           QSyntaxHighlighter, QPainter, QPaintEvent, QMouseEvent, # Added QPaintEvent, QMouseEvent
                           QTextBlock, QTextDocument) # Added QTextBlock, QTextDocument
from PySide6.QtCore import (Qt, QTimer, QStringListModel, QRect, QRegularExpression,
                            Signal, Slot, QPoint, QSize, QThreadPool, QRectF) # Added QRectF
import json
import os
# import sys # Not used
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Callable, TYPE_CHECKING, cast # Added TYPE_CHECKING and others

# Import worker threads
from worker_threads import JediCompletionWorker, PyflakesLinterWorker, WorkerSignals

from python_highlighter import PythonHighlighter
from config_manager import ConfigManager
from config import (DEFAULT_EDITOR_FONT_FAMILY, DEFAULT_EDITOR_FONT_SIZE, # Added
                    DEFAULT_LINE_NUMBER_AREA_PADDING,
                    DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING,
                    DEFAULT_BREAKPOINT_GUTTER_WIDTH) # Added for editor layout

if TYPE_CHECKING:
    # Forward reference for _InternalCodeEditor as it's used by LineNumberArea and BreakpointGutter
    # before _InternalCodeEditor class definition.
    class _InternalCodeEditor(QPlainTextEdit): pass

# Fallback editor settings if config.json is missing or corrupted
FALLBACK_EDITOR_SETTINGS = {
    "auto_pairs": {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'", '<': '>'},
    "tab_stop_char_width_multiplier": 4,
    "linter_interval_ms": 700
}

class LineNumberArea(QWidget):
    editor: '_InternalCodeEditor'

    def __init__(self, editor: '_InternalCodeEditor') -> None:
        super().__init__(editor)
        self.editor = editor

        config_mgr = ConfigManager() # Added
        self.padding = config_mgr.load_setting('editor_line_number_area_padding', DEFAULT_LINE_NUMBER_AREA_PADDING) # Added
        self.text_right_padding = config_mgr.load_setting('editor_line_number_area_text_right_padding', DEFAULT_LINE_NUMBER_AREA_TEXT_RIGHT_PADDING) # Added

    def sizeHint(self) -> QSize:
        block_count: int = self.editor.blockCount()
        num_digits: int = len(str(max(1, block_count)))
        padding: int = self.padding # Modified
        # Ensure self.fontMetrics() is valid, might need to take font from editor if not set on self
        font_metrics = self.fontMetrics() if self.font().family() else self.editor.fontMetrics()
        width: int = font_metrics.horizontalAdvance('9') * num_digits + padding
        return QSize(width, 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter: QPainter = QPainter(self)
        editor: '_InternalCodeEditor' = self.editor

        bg_color_str: str = editor.theme_config.get("editor", {}).get("gutter_background", "#2c313a")
        painter.fillRect(event.rect(), QColor(bg_color_str))

        painter.setFont(editor.font())
        line_num_fg_str: str = editor.theme_config.get("editor", {}).get("line_number_foreground", "#606366")
        painter.setPen(QColor(line_num_fg_str))

        first_block: QTextBlock = editor.firstVisibleBlock()
        current_block_number: int = editor.textCursor().blockNumber()
        padding_right: int = self.text_right_padding # Modified
        block: QTextBlock = first_block
        block_top_y_in_editor_viewport_prev: float = -1.0

        while block.isValid() and editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top() <= event.rect().bottom() + editor.verticalScrollBar().value():
            block_bounding_rect: QRectF = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
            block_top_y_in_editor_viewport: float = block_bounding_rect.top() - editor.verticalScrollBar().value()

            if block_top_y_in_editor_viewport + block_bounding_rect.height() < event.rect().top():
                block = block.next()
                continue
            if int(block_top_y_in_editor_viewport) == int(block_top_y_in_editor_viewport_prev):
                block = block.next()
                continue

            line_num: int = block.blockNumber() + 1
            if block.blockNumber() == current_block_number:
                highlight_color_str: str = editor.theme_config.get("editor", {}).get("current_line_gutter_background", "#3a3f4b")
                highlight_rect = QRect(0, int(block_top_y_in_editor_viewport), self.width(), editor.fontMetrics().height())
                painter.fillRect(highlight_rect, QColor(highlight_color_str))

            painter.drawText(
                0, int(block_top_y_in_editor_viewport),
                self.width() - padding_right, editor.fontMetrics().height(),
                Qt.AlignmentFlag.AlignRight, str(line_num)
            )
            block_top_y_in_editor_viewport_prev = block_top_y_in_editor_viewport
            block = block.next()


class BreakpointGutter(QWidget):
    breakpoint_toggled: Signal = Signal(int)
    text_edit: '_InternalCodeEditor'
    breakpoints: Set[int]

    def __init__(self, text_edit_widget: '_InternalCodeEditor') -> None:
        super().__init__(text_edit_widget)
        self.text_edit = text_edit_widget
        self.breakpoints = set()

        config_mgr = ConfigManager() # Added
        gutter_width = config_mgr.load_setting('editor_breakpoint_gutter_width', DEFAULT_BREAKPOINT_GUTTER_WIDTH) # Added
        self.setFixedWidth(gutter_width) # Modified

        self.text_edit.document().blockCountChanged.connect(self.update)
        self.text_edit.updateRequest.connect(self._on_editor_update_request)
        self.text_edit.verticalScrollBar().valueChanged.connect(self.update)

    @Slot(QRect, int)
    def _on_editor_update_request(self, rect: QRect, dy: int) -> None:
        if dy != 0:
            self.update()
        else:
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter: QPainter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#E0E0E0"))
        block: QTextBlock = self.text_edit.firstVisibleBlock()

        while block.isValid():
            block_bounding_rect: QRectF = self.text_edit.blockBoundingGeometry(block)
            block_top_y_in_editor_viewport: float = block_bounding_rect.translated(0, -self.text_edit.verticalScrollBar().value()).top()
            if block_top_y_in_editor_viewport > event.rect().bottom():
                break
            if block_top_y_in_editor_viewport + block_bounding_rect.height() >= event.rect().top():
                line_num: int = block.blockNumber() + 1
                if line_num in self.breakpoints:
                    block_height: float = block_bounding_rect.height()
                    circle_radius: int = 4
                    circle_center_x: int = self.width() // 2
                    circle_center_y: float = block_top_y_in_editor_viewport + block_height / 2
                    painter.setBrush(Qt.GlobalColor.red)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QPoint(circle_center_x, int(circle_center_y)), circle_radius, circle_radius)
            block = block.next()
            if not block.isValid():
                break

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            click_y_in_gutter_viewport: float = event.position().y()
            target_pos_in_editor_viewport = QPoint(5, int(click_y_in_gutter_viewport))
            cursor: QTextCursor = self.text_edit.cursorForPosition(target_pos_in_editor_viewport)
            line_number: int = cursor.blockNumber() + 1
            self.breakpoint_toggled.emit(line_number)

    def update_breakpoints_display(self, new_breakpoints_set: Set[int]) -> None:
        self.breakpoints = new_breakpoints_set
        self.update()


class _InternalCodeEditor(QPlainTextEdit):
    cursor_position_changed_signal: Signal = Signal(int, int)
    language_changed_signal: Signal = Signal(str)
    control_reclaim_requested: Signal = Signal()

    file_path: Optional[str]
    current_language: str
    theme_config: Dict[str, Any]
    highlighter: PythonHighlighter # Assuming QSyntaxHighlighter or derived
    thread_pool: QThreadPool
    completer: QCompleter
    linter_timer: QTimer
    PAIRS: Dict[str, str]
    CLOSING_CHARS: Set[str]
    _is_programmatic_change: bool
    logger: logging.Logger
    linter_interval_ms: int


    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.file_path = None
        self.current_language = "Plain Text"
        self.logger = logging.getLogger(__name__ + "._InternalCodeEditor")

        config_mgr: ConfigManager = ConfigManager()

        # Load and set editor font
        editor_font_family = config_mgr.load_setting('editor_font_family', DEFAULT_EDITOR_FONT_FAMILY)
        editor_font_size = config_mgr.load_setting('editor_font_size', DEFAULT_EDITOR_FONT_SIZE)
        current_font = self.font()
        current_font.setFamily(editor_font_family)
        current_font.setPointSize(editor_font_size)
        self.setFont(current_font)

        loaded_settings: Dict[str, Any] = config_mgr.load_setting('editor_settings', FALLBACK_EDITOR_SETTINGS)

        self.PAIRS = loaded_settings.get("auto_pairs", FALLBACK_EDITOR_SETTINGS["auto_pairs"])
        self.CLOSING_CHARS = set(self.PAIRS.values())

        tab_multiplier: int = loaded_settings.get("tab_stop_char_width_multiplier", FALLBACK_EDITOR_SETTINGS["tab_stop_char_width_multiplier"])
        # Ensure fontMetrics().averageCharWidth() returns a valid value
        avg_char_width: float = self.fontMetrics().averageCharWidth()
        if avg_char_width <= 0: avg_char_width = self.fontMetrics().maxWidth() # Fallback if avg is 0
        self.setTabStopDistance(tab_multiplier * avg_char_width)


        self.linter_interval_ms = loaded_settings.get("linter_interval_ms", FALLBACK_EDITOR_SETTINGS["linter_interval_ms"])

        # Load theme file path from config
        FALLBACK_THEME_PATH_STR = "config/theme.json" # Relative to code_editor.py
        self.theme_config_file_path_str: str = config_mgr.load_setting(
            'theme_file_path',
            FALLBACK_THEME_PATH_STR
        )

        self.theme_config = self._load_theme_config()
        self._apply_editor_theme()

        self.highlighter = PythonHighlighter(self.document(), self.theme_config)
        self.thread_pool = QThreadPool.globalInstance()
        self.setup_linter()
        self.setup_completer()

        self.cursorPositionChanged.connect(self._emit_cursor_position)
        self._is_programmatic_change = False

    def _load_theme_config(self) -> Dict[str, Any]:
        self.logger.debug("Loading theme config.")

        path_from_config: str = self.theme_config_file_path_str

        if os.path.isabs(path_from_config):
            config_path = path_from_config
        else:
            # Assume relative to the directory of the current file (code_editor.py)
            config_path = os.path.join(os.path.dirname(__file__), path_from_config)

        self.logger.info(f"Attempting to load theme from resolved path: {config_path}")

        try:
            with open(config_path, 'r') as f:
                # Ensure json.load returns a dict or handle other cases
                loaded_data = json.load(f)
                if not isinstance(loaded_data, dict):
                    self.logger.error(f"Theme config at {config_path} is not a dictionary. Using default theme.")
                    return {}
                return loaded_data
        except FileNotFoundError:
            self.logger.warning(f"Theme config file not found at {config_path}. Using default theme.")
            return {}
        except json.JSONDecodeError:
            self.logger.error(f"Error decoding theme config from {config_path}. Using default theme.", exc_info=True)
            return {}
        except Exception as e:
            self.logger.error(f"An unexpected error occurred loading theme config from {config_path}: {e}", exc_info=True)
            return {}

    def _apply_editor_theme(self) -> None:
        self.logger.debug("Applying editor theme.")
        editor_theme: Dict[str, Any] = self.theme_config.get("editor", {})
        bg_color: str = editor_theme.get("background", "#282c34")
        fg_color: str = editor_theme.get("foreground", "#abb2bf")
        selection_bg: str = editor_theme.get("selection_background", "#3e4451")

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

    def _update_language_and_highlighting(self) -> None:
        self.logger.debug(f"Updating language and highlighting for file: {self.file_path}")
        if self._is_programmatic_change:
            self.logger.debug("Programmatic change detected, skipping update_language_and_highlighting.")
            return

        old_language: str = self.current_language
        
        if self.file_path:
            self._is_programmatic_change = True
            self.highlighter.set_lexer_for_filename(self.file_path, self.toPlainText())
            self._is_programmatic_change = False
            if self.highlighter.lexer:
                self.current_language = self.highlighter.lexer.name
            else:
                self.current_language = "Plain Text"
        else:
            self._is_programmatic_change = True
            self.highlighter.lexer = None
            self.current_language = "Plain Text"
            self.highlighter.rehighlight()
            self._is_programmatic_change = False

        if self.current_language != old_language:
            self.logger.info(f"Language changed from '{old_language}' to '{self.current_language}'.")
            self.language_changed_signal.emit(self.current_language)
        
        self.linter_timer.start()

    def set_file_path_and_update_language(self, file_path: Optional[str]) -> None:
        """
        Sets the file path for the editor and triggers language detection and highlighting.
        This method should be called when a new file is opened or saved.
        """
        self.logger.info(f"Setting file path to: {file_path} and updating language.")
        self.file_path = file_path
        self._update_language_and_highlighting()

    def _emit_cursor_position(self) -> None:
        cursor: QTextCursor = self.textCursor()
        line: int = cursor.blockNumber() + 1
        column: int = cursor.columnNumber() + 1
        self.cursor_position_changed_signal.emit(line, column)

    def setup_completer(self) -> None:
        self.logger.debug("Setting up completer.")
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setModel(QStringListModel())
        self.completer.activated.connect(self.insert_completion) # type: ignore[attr-defined]

        self.cursorPositionChanged.connect(self.show_completion_if_dot)

    def show_completion_if_dot(self) -> None:
        cursor: QTextCursor = self.textCursor()
        text_before_cursor: str = self.toPlainText()[:cursor.position()]
        if text_before_cursor and text_before_cursor[-1] == '.':
            self.logger.debug("Dot detected, requesting completions.")
            self.request_completions()
        elif self.completer.popup().isVisible():
            self.completer.popup().hide()

    def request_completions(self) -> None:
        self.logger.debug("Requesting completions.")
        text: str = self.toPlainText()
        line: int = self.textCursor().blockNumber() + 1
        column: int = self.textCursor().columnNumber()
        file_path_for_jedi: str = self.file_path if self.file_path else "untitled.py"

        worker = JediCompletionWorker(text, line, column, file_path_for_jedi)
        worker.signals.result.connect(self._handle_completions_result)
        worker.signals.error.connect(lambda msg: self.logger.error(f"Jedi completion error: {msg}"))
        self.thread_pool.start(worker)

    @Slot(list) # Expected to be List[str]
    def _handle_completions_result(self, words: List[str]) -> None:
        self.logger.debug(f"Handling completions result: {words[:5]}...")
        current_model = self.completer.model()
        if not isinstance(current_model, QStringListModel):
            new_model = QStringListModel()
            self.completer.setModel(new_model)
            current_model = new_model

        model: QStringListModel = cast(QStringListModel, current_model)
        model.setStringList(words)

        if words:
            self.logger.debug("Completions found, showing popup.")
            cursor_rect: QRect = self.cursorRect(self.textCursor())
            self.completer.popup().setGeometry(
                self.mapToGlobal(cursor_rect.bottomLeft()).x(),
                self.mapToGlobal(cursor_rect.bottomLeft()).y(),
                self.completer.popup().sizeHint().width(),
                self.completer.popup().sizeHint().height()
            )
            self.completer.complete()
        else:
            self.logger.debug("No completions found, hiding popup.")
            self.completer.popup().hide()

    def insert_completion(self, completion: str) -> None:
        self.logger.debug(f"Inserting completion: {completion}")
        if self.completer.widget() is not self:
            self.logger.warning("Completer widget mismatch, not inserting completion.")
            return

        tc = self.textCursor()
        extra = len(self.completer.completionPrefix())
        
        self._is_programmatic_change = True # Set flag before programmatic change
        tc.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, extra)
        tc.insertText(completion)
        self.setTextCursor(tc)
        self._is_programmatic_change = False # Reset flag after programmatic change
        self.logger.debug("Completion inserted.")

    def setup_linter(self) -> None:
        self.logger.debug("Setting up linter timer.")
        self.linter_timer = QTimer(self)
        self.linter_timer.setInterval(self.linter_interval_ms)
        self.linter_timer.setSingleShot(True)
        self.linter_timer.timeout.connect(self.lint_code)

    def lint_code(self) -> None:
        self.logger.debug(f"Requesting linting for: {self.file_path if self.file_path else 'untitled'}")
        code: str = self.toPlainText()
        worker = PyflakesLinterWorker(code)
        worker.signals.result.connect(self.apply_linting_highlights)
        worker.signals.error.connect(lambda msg: self.logger.error(f"Pyflakes linter error: {msg}"))
        self.thread_pool.start(worker)

    def apply_linting_highlights(self, errors: List[Tuple[int, int, str]]) -> None:
        self.logger.debug(f"Applying {len(errors)} linting highlights.")
        self._is_programmatic_change = True
        extra_selections: List[QTextEdit.ExtraSelection] = []
        error_format = QTextCharFormat()
        error_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        error_format.setUnderlineColor(QColor("red"))

        for line_num, col_num, message in errors:
            block: QTextBlock = self.document().findBlockByNumber(line_num - 1)
            if block.isValid():
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)

                selection = QTextEdit.ExtraSelection()
                selection.format = error_format
                selection.cursor = cursor
                extra_selections.append(selection)

        self.setExtraSelections(extra_selections)
        self._is_programmatic_change = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.isReadOnly():
            self.control_reclaim_requested.emit()
            event.accept()
            return
        
        cursor: QTextCursor = self.textCursor()
        key: int = event.key()
        text: str = event.text()

        char_after_cursor: str = ''
        doc: QTextDocument = self.document()
        doc_len: int = doc.characterCount() -1
        current_pos: int = cursor.position()
        
        if current_pos < doc_len :
             temp_cursor = QTextCursor(cursor)
             temp_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor, 1)
             if temp_cursor.selectedText():
                 char_after_cursor = temp_cursor.selectedText()[0]


        char_before_cursor: str = ''
        if current_pos > 0:
            temp_cursor = QTextCursor(cursor)
            temp_cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.KeepAnchor, 1)
            if temp_cursor.selectedText():
                char_before_cursor = temp_cursor.selectedText()[0]


        if key == Qt.Key.Key_Tab:
            self._is_programmatic_change = True
            if cursor.hasSelection():
                start_pos: int = cursor.selectionStart()
                end_pos: int = cursor.selectionEnd()
                start_block: int = doc.findBlock(start_pos).blockNumber()
                end_block: int = doc.findBlock(end_pos -1).blockNumber()
                
                cursor.beginEditBlock()
                for block_num in range(start_block, end_block + 1):
                    block_cursor = QTextCursor(doc.findBlockByNumber(block_num))
                    block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    block_cursor.insertText("    ")
                cursor.endEditBlock()
            else:
                cursor.insertText("    ")
            self._is_programmatic_change = False
            event.accept()
            return

        if text in self.CLOSING_CHARS and not cursor.hasSelection():
            if char_after_cursor == text:
                self._is_programmatic_change = True
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                self.setTextCursor(cursor)
                self._is_programmatic_change = False
                event.accept()
                return

        if text in self.PAIRS:
            if cursor.hasSelection():
                selected_text: str = cursor.selectedText()
                self._is_programmatic_change = True
                cursor.insertText(text + selected_text + self.PAIRS[text])
                new_cursor_pos = cursor.selectionStart() + len(text) + len(selected_text)
                cursor.setPosition(new_cursor_pos)
                self.setTextCursor(cursor)
                self._is_programmatic_change = False
                event.accept()
                return
            else:
                should_auto_pair: bool = False
                if not char_after_cursor or char_after_cursor.isspace() or char_after_cursor in self.CLOSING_CHARS or char_after_cursor in self.PAIRS.values() :
                    should_auto_pair = True
                
                if text in ['"', "'"] and char_before_cursor == text:
                    if current_pos > 1 and self.toPlainText()[current_pos - 2] != '\\':
                         should_auto_pair = False

                if should_auto_pair:
                    self._is_programmatic_change = True
                    cursor.insertText(text + self.PAIRS[text])
                    cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
                    self.setTextCursor(cursor)
                    self._is_programmatic_change = False
                    event.accept()
                    return
        
        if key == Qt.Key.Key_Backspace and not cursor.hasSelection():
            if char_before_cursor in self.PAIRS and char_after_cursor == self.PAIRS[char_before_cursor]:
                self._is_programmatic_change = True
                cursor.beginEditBlock()
                cursor.deletePreviousChar()
                cursor.deleteChar()
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                self._is_programmatic_change = False
                event.accept()
                return

        super().keyPressEvent(event)


class CodeEditor(QWidget):
    textChanged: Signal = Signal()
    cursor_position_changed_signal: Signal = Signal(int, int)
    language_changed_signal: Signal = Signal(str)
    control_reclaim_requested: Signal = Signal()
    breakpoint_toggled: Signal = Signal(int)
    cursorPositionChanged: Signal = Signal()

    text_edit: _InternalCodeEditor
    line_number_area: LineNumberArea
    gutter: BreakpointGutter

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.text_edit = _InternalCodeEditor(self)
        self.line_number_area = LineNumberArea(self.text_edit)
        self.gutter = BreakpointGutter(self.text_edit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.line_number_area)
        layout.addWidget(self.gutter)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

        self.text_edit.blockCountChanged.connect(self._update_line_number_area_width_and_repaint)
        self.text_edit.updateRequest.connect(self._on_editor_update_request_for_line_numbers)
        self.text_edit.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.text_edit.cursorPositionChanged.connect(self.line_number_area.update)

        self.text_edit.textChanged.connect(self.textChanged)
        self.text_edit.cursor_position_changed_signal.connect(self.cursor_position_changed_signal)
        self.text_edit.language_changed_signal.connect(self.language_changed_signal)
        self.text_edit.control_reclaim_requested.connect(self.control_reclaim_requested)
        self.gutter.breakpoint_toggled.connect(self.breakpoint_toggled)
        self.text_edit.cursorPositionChanged.connect(self.cursorPositionChanged)

    def _update_line_number_area_width_and_repaint(self) -> None:
        if self.line_number_area:
            self.line_number_area.updateGeometry()
            self.line_number_area.update()

    @Slot(QRect, int)
    def _on_editor_update_request_for_line_numbers(self, rect: QRect, dy: int) -> None:
        if dy != 0:
            self.line_number_area.scroll(0, dy)
        else:
             self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

    def set_exec_highlight(self, line_number: Optional[int]) -> None:
        if not hasattr(self, 'text_edit'):
            return

        if line_number is None:
            self.text_edit.setExtraSelections([])
            return

        target_block_number: int = line_number - 1
        if target_block_number < 0:
            self.text_edit.setExtraSelections([])
            return

        selection = QTextEdit.ExtraSelection()
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor("#3a3d41"))
        highlight_format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selection.format = highlight_format

        block: QTextBlock = self.text_edit.document().findBlockByNumber(target_block_number)
        if block.isValid():
            cursor = QTextCursor(block)
            selection.cursor = cursor
            self.text_edit.setExtraSelections([selection])
        else:
            self.text_edit.setExtraSelections([])

    def toPlainText(self) -> str:
        return self.text_edit.toPlainText()

    def setPlainText(self, text: str) -> None:
        self.text_edit.setPlainText(text)

    def document(self) -> QTextDocument:
        return self.text_edit.document()

    def textCursor(self) -> QTextCursor:
        return self.text_edit.textCursor()

    def setTextCursor(self, cursor: QTextCursor) -> None:
        self.text_edit.setTextCursor(cursor)

    def setReadOnly(self, readOnly: bool) -> None:
        self.text_edit.setReadOnly(readOnly)

    def isReadOnly(self) -> bool:
        return self.text_edit.isReadOnly()

    def set_file_path_and_update_language(self, file_path: Optional[str]) -> None:
        self.text_edit.set_file_path_and_update_language(file_path)

    @property
    def file_path(self) -> Optional[str]:
        return self.text_edit.file_path

    @file_path.setter
    def file_path(self, value: Optional[str]) -> None:
        self.text_edit.file_path = value

    @property
    def current_language(self) -> str:
        return self.text_edit.current_language

    @current_language.setter
    def current_language(self, value: str) -> None:
        self.text_edit.current_language = value