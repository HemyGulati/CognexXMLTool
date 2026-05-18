# Cognex XML Tool

Cognex XML Tool is a Windows GUI utility for processing Cognex In-Sight XML and CSV result exports during offline image review.

The tool combines image information from a Cognex XML file with actual inspection results from a Cognex CSV file. It then allows the user to filter images based on selected inspection results and generate output files that can be used for analysis, review, copying, or moving image sets.

![Cognex XML Tool main window](screenshots/main_window.png)

---

## Why this tool exists

Cognex XML Tool is intended for offline Cognex image-review workflows where the XML output contains image names and image paths, while the CSV output contains the actual inspection results.

This can be useful when working with existing image sets in In-Sight Explorer emulator or TestRun workflows, particularly on older setups where the exported CSV does not include the original image name or image path.

Newer In-Sight versions may support functions for retrieving image filenames during image playback, but the exact export behaviour depends on the job setup, firmware, and workflow being used.

This tool avoids relying on the CSV alone by combining:

- **XML**: image names, image paths, and image order
- **CSV**: actual runtime inspection results

Use this tool when your Cognex CSV does not include image names or paths, or when you need to combine XML and CSV outputs for offline image review.

---

## Key features

- Load a Cognex XML file and matching Cognex CSV file.
- Use the XML file to extract image names, image paths, and image order.
- Use the CSV file to extract actual inspection results.
- Automatically detect CSV result columns ending in `Pass`.
- Convert common result values into readable results:
  - `1`, `true`, `PASS`, `OK` -> `Pass`
  - `0`, `false`, `FAIL`, `NG` -> `Fail`
- Select which inspection results to include.
- Choose the result condition of interest for each selected inspection.
- Reorder selected inspection columns before export.
- Filter results using `ALL` or `ANY` match mode.
- Preview the number of matching images before generating outputs.
- Generate CSV and TXT output files.
- Copy or move matched images into a dedicated output folder.
- Automatically create result-specific output folders.
- Save and auto-load the last used configuration.
- Includes app icon and About popup.
- Supports portable EXE and Windows installer workflows.

---

## Example use case

A user has an offline image set and wants to find images where one inspection passes but another inspection fails.

Example selected conditions:

```text
Inspection A = Pass
Inspection B = Fail
```

The tool will:

1. Read image names and image paths from the XML file.
2. Read actual inspection results from the CSV file.
3. Match the XML and CSV data together.
4. Filter images where:
   - `Inspection A = Pass`
   - `Inspection B = Fail`
5. Create a dedicated output folder.
6. Export result CSV files and an image path TXT file.
7. Optionally copy or move the matching images into an `images` subfolder.

---

## Inputs

### XML file

The XML file is used to identify:

- image names
- image paths
- image order

### CSV file

The CSV file is used to identify actual runtime inspection results.

The tool automatically detects result columns ending in `Pass`.

Example generic CSV columns:

```text
Record
InspectionAPass
InspectionBPass
AlignmentPass
OverallPass
InspectionAPct
InspectionBPct
```

The detected inspections would appear in the tool as:

```text
InspectionA
InspectionB
Alignment
Overall
```

---

## Outputs

Each run creates a dedicated output folder containing:

```text
selected_test_results.csv
matched_results.csv
matched_image_paths.txt
```

If matched images are copied or moved, the tool also creates:

```text
images/
```

---

## Output folder behaviour

By default, the output base folder is set to the same folder as the selected CSV file.

When outputs are created, the tool automatically creates a result-specific folder based on the selected test names and result conditions.

Example selected conditions:

```text
Inspection A = Pass
Inspection B = Fail
```

Example output folder:

```text
Inspection_A_Pass_AND_Inspection_B_Fail
```

The output files are then saved inside that folder:

```text
Inspection_A_Pass_AND_Inspection_B_Fail/
├─ selected_test_results.csv
├─ matched_results.csv
├─ matched_image_paths.txt
└─ images/
```

This makes it easier to run multiple different result filters without overwriting previous outputs.

---

## Match modes

The tool supports two match modes.

### ALL selected conditions

The image must match every selected condition.

Example:

```text
Inspection A = Pass
Inspection B = Fail
```

This means:

```text
Inspection A must be Pass
AND
Inspection B must be Fail
```

Use this when you are looking for a specific combination of results.

### ANY selected condition

The image only needs to match one selected condition.

Example:

```text
Inspection A = Fail
Inspection B = Fail
Alignment = Fail
```

This means:

```text
Inspection A is Fail
OR
Inspection B is Fail
OR
Alignment is Fail
```

Use this when you want to collect images where any selected inspection has a result of interest.

---

## Configuration

The tool automatically saves and loads the last used configuration.

The config file is stored in the user AppData folder:

```text
%APPDATA%\CognexXMLTool\cognex_xml_tool_config.json
```

Example location:

```text
C:\Users\<UserName>\AppData\Roaming\CognexXMLTool\cognex_xml_tool_config.json
```

The config may include:

- last selected XML file
- last selected CSV file
- output folder
- selected inspections
- selected result filters
- match mode
- image copy/move folder

---

## Installation

### Option 1: Windows installer

Download the latest installer from the GitHub Releases page and run:

```text
CognexXMLTool_Setup_v1.1.0.exe
```

The installer adds the application to Windows and can create shortcuts.

### Option 2: Portable EXE

Download the portable EXE from the GitHub Releases page:

```text
Cognex XML Tool.exe
```

Then double-click to run it.

No installation is required.

---

## Running from source

Python 3.10 or later is recommended.

Clone the repository:

```bash
git clone https://github.com/HemyGulati/CognexXMLTool.git
cd CognexXMLTool
```

Run the tool:

```bash
python cognex_xml_tool.py
```

The tool uses Python standard-library GUI components, so no runtime package installation is required for normal source execution.

---

## Building the portable EXE

The project includes a build script for PyInstaller.

Run:

```bat
build_exe.bat
```

This creates the portable EXE in:

```text
dist/
```

Expected output:

```text
dist/Cognex XML Tool.exe
```

---

## Building the installer

The installer is built using Inno Setup.

Run:

```bat
build_installer.bat
```

Expected installer output:

```text
installer_output/CognexXMLTool_Setup_v1.1.0.exe
```

If Inno Setup is installed in a non-standard location, update the `ISCC.exe` path in `build_installer.bat`.

---

## Repository structure

```text
CognexXMLTool/
├─ cognex_xml_tool.py
├─ build_exe.bat
├─ build_installer.bat
├─ LICENSE
├─ LICENSE.txt
├─ README.md
├─ CHANGELOG.md
├─ requirements.txt
├─ requirements-dev.txt
├─ assets/
│  ├─ cognex_xml_tool.ico
│  └─ cognex_xml_tool.png
├─ installer/
│  └─ CognexXMLTool.iss
└─ screenshots/
   └─ main_window.png
```

---

## Notes

This tool is designed for offline result analysis and image sorting workflows.

It does not modify Cognex job files or image files unless the user explicitly chooses to copy or move matched images.

When using the move option, matched images are moved from their original location into the selected output image folder.

---

## Author

Hemy Gulati

GitHub:

```text
https://github.com/HemyGulati/CognexXMLTool
```

---

## License

This project is licensed under the MIT License.

See the `LICENSE` file for details.
