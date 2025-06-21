import os
import logging
import sys # Added for sys.executable
import platform # Added for platform.system()
from PySide6.QtCore import QObject, Slot, QProcess
from PySide6.QtWidgets import QMessageBox, QListWidgetItem, QTreeWidgetItem
from code_editor import CodeEditor
from config_manager import ConfigManager
from config import RUNNER_CONFIG as DEFAULT_RUNNER_CONFIG
from config import DEFAULT_EXTENSION_TO_LANGUAGE_MAP
from typing import Any, cast, TYPE_CHECKING, Optional # Added TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from main_window import MainWindow # Assuming main_window.py

logger = logging.getLogger(__name__)

class ExecutionCoordinator(QObject):
    main_win: Optional['MainWindow'] # Forward reference, now Optional
    active_breakpoints: dict[str, set[int]]
    current_run_mode: str
    config_manager: ConfigManager
    runner_config: dict[str, Any]
    extension_to_language_map: dict[str, str]

    def __init__(self) -> None: # Removed main_window parameter
        super().__init__()
        self.main_win = None # Initialize as None
        self.active_breakpoints = {} # Initialize as empty
        self.current_run_mode = "Run" # Default value

        self.config_manager = ConfigManager() # This can be initialized without main_win
        self.runner_config = self.config_manager.load_setting('runner_config', DEFAULT_RUNNER_CONFIG)
        if self.runner_config is DEFAULT_RUNNER_CONFIG:
            logger.info("Using default RUNNER_CONFIG as it was not found in settings.")
        else:
            logger.info("Loaded RUNNER_CONFIG from settings.")
        # logger.debug(f"Effective RUNNER_CONFIG: {self.runner_config}") # Removed temp log

        self.extension_to_language_map = self.config_manager.load_setting('extension_to_language_map', DEFAULT_EXTENSION_TO_LANGUAGE_MAP)
        if self.extension_to_language_map is DEFAULT_EXTENSION_TO_LANGUAGE_MAP:
            logger.info("Using default EXTENSION_TO_LANGUAGE_MAP as it was not found in settings.")
        else:
            logger.info("Loaded EXTENSION_TO_LANGUAGE_MAP from settings.")

    def set_main_window_ref(self, main_window: 'MainWindow') -> None:
        self.main_win = main_window
        if self.main_win:
            # Initialize attributes that depend on main_window
            self.active_breakpoints = self.main_win.active_breakpoints
            self.current_run_mode = self.main_win.current_run_mode
        else: # Should not happen
            self.active_breakpoints = {}
            self.current_run_mode = "Run"


    @Slot()
    def _handle_run_request(self) -> None:
        if not self.main_win:
            logger.error("ExecutionCoordinator: MainWindow reference not set.")
            return

        editor: CodeEditor | None = self.main_win._get_current_code_editor()
        if not editor:
            self.main_win.status_bar.showMessage("No active editor to run.", 3000)
            return

        if not self.main_win.editor_file_coordinator.save_current_file():
            self.main_win.status_bar.showMessage("Save operation cancelled or failed. Run aborted.", 3000)
            return

        file_path: str | None = self.main_win.editor_file_coordinator.editor_to_path.get(editor)
        if not file_path or file_path.startswith("untitled:") or not os.path.isfile(file_path):
            # More robust check for actual file
            error_msg = f"Cannot run. Please save the file and ensure it's a valid file path.\nAttempted path: {file_path}"
            if file_path and not os.path.isfile(file_path) and os.path.isdir(file_path):
                 error_msg = f"Cannot run a directory directly. Please select a file to run.\nAttempted path: {file_path}"
            elif not file_path or file_path.startswith("untitled:"):
                 error_msg = "Please save the file before running."

            QMessageBox.warning(self.main_win, "Execution Error", error_msg)
            logger.error(f"Execution Error: Invalid file_path for run request: {file_path}")
            return

        _fname, extension = os.path.splitext(file_path)
        language_name: str | None = self.extension_to_language_map.get(extension.lower())
        if not language_name:
            logger.warning(f"No language found for extension '{extension}' in extension_to_language_map.")
            QMessageBox.warning(self.main_win, "Execution Error", f"No language is configured for file type '{extension}'.")
            return

        # --- MODIFIED PYTHON EXECUTION FOR WINDOWS ---
        if language_name == "Python" and platform.system() == "Windows":
            logger.info("Using sys.executable for Python on Windows.")
            python_executable = sys.executable
            quoted_python_executable = f'"{python_executable}"'

            # Get arguments (like -u, {file}) from runner_config, skipping the executable part
            original_template: list[str] | None = self.runner_config.get(language_name, {}).get("run")
            args_template: list[str] = []
            if original_template and len(original_template) > 1:
                args_template = original_template[1:] # Skip the original executable, take rest of args
            elif original_template and "{file}" in original_template[0]: # e.g. if template was just ["{file}"]
                args_template = original_template
            else: # Fallback if template is minimal or unusual
                args_template = ["-u", "{file}"]
                logger.warning(f"Python run template for Windows was minimal or not found, defaulting to: {args_template}")

            # logger.debug(f"Language: {language_name}, Args template for sys.executable: {args_template}") # Removed temp log

            # Ensure paths are quoted
            quoted_file_path = f'"{file_path}"'
            # output_file_no_ext is not typically used for Python run, but include if necessary for other languages
            # quoted_output_file_no_ext = f'"{output_file_no_ext}"'

            command_parts = [] # Start with PowerShell call operator and quoted executable
            # PowerShell call operator '&' is needed if the executable path contains spaces or certain characters.
            # It's safer to include it.
            command_parts.append("&")
            command_parts.append(quoted_python_executable)

            for part_template in args_template:
                part: str = part_template.replace("{file}", quoted_file_path)
                # part = part.replace("{output_file}", quoted_output_file_no_ext) # If needed
                command_parts.append(part)

            # logger.debug(f"Command parts for Python on Windows (using sys.executable): {command_parts}") # Removed temp log

        else: # Original logic for other OS or languages
            command_template_list: list[str] | None = self.runner_config.get(language_name, {}).get("run")
            # logger.debug(f"Language: {language_name}, Command template list: {command_template_list}") # Removed temp log
            if not command_template_list or not isinstance(command_template_list, list):
                logger.warning(f"No 'run' command configured or invalid format for language '{language_name}' in self.runner_config.")
                QMessageBox.warning(self.main_win, "Execution Error", f"No 'run' command is configured or it's in an invalid format for the language '{language_name}'.")
                return

            # Ensure paths are quoted to handle spaces
            quoted_file_path = f'"{file_path}"'
            quoted_output_file_no_ext = f'"{output_file_no_ext}"'

            command_parts: list[str] = []
            for part_template in command_template_list:
                # Replace placeholders with their quoted versions
                part: str = part_template.replace("{file}", quoted_file_path)
                part = part.replace("{output_file}", quoted_output_file_no_ext)
                command_parts.append(part)

            # logger.debug(f"Command parts before Pithon check: {command_parts}") # Removed temp log

            # Check for "Pithon" typo in Python commands (relevant for non-Windows Python or other languages)
            if language_name == "Python" and command_parts and \
               (command_parts[0].lower() == "pithon" or command_parts[0].lower() == "pithon.exe"):
                logger.warning(
                    "Potential typo 'Pithon' detected as the Python executable in the run command. "
                    "This might be from 'config/runner_config.json'. "
                    "Please verify your Python command configuration."
                )
                if command_parts[0].lower() in ["pithon", "pithon.exe"]:
                     corrected_executable = "python.exe" if os.name == 'nt' else "python" # Should be python for non-windows
                     logger.info(f"Attempting to correct '{command_parts[0]}' to '{corrected_executable}'.")
                     QMessageBox.information(self.main_win, "Potential Typo", f"Corrected potential typo '{command_parts[0]}' to '{corrected_executable}'. Please check your runner configuration.")
                     command_parts[0] = corrected_executable

        if not command_template_list or not isinstance(command_template_list, list):
            logger.warning(f"No 'run' command configured or invalid format for language '{language_name}' in self.runner_config.")
            QMessageBox.warning(self.main_win, "Execution Error", f"No 'run' command is configured or it's in an invalid format for the language '{language_name}'.")
            return

        working_dir: str = os.path.dirname(file_path) or os.getcwd()
        output_file_no_ext: str = os.path.splitext(file_path)[0]

        # Ensure paths are quoted to handle spaces
        # Note: If runner_config templates already quote placeholders, this might lead to double quoting.
        #       The default config does not quote placeholders. This change assumes placeholders are bare.
        quoted_file_path = f'"{file_path}"'
        quoted_output_file_no_ext = f'"{output_file_no_ext}"'

        command_parts: list[str] = []
        for part_template in command_template_list:
            # Replace placeholders with their quoted versions
            part: str = part_template.replace("{file}", quoted_file_path)
            part = part.replace("{output_file}", quoted_output_file_no_ext)
            command_parts.append(part)

        logger.debug(f"Command parts before Pithon check: {command_parts}") # Log parts before correction

        if not command_parts:
            QMessageBox.warning(self.main_win, "Execution Error", "Command became empty after processing template.")
            return

        # Check for "Pithon" typo in Python commands
        if language_name == "Python" and command_parts and \
           (command_parts[0].lower() == "pithon" or command_parts[0].lower() == "pithon.exe"):
            logger.warning(
                "Potential typo 'Pithon' detected as the Python executable in the run command. "
                "This might be from 'config/runner_config.json'. "
                "Please verify your Python command configuration."
            )
            # Forcing correction to "python" if "pithon" is detected and it's the only part of the executable name
            if command_parts[0].lower() in ["pithon", "pithon.exe"]:
                 corrected_executable = "python.exe" if os.name == 'nt' else "python"
                 logger.info(f"Attempting to correct '{command_parts[0]}' to '{corrected_executable}'.")
                 QMessageBox.information(self.main_win, "Potential Typo", f"Corrected potential typo '{command_parts[0]}' to '{corrected_executable}'. Please check your runner configuration.")
                 command_parts[0] = corrected_executable


        # Construct the full command string to be executed in the terminal
        command_string = " ".join(command_parts)
        # logger.debug(f"Final command string to be executed: {command_string}") # Removed temp log

        # Ensure the terminal widget is available and execute the command
        if self.main_win and hasattr(self.main_win, 'terminal_widget') and self.main_win.terminal_widget:
            self.main_win.terminal_widget.execute_ide_command(command_string)
            # Switch focus to the terminal tab
            if hasattr(self.main_win, 'bottom_dock_tab_widget') and hasattr(self.main_win, 'terminal_widget'):
                for i in range(self.main_win.bottom_dock_tab_widget.count()):
                    if self.main_win.bottom_dock_tab_widget.widget(i) == self.main_win.terminal_widget:
                        self.main_win.bottom_dock_tab_widget.setCurrentIndex(i)
                        break
            if hasattr(self.main_win, 'terminal_dock'):
                self.main_win.terminal_dock.show()
                self.main_win.terminal_dock.raise_()
                self.main_win.terminal_widget.setFocus() # Set focus to the terminal input widget
        else:
            QMessageBox.warning(self.main_win, "Execution Error", "Terminal widget is not available.")
            logger.error("ExecutionCoordinator: Terminal widget not found in main_win for executing IDE command.")


    @Slot()
    def _handle_debug_request(self) -> None:
        if not self.main_win:
            logger.error("ExecutionCoordinator: MainWindow reference not set.")
            return

        editor: CodeEditor | None = self.main_win._get_current_code_editor()
        if not editor:
            QMessageBox.information(self.main_win, "Debug", "No active editor to debug.")
            return

        file_path: str | None = editor.file_path
        if not file_path or file_path.startswith("untitled:"):
            QMessageBox.warning(self.main_win, "Debug", "Please save the file before debugging.")
            return

        if not self.main_win.editor_file_coordinator.save_current_file():
            QMessageBox.warning(self.main_win, "Debug", "Save operation cancelled or failed. Debug aborted.")
            return

        _fname, extension = os.path.splitext(file_path)
        language_name: str | None = self.extension_to_language_map.get(extension.lower())
        if not language_name:
            logger.warning(f"No language found for extension '{extension}' in extension_to_language_map.")
            QMessageBox.warning(self.main_win, "Debug Error", f"No language is configured for file type '{extension}'.")
            return

        command_template_list: list[str] | None = self.runner_config.get(language_name, {}).get("debug")
        if not command_template_list or not isinstance(command_template_list, list):
            logger.warning(f"No 'debug' command configured or invalid format for language '{language_name}' in self.runner_config.")
            QMessageBox.warning(self.main_win, "Debug Error", f"No 'debug' command is configured or it's in an invalid format for the language '{language_name}'.")
            return

        working_dir: str = os.path.dirname(file_path) or os.getcwd()
        output_file_no_ext: str = os.path.splitext(file_path)[0]

        command_parts: list[str] = []
        for part_template in command_template_list:
            part: str = part_template.replace("{file}", file_path)
            part = part.replace("{output_file}", output_file_no_ext)
            command_parts.append(part)

        if not command_parts:
            QMessageBox.warning(self.main_win, "Debug Error", "Command became empty after processing template.")
            return

        for path, lines_set in self.active_breakpoints.items():
            self.main_win.debug_manager.update_internal_breakpoints(path, lines_set)

        self.main_win.debug_manager.start_session(cast(str, file_path))


    @Slot(str)
    def _handle_process_output(self, output_str: str) -> None:
        if not self.main_win: return
        if hasattr(self.main_win, 'command_output_viewer') and self.main_win.command_output_viewer:
            self.main_win.command_output_viewer.append_output(output_str)
            if hasattr(self.main_win, 'bottom_dock_tab_widget'):
                self.main_win.bottom_dock_tab_widget.setCurrentWidget(self.main_win.command_output_viewer)
        else:
            logger.info(f"Process Output (no command_output_viewer): {output_str}")

    @Slot()
    def _handle_process_started(self) -> None:
        if not self.main_win: return
        logger.info("Process started.")
        self.main_win.status_bar.showMessage("Process started...")
        if hasattr(self.main_win, 'run_action_button'):
            self.main_win.run_action_button.setEnabled(False)
        if hasattr(self.main_win, 'debug_action_button'):
            self.main_win.debug_action_button.setEnabled(False)

        if hasattr(self.main_win, 'command_output_viewer') and self.main_win.command_output_viewer:
            self.main_win.command_output_viewer.clear_output()
            if hasattr(self.main_win, 'bottom_dock_tab_widget'):
                self.main_win.bottom_dock_tab_widget.setCurrentWidget(self.main_win.command_output_viewer)
            if hasattr(self.main_win, 'terminal_dock'):
                self.main_win.terminal_dock.show()
                self.main_win.terminal_dock.raise_()

    @Slot(int, QProcess.ExitStatus)
    def _handle_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if not self.main_win: return
        status_text: str = "successfully" if exit_status == QProcess.NormalExit and exit_code == 0 else f"with errors (code: {exit_code})"
        message: str = f"Process finished {status_text}."
        logger.info(message)
        self.main_win.status_bar.showMessage(message, 5000)
        if hasattr(self.main_win, 'command_output_viewer') and self.main_win.command_output_viewer:
            self.main_win.command_output_viewer.append_output(f"\n--- {message} ---\n")
        if hasattr(self.main_win, 'run_action_button'):
            self.main_win.run_action_button.setEnabled(True)
        if hasattr(self.main_win, 'debug_action_button'):
            self.main_win.debug_action_button.setEnabled(True)

    @Slot(str)
    def _handle_process_error(self, error_message: str) -> None:
        if not self.main_win: return
        full_error_message: str = f"Process error: {error_message}"
        logger.error(f"Process execution error: {error_message}")
        QMessageBox.critical(self.main_win, "Process Error", full_error_message)
        self.main_win.status_bar.showMessage(full_error_message, 5000)
        if hasattr(self.main_win, 'command_output_viewer') and self.main_win.command_output_viewer:
            self.main_win.command_output_viewer.append_output(f"\n--- ERROR: {error_message} ---\n")
            if hasattr(self.main_win, 'bottom_dock_tab_widget'):
                self.main_win.bottom_dock_tab_widget.setCurrentWidget(self.main_win.command_output_viewer)
        if hasattr(self.main_win, 'run_action_button'):
            self.main_win.run_action_button.setEnabled(True)
        if hasattr(self.main_win, 'debug_action_button'):
            self.main_win.debug_action_button.setEnabled(True)

    @Slot()
    def _on_debug_session_started(self) -> None:
        if not self.main_win: return
        logger.info("Debug session started.")
        self.main_win.debugger_toolbar.setVisible(True)
        if hasattr(self.main_win, 'run_action_button'): self.main_win.run_action_button.setEnabled(False)
        if hasattr(self.main_win, 'debug_action_button'): self.main_win.debug_action_button.setEnabled(False)

        self.main_win.continue_action.setEnabled(True)
        self.main_win.step_over_action.setEnabled(False)
        self.main_win.step_into_action.setEnabled(False)
        self.main_win.step_out_action.setEnabled(False)
        self.main_win.stop_action.setEnabled(True)

    @Slot()
    def _on_debug_session_stopped(self) -> None:
        if not self.main_win: return
        logger.info("Debug session stopped.")
        self.main_win.debugger_toolbar.setVisible(False)
        if hasattr(self.main_win, 'run_action_button'): self.main_win.run_action_button.setEnabled(True)
        if hasattr(self.main_win, 'debug_action_button'): self.main_win.debug_action_button.setEnabled(True)

        self.main_win.variables_panel.clear()
        self.main_win.variables_panel.addTopLevelItem(QTreeWidgetItem(self.main_win.variables_panel, ["Locals"]))
        self.main_win.call_stack_panel.clear()

        if self.main_win.editor_file_coordinator: # Check if coordinator exists
            for editor in self.main_win.editor_file_coordinator.path_to_editor.values():
                if isinstance(editor, CodeEditor):
                    editor.set_exec_highlight(None)

    @Slot(int, str, list, list)
    def _on_debugger_paused(self, thread_id: int, reason: str, call_stack: list[dict[str, Any]], variables: list[dict[str, Any]]) -> None:
        if not self.main_win: return
        logger.info(f"Debugger paused. Thread: {thread_id}, Reason: {reason}")
        self.main_win.call_stack_panel.clear()
        for frame in call_stack:
            item_text: str = f"{os.path.basename(frame['file'])}:{frame['line']} - {frame['name']}"
            self.main_win.call_stack_panel.addItem(QListWidgetItem(item_text))

        self.main_win.variables_panel.clear()
        if not variables:
            placeholder_item = QTreeWidgetItem(self.main_win.variables_panel, ["No variables in current scope."])
            self.main_win.variables_panel.addTopLevelItem(placeholder_item)
        else:
            for var in variables:
                var_item = QTreeWidgetItem([var['name'], var['value'], var['type']])
                self.main_win.variables_panel.addTopLevelItem(var_item)
        self.main_win.variables_panel.expandAll()

        active_editor: CodeEditor | None = self.main_win._get_current_code_editor()
        if call_stack:
            current_frame: dict[str, Any] = call_stack[0]
            file_path: str = current_frame['file']
            line_number: int = current_frame['line']
            if active_editor and active_editor.file_path == file_path:
                active_editor.set_exec_highlight(line_number)
            elif active_editor:
                active_editor.set_exec_highlight(None)
        elif active_editor:
            active_editor.set_exec_highlight(None)

        self.main_win.continue_action.setEnabled(True)
        self.main_win.step_over_action.setEnabled(True)
        self.main_win.step_into_action.setEnabled(True)
        self.main_win.step_out_action.setEnabled(True)
        self.main_win.stop_action.setEnabled(True)
        self.main_win.activateWindow()
        self.main_win.raise_()
        if self.main_win.left_tab_widget:
            for i in range(self.main_win.left_tab_widget.count()):
                if self.main_win.left_tab_widget.tabText(i) == "Debugger":
                    self.main_win.left_tab_widget.setCurrentIndex(i)
                    break

    @Slot()
    def _on_debugger_resumed(self) -> None:
        if not self.main_win: return
        logger.info("Debugger resumed.")
        self.main_win.variables_panel.clear()
        self.main_win.variables_panel.addTopLevelItem(QTreeWidgetItem(self.main_win.variables_panel, ["Running..."]))
        self.main_win.call_stack_panel.clear()
        self.main_win.call_stack_panel.addItem(QListWidgetItem("Running..."))

        active_editor: CodeEditor | None = self.main_win._get_current_code_editor()
        if active_editor:
            active_editor.set_exec_highlight(None)

        self.main_win.continue_action.setEnabled(False)
        self.main_win.step_over_action.setEnabled(False)
        self.main_win.step_into_action.setEnabled(False)
        self.main_win.step_out_action.setEnabled(False)
        self.main_win.stop_action.setEnabled(True)

    @Slot(int)
    def _handle_breakpoint_toggled(self, line_number: int) -> None:
        if not self.main_win: return
        editor: CodeEditor | None = self.main_win._get_current_code_editor()
        if not editor:
            return

        file_path: str | None = editor.file_path
        if not file_path or file_path.startswith("untitled:"):
            QMessageBox.warning(self.main_win, "Breakpoints", "Please save the file before setting breakpoints.")
            return

        # Ensure file_path is a valid key before proceeding
        if file_path not in self.active_breakpoints:
            self.active_breakpoints[file_path] = set()

        if line_number in self.active_breakpoints[file_path]:
            self.active_breakpoints[file_path].remove(line_number)
        else:
            self.active_breakpoints[file_path].add(line_number)

        self.main_win.breakpoints_panel.clear()
        for path, lines in self.active_breakpoints.items():
            if not lines:
                continue
            path_basename: str = os.path.basename(path)
            for line_num_in_set in sorted(list(lines)):
                self.main_win.breakpoints_panel.addItem(QListWidgetItem(f"{path_basename}:{line_num_in_set}"))

        editor.gutter.update_breakpoints_display(self.active_breakpoints.get(file_path, set()))

        lines_for_file: set[int] = self.active_breakpoints.get(file_path, set())

        if file_path: # Ensure file_path is not None
            self.main_win.debug_manager.update_internal_breakpoints(file_path, lines_for_file)

            if self.main_win.debug_manager.dap_client and \
               self.main_win.debug_manager.dap_client.isOpen() and \
               self.main_win.debug_manager._dap_request_pending_response.get('handshake_complete', False):
                self.main_win.debug_manager.set_breakpoints_on_adapter(file_path, list(lines_for_file))

# Ensure a newline at the end of the file
