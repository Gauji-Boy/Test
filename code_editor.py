from PySide6.QtWidgets import QPlainTextEdit, QWidget, QHBoxLayout, QTextEdit
from PySide6.QtGui import QColor, QPainter, QFont, QTextFormat, QUndoStack, QAction
from PySide6.QtCore import Qt, QRect, QSize, Signal, Slot

# Assuming python_highlighter.py exists and PythonHighlighter class is correctly defined.
# If not, this import will fail. For the purpose of this subtask, we assume it's available.
try:
    from python_highlighter import PythonHighlighter
except ImportError:
    print("Warning: python_highlighter.py not found or PythonHighlighter class not defined.")
    PythonHighlighter = None

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor
        self.background_color = QColor("#2c3e50") # Example: Dark blue-grey
        self.text_color = QColor("#bdc3c7")       # Example: Light grey

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        if hasattr(self.code_editor, 'line_number_area_paint_event'):
            self.code_editor.line_number_area_paint_event(event)
        else:
            # Fallback paint event if main editor doesn't provide one
            painter = QPainter(self)
            painter.fillRect(event.rect(), self.background_color)


    def update_theme_colors(self, background: QColor, text: QColor):
        self.background_color = background
        self.text_color = text
        self.update()

class _InternalCodeEditor(QPlainTextEdit):
    cursor_position_changed_signal = Signal(int, int)
    modification_changed_signal = Signal(bool)
    breakpoint_toggled_signal = Signal(int) # Line number

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.current_language = "Plain Text"
        self.highlighter = None
        self.exec_highlight_line = None
        self.exec_highlight_format = QTextFormat()
        self.exec_highlight_format.setBackground(QColor("#f1c40f").lighter(160)) # Light yellow
        self.exec_highlight_format.setProperty(QTextFormat.FullWidthSelection, True)
        self.breakpoints = set()

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self._emit_cursor_position_and_highlight) # Changed connection
        self.document().modificationChanged.connect(self.modification_changed_signal.emit)

        self.update_line_number_area_width()
        self._emit_cursor_position_and_highlight() # Initial call

        # Default font - this should be set by CodeEditor wrapper or MainWindow
        # self.setFont(QFont("Fira Code", 11)) # Commented out, to be set externally

    def line_number_area_width(self):
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        # Adjust padding and calculation for better spacing
        space = self.fontMetrics().horizontalAdvance('9') * (digits + 1) + 10 # Add margin
        return space

    def update_line_number_area_width(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event): # This is called by LineNumberArea's paintEvent
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self.line_number_area.background_color)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        font_metrics_height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(self.line_number_area.text_color)
                painter.drawText(0, int(top), self.line_number_area.width() - 5,
                                 font_metrics_height, Qt.AlignRight, number)
                if (block_number + 1) in self.breakpoints:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor("#e74c3c")) # Red for breakpoints
                    marker_size = 8
                    y_pos = top + (font_metrics_height - marker_size) / 2
                    painter.drawEllipse(QRect(4, int(y_pos), marker_size, marker_size)) # Small left margin
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def _emit_cursor_position_and_highlight(self): # Renamed and combined
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            # Use a less intrusive current line highlight or make it themeable
            line_color = QColor(self.palette().alternateBase().color()).lighter(110) if self.palette().alternateBase().isValid() else QColor("#2c3e50").lighter(110)

            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        if self.exec_highlight_line is not None:
            exec_selection = QTextEdit.ExtraSelection()
            exec_selection.format = self.exec_highlight_format
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, self.exec_highlight_line - 1)
            exec_selection.cursor = cursor
            exec_selection.cursor.clearSelection()
            extra_selections.append(exec_selection)

        self.setExtraSelections(extra_selections)

        cursor = self.textCursor()
        self.cursor_position_changed_signal.emit(cursor.blockNumber() + 1, cursor.columnNumber() + 1)

    def set_exec_highlight(self, line_num: int | None):
        self.exec_highlight_line = line_num
        self._emit_cursor_position_and_highlight()

    def set_language(self, language_name: str):
        self.current_language = language_name
        if PythonHighlighter and language_name.lower() == "python":
            self.highlighter = PythonHighlighter(self.document())
        else:
            if self.highlighter:
                self.highlighter.setDocument(None)
            self.highlighter = None
        # print(f"Editor language set to: {language_name if self.highlighter else 'Plain Text'}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            margin = self.viewportMargins().left()
            if event.pos().x() < margin:
                # Simplified blockAt lookup
                cursor = self.cursorForPosition(event.pos())
                line_number = cursor.blockNumber() + 1
                self.toggle_breakpoint(line_number)
                return
        super().mousePressEvent(event)

    def toggle_breakpoint(self, line_number: int):
        if line_number in self.breakpoints:
            self.breakpoints.remove(line_number)
        else:
            self.breakpoints.add(line_number)
        self.breakpoint_toggled_signal.emit(line_number)
        self.line_number_area.update()

    def update_breakpoints_display(self, new_breakpoints: set):
        self.breakpoints = new_breakpoints
        if self.line_number_area:
            self.line_number_area.update()

class CodeEditor(QWidget):
    text_changed = Signal()
    cursor_position_changed = Signal(int, int)
    modification_changed = Signal(bool)
    breakpoint_toggled_in_editor = Signal(str, int) # path, line_number
    control_reclaim_requested = Signal() # For collaborative editing

    def __init__(self, parent=None, file_path_context: str = None):
        super().__init__(parent)
        
        self._file_path_context = file_path_context # Store path for emitting with breakpoint signal
        self.text_edit = _InternalCodeEditor(self)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

        # Forward signals from internal editor
        self.text_edit.textChanged.connect(self.text_changed)
        self.text_edit.cursor_position_changed_signal.connect(self.cursor_position_changed)
        self.text_edit.modification_changed_signal.connect(self.modification_changed)
        self.text_edit.breakpoint_toggled_signal.connect(self._on_internal_breakpoint_toggled)

        # Default font for editor
        editor_font = QFont("Fira Code", 11) # Default, can be made configurable
        self.text_edit.setFont(editor_font)
        
        # Update line number area theme based on editor's palette (which can be set by QSS)
        # This is a basic example; QSS might also style LineNumberArea directly.
        # self.text_edit.line_number_area.update_theme_colors(
        #     self.text_edit.palette().color(self.text_edit.backgroundRole()).darker(110),
        #     self.text_edit.palette().color(self.text_edit.foregroundRole()).darker(110)
        # )


    @Slot(int)
    def _on_internal_breakpoint_toggled(self, line_number: int):
        if self._file_path_context: # Only emit if path context is known
            self.breakpoint_toggled_in_editor.emit(self._file_path_context, line_number)
        else:
            print("CodeEditor: Breakpoint toggled but no file_path_context set.")


    def set_text(self, text: str, is_modified: bool = False):
        # Disconnect modificationChanged temporarily to avoid signaling dirty on programmatic text set
        try:
            self.text_edit.modification_changed_signal.disconnect(self.modification_changed)
        except RuntimeError: pass
        
        self.text_edit.setPlainText(text)
        self.text_edit.document().setModified(is_modified) # Set modified state as passed
        
        self.text_edit.modification_changed_signal.connect(self.modification_changed)

    def get_text(self) -> str:
        return self.text_edit.toPlainText()

    def set_language(self, language_name: str):
        self.text_edit.set_language(language_name)

    def is_modified(self) -> bool:
        return self.text_edit.document().isModified()

    def set_modified(self, modified: bool):
        self.text_edit.document().setModified(modified)

    def get_undo_stack(self) -> QUndoStack:
        return self.text_edit.document().undoStack()

    def set_read_only(self, read_only: bool):
        self.text_edit.setReadOnly(read_only)

    def set_exec_highlight(self, line_num: int | None):
        self.text_edit.set_exec_highlight(line_num)

    def update_breakpoints_display(self, new_breakpoints: set):
        self.text_edit.update_breakpoints_display(new_breakpoints)

    def set_file_path_context(self, path: str):
        self._file_path_context = path
        # Potentially update language based on new path's extension here
        # lang = self._guess_language_from_path(path)
        # if lang: self.set_language(lang)

    def _guess_language_from_path(self, path:str) -> str | None:
        # Basic language guessing, can be expanded
        if path.endswith(".py"): return "Python"
        if path.endswith(".js"): return "JavaScript"
        if path.endswith(".html"): return "HTML"
        if path.endswith(".css"): return "CSS"
        if path.endswith(".json"): return "JSON"
        return None


    @Slot()
    def undo(self):
        self.text_edit.undo()

    @Slot()
    def redo(self):
        self.text_edit.redo()

    def ensure_cursor_visible(self):
        self.text_edit.ensureCursorVisible()

    def move_cursor(self, operation: QTextCursor.MoveOperation, mode: QTextCursor.MoveMode = QTextCursor.MoveAnchor):
        self.text_edit.moveCursor(operation, mode)

    def get_document(self): # Expose document for advanced operations if needed by MainWindow
        return self.text_edit.document()