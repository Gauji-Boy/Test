import pytest
import os
import json
from unittest.mock import MagicMock, patch, PropertyMock, call

from PySide6.QtCore import Qt, QPoint, Signal, QTimer, QStringListModel
from PySide6.QtGui import QTextCursor, QKeyEvent, QFontMetrics, QSyntaxHighlighter, QMouseEvent, QTextDocument # Added QMouseEvent, QTextDocument
from PySide6.QtWidgets import QPlainTextEdit, QApplication, QCompleter, QWidget # Added QWidget

# Adjust import path as necessary
from code_editor import CodeEditor, _InternalCodeEditor, LineNumberArea, BreakpointGutter, FALLBACK_EDITOR_SETTINGS
from python_highlighter import PythonHighlighter # For mocking purposes
from config_manager import ConfigManager # For mocking

# Need to ensure a QApplication instance exists for widgets that require it (e.g., font metrics)
@pytest.fixture(scope="session", autouse=True)
def qt_application():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def mock_config_manager_for_editor():
    cm = MagicMock(spec=ConfigManager)
    # Use a copy of FALLBACK_EDITOR_SETTINGS to avoid modification across tests
    cm.load_setting.return_value = FALLBACK_EDITOR_SETTINGS.copy()
    return cm

@pytest.fixture
def internal_editor(mock_config_manager_for_editor):
    # Patch ConfigManager during _InternalCodeEditor instantiation
    with patch('code_editor.ConfigManager', return_value=mock_config_manager_for_editor):
        # Mock PythonHighlighter to avoid actual lexer loading in unit tests
        with patch('code_editor.PythonHighlighter') as MockHighlighter:
            # Mock QPlainTextEdit's document() method to return a mock QSyntaxHighlighter for the highlighter
            # This is because PythonHighlighter expects a QTextDocument
            mock_document = MagicMock(spec=QTextDocument)

            # Create editor instance, it will try to create a PythonHighlighter
            # The highlighter will be passed its document()
            editor = _InternalCodeEditor(parent=None)

            # Assign the mocked highlighter instance that PythonHighlighter(document) would return
            # This mock_highlighter_instance is what editor.highlighter will be
            mock_highlighter_instance = MockHighlighter.return_value
            editor.highlighter = mock_highlighter_instance

            # Ensure the document() method of the editor returns our mock_document
            # This is important because the highlighter is typically parented to the document
            # editor.document = MagicMock(return_value=mock_document) # This might be too late or override internal
            # Instead, ensure the base QPlainTextEdit's document is the one PythonHighlighter gets
            # This is implicitly handled if PythonHighlighter(editor.document()) is called.
            # The patch ensures MockHighlighter is used.

            editor.thread_pool = MagicMock()
            editor.thread_pool.start = MagicMock()

            if hasattr(editor, 'linter_timer'):
                 editor.linter_timer.stop()
            editor.linter_timer = MagicMock(spec=QTimer)
            # Mock the timeout signal specifically for connection testing
            editor.linter_timer.timeout = MagicMock(spec=Signal)


            editor.completer = MagicMock(spec=QCompleter)
            editor.completer.model = MagicMock(return_value=MagicMock(spec=QStringListModel))
            editor.completer.popup = MagicMock(return_value=MagicMock(spec=QWidget)) # popup returns a QWidget
            # Mock isVisible for the popup
            editor.completer.popup.return_value.isVisible = MagicMock(return_value=False)


    return editor


@pytest.fixture
def code_editor_widget(internal_editor):
    with patch('code_editor._InternalCodeEditor', return_value=internal_editor) as MockInternalEditor:
        # Create a mock parent for CodeEditor if needed, e.g. for window().
        mock_parent_widget = MagicMock(spec=QWidget)
        widget = CodeEditor(parent=mock_parent_widget)
        assert widget.text_edit is internal_editor

        # Mock methods on the parent if CodeEditor interacts with it via self.window()
        # For example, if it needs to get attributes from the main window
        if hasattr(widget, 'window'): # Ensure window() is callable if used
             widget.window = MagicMock(return_value=mock_parent_widget)

    return widget


# --- Tests for _InternalCodeEditor ---

class TestInternalCodeEditorBehavior:

    def test_auto_pairing_parentheses(self, internal_editor):
        internal_editor.insertPlainText("(")
        assert internal_editor.toPlainText() == "()"
        assert internal_editor.textCursor().position() == 1

    def test_auto_pairing_selection_wrap(self, internal_editor):
        internal_editor.insertPlainText("text_to_wrap")
        cursor = internal_editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        internal_editor.setTextCursor(cursor)

        internal_editor.insertPlainText("{")
        assert internal_editor.toPlainText() == "{text_to_wrap}"
        assert internal_editor.textCursor().position() == len("{text_to_wrap") -1


    def test_smart_backspace_pairs(self, internal_editor):
        internal_editor.insertPlainText("()")
        cursor = internal_editor.textCursor()
        cursor.setPosition(1)
        internal_editor.setTextCursor(cursor)

        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Backspace, Qt.KeyboardModifier.NoModifier)
        internal_editor.keyPressEvent(event)

        assert internal_editor.toPlainText() == ""

    def test_tab_indentation_no_selection(self, internal_editor):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Tab, Qt.KeyboardModifier.NoModifier)
        internal_editor.keyPressEvent(event)
        assert internal_editor.toPlainText() == "    "

    def test_tab_indentation_with_selection(self, internal_editor):
        internal_editor.setPlainText("line1\nline2")
        cursor = internal_editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(len("line1\nline2"), QTextCursor.MoveMode.KeepAnchor)
        internal_editor.setTextCursor(cursor)

        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Tab, Qt.KeyboardModifier.NoModifier)
        internal_editor.keyPressEvent(event)
        assert internal_editor.toPlainText() == "    line1\n    line2"

    def test_overtype_closing_char(self, internal_editor):
        internal_editor.insertPlainText(")")
        cursor = internal_editor.textCursor()
        cursor.setPosition(0)
        internal_editor.setTextCursor(cursor)

        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_ParenRight, Qt.KeyboardModifier.NoModifier, ")")
        internal_editor.keyPressEvent(event)

        assert internal_editor.toPlainText() == ")"
        assert internal_editor.textCursor().position() == 1


    def test_linter_integration_triggers_lint_code(self, internal_editor):
        # Linter timer is already mocked in the fixture

        internal_editor.textChanged.emit()
        internal_editor.linter_timer.start.assert_called_once()

        with patch('code_editor.PyflakesLinterWorker') as MockLinterWorker:
            mock_linter_worker_instance = MockLinterWorker.return_value
            # Simulate worker signals structure
            mock_linter_worker_instance.signals = QObject()
            mock_linter_worker_instance.signals.linting_done = MagicMock(spec=Signal)
            mock_linter_worker_instance.signals.error_occurred = MagicMock(spec=Signal)

            internal_editor.lint_code()

            MockLinterWorker.assert_called_once_with(internal_editor.toPlainText())
            internal_editor.thread_pool.start.assert_called_with(mock_linter_worker_instance)


    def test_completer_integration_on_dot(self, internal_editor):
        # Completer and its popup are mocked in the fixture
        # Ensure popup.isVisible() is available on the *return value* of popup()
        internal_editor.completer.popup.return_value.isVisible = MagicMock(return_value=False)


        with patch.object(internal_editor, 'request_completions') as mock_request_completions:
            internal_editor.insertPlainText("object.")
            internal_editor.show_completion_if_dot()
            mock_request_completions.assert_called_once()

    @patch('code_editor.os.path.dirname', return_value='/fake/path')
    @patch('builtins.open', new_callable=mock_open, read_data='{"editor": {"background": "#123456"}}')
    def test_theme_loading(self, mock_file_open, mock_os_path_dirname, internal_editor):
        # Theme is loaded in init. We need to ensure the mock_config_manager returns a theme name.
        internal_editor.config_manager.load_setting.return_value['active_theme'] = "custom_theme.json"

        # Re-initialize or directly call _load_theme_config and _apply_editor_theme
        # Since _load_theme_config is part of init, and init is complex to re-run here,
        # we'll assume it was called. We can test _apply_editor_theme.
        internal_editor._theme_config = {"editor": {"background": "#123456", "text": "#abcdef", "selection_background": "#777777"}} # Simulate loaded theme
        internal_editor._apply_editor_theme()

        assert "#123456" in internal_editor.styleSheet()

    def test_language_detection_and_highlighting_update(self, internal_editor):
        internal_editor.highlighter.set_lexer_for_filename = MagicMock()
        internal_editor.highlighter.rehighlight = MagicMock()
        type(internal_editor.highlighter).lexer = PropertyMock(return_value=MagicMock(name="Python"))

        internal_editor.language_changed_signal = MagicMock(spec=Signal)

        internal_editor.set_file_path_and_update_language("/path/to/file.py")

        internal_editor.highlighter.set_lexer_for_filename.assert_called_once_with("/path/to/file.py", ANY)
        assert internal_editor.current_language == "Python"
        internal_editor.language_changed_signal.emit.assert_called_with("Python")
        internal_editor.linter_timer.start.assert_called()


class TestCodeEditorWidget:

    def test_signal_proxies(self, code_editor_widget, internal_editor):
        mock_slot_text_changed = MagicMock()
        code_editor_widget.textChanged.connect(mock_slot_text_changed)
        internal_editor.textChanged.emit()
        mock_slot_text_changed.assert_called_once()

        mock_slot_cursor_pos = MagicMock()
        code_editor_widget.cursor_position_changed_signal.connect(mock_slot_cursor_pos)
        internal_editor.cursor_position_changed_signal.emit(1, 5)
        mock_slot_cursor_pos.assert_called_with(1, 5)


    def test_method_forwarding(self, code_editor_widget, internal_editor):
        internal_editor.toPlainText = MagicMock(return_value="text content")
        assert code_editor_widget.toPlainText() == "text content"
        internal_editor.toPlainText.assert_called_once()

        internal_editor.setPlainText = MagicMock()
        code_editor_widget.setPlainText("new text")
        internal_editor.setPlainText.assert_called_once_with("new text")

        mock_doc = MagicMock(spec=QTextDocument)
        # Ensure the document() method of the internal editor returns the mock document
        internal_editor.document = MagicMock(return_value=mock_doc)
        assert code_editor_widget.document() == mock_doc
        internal_editor.document.assert_called_once()


    def test_breakpoint_gutter_integration(self, code_editor_widget, internal_editor):
        mock_slot_breakpoint = MagicMock()
        code_editor_widget.breakpoint_toggled.connect(mock_slot_breakpoint)

        code_editor_widget.gutter.breakpoint_toggled.emit(5)
        mock_slot_breakpoint.assert_called_once_with(5)

    def test_line_number_area_update_on_block_count_change(self, code_editor_widget, internal_editor):
        code_editor_widget.line_number_area.updateGeometry = MagicMock()
        code_editor_widget.line_number_area.update = MagicMock()

        # Ensure internal_editor.document() returns a mock that has blockCountChanged signal
        mock_doc_for_signal = MagicMock(spec=QTextDocument)
        mock_doc_for_signal.blockCountChanged = MagicMock(spec=Signal)
        internal_editor.document = MagicMock(return_value=mock_doc_for_signal)

        # Emit the signal from the document mock
        mock_doc_for_signal.blockCountChanged.emit(10)

        # The connection is in CodeEditor's __init__; it connects internal_editor.blockCountChanged
        # However, blockCountChanged is a signal of the DOCUMENT, not the editor itself.
        # So, we should simulate the document's signal.
        # The CodeEditor connects internal_editor.blockCountChanged to its slot.
        # _InternalCodeEditor emits blockCountChanged when its document's signal emits.
        # This test might be more direct if we emit internal_editor.blockCountChanged directly.

        # Let's try emitting the proxied signal from internal_editor
        # This requires internal_editor.blockCountChanged to be a real signal or a MagicMock(spec=Signal)
        internal_editor.blockCountChanged = MagicMock(spec=Signal) # Ensure it's mockable as a signal for this test
        code_editor_widget.setup_editor_connections() # Re-run to connect to this new mock signal

        internal_editor.blockCountChanged.emit(10)

        code_editor_widget.line_number_area.updateGeometry.assert_called()
        code_editor_widget.line_number_area.update.assert_called()

```
