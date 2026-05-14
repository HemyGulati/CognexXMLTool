# Cognex XML Tool

**Author:** Hemy Gulati  
**Version:** 1.0.0

Cognex XML Tool is a Windows-friendly GUI app for processing Cognex In-Sight TestRun XML summary files.

The tool loads one or more Cognex XML files, detects all available test names, lets the user choose which tests and result conditions matter, then exports CSV/TXT outputs and can copy the matched images into a selected folder.

---

## Key features

- Load one or more Cognex XML summary files.
- Scrollable, resizable GUI layout for laptop screens and smaller displays.
- Automatically detect image names and test names from the XML.
- Choose any detected tests to include in the output CSV.
- Choose the result of interest for each selected test, such as `Pass`, `Fail`, `(Any / output only)`, or `(Missing / blank)`.
- Reorder selected tests to control CSV column order.
- Export all selected test results to CSV.
- Export only matched rows to a separate CSV.
- Export a TXT file containing only the matched image paths.
- Copy matched images into a selected folder using the generated TXT path list.
- Auto-load the last saved config file on startup.
- Manually save or load config files from the **Settings** panel.

---

## Output files

By default, the tool creates:

| File | Purpose |
|---|---|
| `selected_test_results.csv` | All images with the selected test result columns. |
| `matched_results.csv` | Only images matching the selected result conditions. |
| `matched_image_paths.txt` | One image path per line for matched images. |

Example CSV:

```csv
image name,image path,Inspection A result,Inspection B result
sample_image_0001.bmp,C:\ExampleImages\sample_image_0001.bmp,Pass,Fail
```

Example TXT:

```text
C:\ExampleImages\sample_image_0001.bmp
C:\ExampleImages\sample_image_0042.bmp
```

---

## How to use the GUI

The main workflow window is scrollable. If your screen is smaller or Windows display scaling hides the lower sections, use the vertical scrollbar or mouse wheel to reach **Run and copy** and **Log**.

1. Open **Cognex XML Tool**.
2. Click **Add XML(s)** and select one or more Cognex XML files.
3. Click **Scan XML(s)**.
4. Select a detected test name from the left table.
5. Select the result of interest, such as `Pass`, `Fail`, or `(Any / output only)`.
6. Click **Add to output/filter**.
7. Repeat for any other tests you want to include.
8. Use **Move up** / **Move down** to control the CSV column order.
9. Choose the output folder.
10. Optional: choose an **Image folder override** if the XML image paths are missing or point to the wrong location.
11. Choose the **Match mode**.
12. Click **▶ Run: create outputs**.
13. Optional: choose a **Copy images to** folder.
14. Click **Copy matched images** to copy only the matched images.

---

## Match mode explained

Hover over **Match mode ⓘ** in the app to see this explanation.

### ALL selected result conditions

Use this when the image must meet every selected filter.

Example:

```text
Inspection A = Pass AND Inspection B = Fail
```

Only images where Inspection A is `Pass` and Inspection B is `Fail` will be included in `matched_results.csv` and `matched_image_paths.txt`.

### ANY selected result condition

Use this when the image can meet at least one selected filter.

Example:

```text
Inspection B = Fail OR Label Check = Fail OR Measurement = Fail
```

This is useful when you want one combined list of images that failed any one of several inspections.

### `(Any / output only)`

Use this when you want the test included as a CSV column, but you do not want it to filter the matched image list.

Example:

| Test | Result of interest |
|---|---|
| Inspection A | Pass |
| Inspection B | Fail |
| Overall | `(Any / output only)` |

This filters on Inspection A and Inspection B, but still includes Overall in the CSV for context.

---

## Saved config file

The app automatically looks for this file on startup:

```text
cognex_xml_tool_config.json
```

When running from Python, the config file is saved beside:

```text
cognex_xml_tool.py
```

When running as a packaged EXE, the config file is saved beside:

```text
Cognex XML Tool.exe
```

The config stores:

- output folder
- image folder override
- copy destination folder
- output filenames
- match mode
- selected tests and their result filters

The app saves the config when you click **Save config**, when you process outputs, and when you close the app. You can also manually load a different config file using **Load config** under **Settings**.

A template is included:

```text
cognex_xml_tool_config.example.json
```

---

## Image folder override

Use **Image folder override** when the XML contains image names but the stored paths are missing, old, or pointing to another PC.

For example, if the XML image is:

```text
sample_image_0001.bmp
```

and the image folder override is:

```text
C:\ExampleImages\Run_01
```

then the TXT output will contain:

```text
C:\ExampleImages\Run_01\sample_image_0001.bmp
```

---

## Copy behaviour

The **Copy matched images** button reads the generated `matched_image_paths.txt` file and copies those images into the selected folder.

If two source images have the same filename, the tool avoids overwriting by adding a suffix:

```text
image.bmp
image_copy1.bmp
image_copy2.bmp
```

Missing source images are counted and shown in the log instead of stopping the full copy operation.

---

## Run from Python

Requirements:

- Python 3.10 or newer recommended.
- Tkinter, which is normally included with Python on Windows.

Run:

```powershell
python cognex_xml_tool.py
```

---

## Build a standalone Windows EXE

1. Install Python 3.10 or newer.
2. Make sure Python is added to PATH.
3. Double-click:

```text
build_exe.bat
```

The standalone EXE will be created here:

```text
dist\Cognex XML Tool.exe
```

You can then copy that EXE to another Windows PC and run it without opening Python manually.

---

## Repository structure

```text
CognexXMLTool/
├─ cognex_xml_tool.py
├─ build_exe.bat
├─ cognex_xml_tool_config.example.json
├─ requirements.txt
├─ requirements-dev.txt
├─ README.md
├─ LICENSE_NOTE.md
├─ .gitignore
└─ output/
```

---

## Notes on Cognex XML structure

The parser is designed around Cognex TestRun-style XML summary files where:

- Each image is stored under a `ValidationFolder` element.
- The `ValidationFolder` name is the image filename.
- Test results are stored under child `Validate` elements.
- Result values may be stored under tags such as `ExpectedResult`, `ActualResult`, `Result`, `Status`, `Actual`, or `Outcome`.
- Image paths may be stored under tags such as `RefPath`, `Path`, `ImagePath`, or `FilePath`.

---

## Development notes

The GUI is built with Tkinter and packaged with PyInstaller.
