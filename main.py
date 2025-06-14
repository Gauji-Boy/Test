import sys
import os # Added for path joining
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase # Added for font loading
from main_window import MainWindow

# Determine the absolute path to the application's directory
# This is important for finding assets and stylesheets correctly,
# especially when the script is run from different working directories.
APP_DIR = os.path.dirname(os.path.abspath(__file__))

def load_fonts():
    # Construct absolute paths to font files within the 'assets' directory
    assets_dir = os.path.join(APP_DIR, "assets")
    inter_regular_path = os.path.join(assets_dir, "Inter-Regular.ttf")
    fira_code_regular_path = os.path.join(assets_dir, "FiraCode-Regular.ttf")
    material_symbols_path = os.path.join(assets_dir, "MaterialSymbolsOutlined.ttf")

    # Load application fonts
    font_id_inter = QFontDatabase.addApplicationFont(inter_regular_path)
    if font_id_inter == -1:
        print(f"Warning: Could not load Inter-Regular.ttf from {inter_regular_path}")
    else:
        inter_family = QFontDatabase.applicationFontFamilies(font_id_inter)[0]
        print(f"Successfully loaded font: {inter_family}")

    font_id_fira = QFontDatabase.addApplicationFont(fira_code_regular_path)
    if font_id_fira == -1:
        print(f"Warning: Could not load FiraCode-Regular.ttf from {fira_code_regular_path}")
    else:
        fira_family = QFontDatabase.applicationFontFamilies(font_id_fira)[0]
        print(f"Successfully loaded font: {fira_family}")

    font_id_material = QFontDatabase.addApplicationFont(material_symbols_path)
    if font_id_material == -1:
        print(f"Warning: Could not load MaterialSymbolsOutlined.ttf from {material_symbols_path}")
    else:
        material_family = QFontDatabase.applicationFontFamilies(font_id_material)[0]
        print(f"Successfully loaded font: {material_family} (for icons)")
    
    # Note: The actual font names to be used in QSS or programmatically
    # will be "Inter", "Fira Code", and "Material Symbols Outlined" (or similar,
    # depending on what QFontDatabase reports after loading the actual files).
    # The print statements above will show the loaded family names.

def main():
    app = QApplication(sys.argv)

    # Load custom fonts
    load_fonts()

    # Load and apply stylesheet
    # Construct absolute path to styling.qss
    stylesheet_path = os.path.join(APP_DIR, "styling.qss")
    try:
        with open(stylesheet_path, "r") as f:
            style_sheet = f.read()
        app.setStyleSheet(style_sheet)
        print(f"Successfully loaded stylesheet from {stylesheet_path}")
    except FileNotFoundError:
        print(f"Warning: styling.qss not found at {stylesheet_path}. Using default styles.")
    except Exception as e:
        print(f"Error loading stylesheet: {e}")


    # Get the initial path from command line arguments, if provided
    initial_path = None
    if len(sys.argv) > 1:
        script_path = os.path.abspath(sys.argv[1])
        if os.path.exists(script_path):
            initial_path = script_path
        else:
            print(f"Provided path does not exist: {script_path}")
            # Decide if you want to exit or proceed without an initial path
            # For now, let's proceed without it.

    window = MainWindow(initial_path=initial_path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()