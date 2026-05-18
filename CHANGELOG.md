# Changelog

## v1.1.0

- Added MIT License file and installer license screen.
- Added MIT License text to the About popup.
- Improved installer build script path handling and output folder creation.

- Added XML + CSV workflow: XML supplies image names/paths/order, CSV supplies actual runtime results.
- Added automatic detection of CSV result columns such as columns ending in `Pass`.
- Added result-specific output folders next to the selected CSV file.
- Added default `images` subfolder for copied or moved matched images.
- Added copy and move image actions.
- Added installer support using Inno Setup.
- Moved user configuration to `%APPDATA%\CognexXMLTool\cognex_xml_tool_config.json`.
- Added app icon support for the GUI, EXE, installer, About popup, and Windows taskbar.

## v1.0.0

- Initial GitHub release.
- Added Cognex XML loading and automatic test detection.
- Added selected result CSV, matched result CSV, matched image path TXT output, and saved configuration support.
