import logging
import os
import sys # Added for stderr print in case of file logging setup error

def setup_logging(level=logging.INFO, log_to_file=False):
    """
    Sets up basic logging configuration for the application.
    """
    root_logger = logging.getLogger()

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(level)

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    if log_to_file:
        try:
            log_dir = os.path.join(os.path.expanduser("~"), ".aether_editor", "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file_path = os.path.join(log_dir, "aether_editor.log")

            file_handler = logging.FileHandler(log_file_path, mode='a')
            file_formatter = logging.Formatter(
                '%(asctime)s - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG) # Example: Log DEBUG level to file
            root_logger.addHandler(file_handler)
            # Use a print here for initial setup message, as this function sets up the logger itself.
            print(f"INFO: Aether Editor logging to file: {log_file_path}")
        except Exception as e:
            print(f"ERROR: Could not set up file logger: {e}", file=sys.stderr)

if __name__ == '__main__':
    setup_logging(level=logging.DEBUG, log_to_file=True)

    logger = logging.getLogger(__name__) # Get logger for this module
    logger.debug("This is a debug message from logging_config.")
    logger.info("This is an info message from logging_config.")
    logger.warning("This is a warning from logging_config.")
    logger.error("This is an error from logging_config.")
    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("A handled exception occurred (division by zero) in logging_config.")

    logging.getLogger("main_test").info("Test message from main_test logger via logging_config.")
    logging.info("Test message from root logger directly via logging_config.")
