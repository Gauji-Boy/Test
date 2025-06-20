import os
import logging
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

        self.extension_to_language_map = self.config_manager.load_setting('extension_to_language_map', DEFAULT_EXTENSION_TO_LANGUAGE_MAP)
        if self.extension_to_language_map is DEFAULT_EXTENSION_TO_LANGUAGE_MAP:
            logger.info("Using default EXTENSION_TO_LANGUAGE_MAP as it was not found in settings.")
        else:
            logger.info("Loaded EXTENSION_TO_LANGUAGE_MAP from settings.")

        self.compiled_exe_path = None
        self.is_running_cpp_sequence = False
        self.cpp_compilation_working_dir = None # To store working_dir for the execution step

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
        if not file_path or file_path.startswith("untitled:"):
            QMessageBox.warning(self.main_win, "Execution Error", "Please save the file before running.")
            return

        _fname, extension = os.path.splitext(file_path)
        language_name: str | None = self.extension_to_language_map.get(extension.lower())
        if not language_name:
            logger.warning(f"No language found for extension '{extension}' in extension_to_language_map.")
            QMessageBox.warning(self.main_win, "Execution Error", f"No language is configured for file type '{extension}'.")
            return

        command_template_list: list[str] | None = self.runner_config.get(language_name, {}).get("run")
        if not command_template_list or not isinstance(command_template_list, list):
            logger.warning(f"No 'run' command configured or invalid format for language '{language_name}' in self.runner_config.")
            QMessageBox.warning(self.main_win, "Execution Error", f"No 'run' command is configured or it's in an invalid format for the language '{language_name}'.")
            return

        working_dir: str = os.path.dirname(file_path) or os.getcwd() # Define working_dir earlier
        output_file_no_ext: str = os.path.splitext(file_path)[0] # Define output_file_no_ext earlier

        # Path preparations (assuming file_path and output_file_no_ext are defined earlier)
        # These are unquoted, QProcess will handle quoting for direct calls if needed.
        # Ensure logger.debug lines for raw paths and stripping are here if you want to keep them
        logger.debug(f"Raw file_path before quoting: '[{file_path}]'")
        logger.debug(f"Raw output_file_no_ext before quoting: '[{output_file_no_ext}]'")

        file_path = file_path.strip()
        output_file_no_ext = output_file_no_ext.strip()

        file_path_for_command = file_path
        output_file_exe_path_for_command = output_file_no_ext + ".exe"
        output_file_no_ext_for_command = output_file_no_ext
        # Add any other general placeholder values you might need, e.g. for Java class_name
        # class_name_for_command = os.path.splitext(os.path.basename(file_path_for_command))[0]


        # --- C++ specific compile-then-run logic ---
        if language_name == "C++": # Assuming "run" implies compile then execute for C++
            self.is_running_cpp_sequence = True
            self.compiled_exe_path = output_file_exe_path_for_command # Store for execution after successful compile
            self.cpp_compilation_working_dir = working_dir # Store for use in execution step

            # 1. Construct C++ Compilation Command from runner_config
            # command_template_list should be like: ["g++", "{file}", "-o", "{output_file_exe}"]
            cpp_compile_command_parts: list[str] = []
            for part_template in command_template_list:
                part: str = part_template
                part = part.replace("{file}", file_path_for_command)
                part = part.replace("{output_file_exe}", output_file_exe_path_for_command)
                cpp_compile_command_parts.append(part)

            logger.info(f"Executing C++ compilation: {cpp_compile_command_parts} in {working_dir}")

            # Ensure signal is connected only once or disconnect before connecting
            try:
                self.main_win.process_manager.process_finished.disconnect(self._handle_cpp_compilation_finished)
            except RuntimeError: # Catches "signal not connected" or already disconnected
                pass
            self.main_win.process_manager.process_finished.connect(self._handle_cpp_compilation_finished)

            self.main_win.process_manager.execute(cpp_compile_command_parts, working_dir)

        # --- Generic command execution logic (for non-C++ languages or other command types) ---
        else:
            self.is_running_cpp_sequence = False # Ensure flag is reset

            generic_command_parts: list[str] = []
            for part_template in command_template_list:
                part: str = part_template
                part = part.replace("{file}", file_path_for_command)
                part = part.replace("{output_file_exe}", output_file_exe_path_for_command)
                part = part.replace("{output_file}", output_file_no_ext_for_command)
                # Example for Java:
                # if language_name == "Java" and "{class_name}" in part:
                #     part = part.replace("{class_name}", class_name_for_command)
                generic_command_parts.append(part)

            # Logic for cmd.exe (if any command still uses it, though C++ doesn't anymore for compilation)
            if generic_command_parts and generic_command_parts[0].lower() == "cmd.exe" and \
               len(generic_command_parts) > 1 and generic_command_parts[1] == "/c" and \
               len(generic_command_parts) > 2:
                actual_command = " ".join(generic_command_parts[2:])
                # If actual_command needs internal quotes for paths with spaces, they should have been added
                # during the placeholder replacement if this path is ever reactivated.
                # For now, this cmd.exe path is not used by our modified C++ config.
                final_command_parts = [generic_command_parts[0], generic_command_parts[1], actual_command]
                logger.info(f"Executing command (via cmd.exe): {final_command_parts} in {working_dir}")
            else: # Direct execution
                final_command_parts = generic_command_parts
                logger.info(f"Executing command (direct): {final_command_parts} in {working_dir}")

            self.main_win.process_manager.execute(final_command_parts, working_dir)

    @Slot(int, QProcess.ExitStatus)
    def _handle_cpp_compilation_finished(self, exit_code, exit_status):
        # IMPORTANT: Disconnect immediately
        try:
            self.main_win.process_manager.process_finished.disconnect(self._handle_cpp_compilation_finished)
        except RuntimeError:
            logger.warning("_handle_cpp_compilation_finished: Could not disconnect signal.")

        if not self.is_running_cpp_sequence:
            return # Not part of the C++ sequence we initiated

        # Store these to local variables before resetting instance variables
        compiled_exe_path_local = self.compiled_exe_path
        working_dir_local = self.cpp_compilation_working_dir # Use the stored working_dir

        # Reset instance variables for the next sequence
        self.is_running_cpp_sequence = False
        self.compiled_exe_path = None
        self.cpp_compilation_working_dir = None

        if exit_code == 0 and exit_status == QProcess.NormalExit:
            logger.info(f"C++ compilation successful. Executing: {compiled_exe_path_local}")
            if compiled_exe_path_local:
                # Determine working directory for the executable
                # Using the directory of the executable itself is often a good default
                exe_working_dir = os.path.dirname(compiled_exe_path_local)
                if not os.path.isdir(exe_working_dir): # Check if dirname returned a valid dir
                    logger.warning(f"Could not determine executable's directory: {exe_working_dir}. Falling back to compilation working_dir: {working_dir_local}")
                    exe_working_dir = working_dir_local # Fallback

                execution_command = [compiled_exe_path_local] # QProcess handles paths with spaces

                logger.info(f"Executing compiled C++ program: {execution_command} in {exe_working_dir}")
                self.main_win.process_manager.execute(execution_command, exe_working_dir)
            else:
                logger.error("C++ compilation successful, but compiled_exe_path was not available.")
        else:
            logger.error(f"C++ compilation failed. Exit code: {exit_code}, Status: {exit_status}. Not executing.")

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
