"""
Cognex XML Tool
===============================

Author: Hemy Gulati
Version: 1.0.0

A small Tkinter GUI for processing Cognex In-Sight TestRun XML summary files.

Main features
-------------
- Load one or more Cognex XML files.
- Automatically detect image names, image paths, and available test names.
- Let the user choose which test results to output and filter on.
- Export all selected results to CSV.
- Export matched results to CSV.
- Export matched image paths to TXT.
- Copy matched images into a selected folder for review or re-testing.

The app is intentionally written as a single Python file so it can be easily
reviewed, edited, and packaged into a standalone Windows EXE using PyInstaller.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import traceback
import webbrowser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText


# -----------------------------------------------------------------------------
# Application metadata
# -----------------------------------------------------------------------------

APP_NAME = "Cognex XML Tool"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Hemy Gulati"
APP_GITHUB = "https://github.com/HemyGulati/CognexXMLTool"


# -----------------------------------------------------------------------------
# Configuration constants
# -----------------------------------------------------------------------------

# File extensions treated as image names. Cognex TestRun XMLs commonly use BMP,
# but the tool also supports other common inspection image formats.
IMAGE_EXTENSIONS = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# Cognex XML files can vary slightly depending on the export method/version.
# These candidate tag names make the parser more tolerant.
RESULT_TAGS = ["ActualResult", "ExpectedResult", "Result", "Status", "Actual", "Outcome"]
PATH_TAGS = ["RefPath", "Path", "ImagePath", "FilePath"]

# Special result filter options displayed in the GUI.
ANY_TARGET = "(Any / output only)"
MISSING_TARGET = "(Missing / blank)"

# Default output file names.
DEFAULT_ALL_RESULTS_CSV = "selected_test_results.csv"
DEFAULT_MATCHED_RESULTS_CSV = "matched_results.csv"
DEFAULT_MATCHED_PATHS_TXT = "matched_image_paths.txt"
DEFAULT_COPY_FOLDER = "matched_images"

# The app automatically loads this file on startup if it exists.
# It is saved beside the Python script or beside the packaged EXE.
CONFIG_FILENAME = "cognex_xml_tool_config.json"

# Match mode labels shown in the GUI.
MATCH_MODE_ALL = "ALL selected result conditions"
MATCH_MODE_ANY = "ANY selected result condition"


# -----------------------------------------------------------------------------
# Small UI helpers
# -----------------------------------------------------------------------------

class ToolTip:
    """Simple hover tooltip for Tkinter/ttk widgets.

    Tkinter does not include a built-in tooltip widget. This helper keeps the
    behaviour lightweight and dependency-free so the app remains easy to package
    with PyInstaller.
    """

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 400, wraplength: int = 420) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wraplength = wraplength
        self._after_id: Optional[str] = None
        self._tip_window: Optional[tk.Toplevel] = None

        self.widget.bind("<Enter>", self._schedule)
        self.widget.bind("<Leave>", self._hide)
        self.widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event: Optional[tk.Event] = None) -> None:
        """Schedule the tooltip to appear after a short hover delay."""

        self._cancel_schedule()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel_schedule(self) -> None:
        """Cancel a tooltip that has been scheduled but not shown yet."""

        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        """Display the tooltip near the widget."""

        if self._tip_window is not None or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8

        self._tip_window = tk.Toplevel(self.widget)
        self._tip_window.wm_overrideredirect(True)
        self._tip_window.wm_geometry(f"+{x}+{y}")

        label = ttk.Label(
            self._tip_window,
            text=self.text,
            justify="left",
            relief="solid",
            borderwidth=1,
            padding=(8, 6),
            wraplength=self.wraplength,
        )
        label.pack()

    def _hide(self, _event: Optional[tk.Event] = None) -> None:
        """Hide the tooltip and cancel any pending display."""

        self._cancel_schedule()
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None


# -----------------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------------

@dataclass
class ImageRecord:
    """Results found for one image across one or more XML files."""

    image_name: str
    image_path: str = ""
    results: Dict[str, str] = field(default_factory=dict)
    source_files: Set[str] = field(default_factory=set)


@dataclass
class ParsedXml:
    """Parsed contents of one Cognex XML file."""

    xml_path: Path
    records: Dict[str, ImageRecord] = field(default_factory=dict)
    test_counts: Counter = field(default_factory=Counter)
    test_values: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    validation_folders_seen: int = 0
    image_records_seen: int = 0


@dataclass
class MergedData:
    """Combined result set after loading one or more XML files."""

    records: Dict[str, ImageRecord] = field(default_factory=dict)
    test_counts: Counter = field(default_factory=Counter)
    test_values: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    source_files: List[Path] = field(default_factory=list)
    duplicate_result_overwrites: int = 0


@dataclass
class Condition:
    """A selected test column and optional result filter."""

    test_name: str
    target_result: str = ANY_TARGET


@dataclass
class OutputSummary:
    """Summary of CSV/TXT files created by the processing step."""

    total_images: int = 0
    tests_selected: int = 0
    filter_conditions: int = 0
    matched_images: int = 0
    all_results_csv: Optional[Path] = None
    matched_results_csv: Optional[Path] = None
    matched_paths_txt: Optional[Path] = None


@dataclass
class CopySummary:
    """Summary of image copy operation."""

    total_paths: int = 0
    copied: int = 0
    missing: int = 0
    skipped_blank: int = 0
    errors: int = 0
    destination_folder: Optional[Path] = None


# -----------------------------------------------------------------------------
# General helper functions
# -----------------------------------------------------------------------------

def local_name(tag: str) -> str:
    """Return an XML tag name without its namespace prefix."""

    return tag.split("}", 1)[-1]


def direct_children(parent: ET.Element, tag_name: str) -> List[ET.Element]:
    """Return direct child elements matching a tag name, ignoring namespaces."""

    return [child for child in list(parent) if local_name(child.tag) == tag_name]


def child_text(parent: ET.Element, possible_child_tag_names: Iterable[str]) -> str:
    """Return direct-child text using the first matching candidate tag name."""

    possible = {name.lower() for name in possible_child_tag_names}
    for child in list(parent):
        if local_name(child.tag).lower() in possible:
            return (child.text or "").strip()
    return ""


def normalise_result(value: str) -> str:
    """Normalise common result values so CSV output is easier to filter."""

    value = (value or "").strip()
    lower = value.lower()
    common = {
        "pass": "Pass",
        "passed": "Pass",
        "ok": "Pass",
        "true": "Pass",
        "1": "Pass",
        "fail": "Fail",
        "failed": "Fail",
        "ng": "Fail",
        "false": "Fail",
        "0": "Fail",
    }
    return common.get(lower, value)


def is_image_name(value: str) -> bool:
    """Return True when a string looks like an image filename."""

    return Path(value or "").suffix.lower() in IMAGE_EXTENSIONS


def natural_key(value: str) -> List[object]:
    """Sort image names naturally, e.g. image_2.bmp before image_10.bmp."""

    parts = re.split(r"(\d+)", value)
    key: List[object] = []
    for part in parts:
        key.append(int(part) if part.isdigit() else part.lower())
    return key


def output_image_path(image_name: str, xml_image_path: str, image_root_override: Optional[str]) -> str:
    """Return the image path written to output files.

    If the user supplies an image folder override, that folder is used with the
    image filename. Otherwise the image path stored in the XML is used. If the
    XML does not contain a full image path, the image filename is used.
    """

    if image_root_override:
        return os.path.join(image_root_override, image_name)
    if xml_image_path:
        return xml_image_path
    return image_name


def unique_destination_path(destination_folder: Path, filename: str) -> Path:
    """Return a non-conflicting destination path for a copied image.

    If multiple source images share the same filename, the second and later
    copies receive a suffix such as "_copy1", "_copy2", etc.
    """

    destination = destination_folder / filename
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while True:
        candidate = destination_folder / f"{stem}_copy{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# -----------------------------------------------------------------------------
# Cognex XML parsing
# -----------------------------------------------------------------------------

def parse_cognex_xml(xml_path: Path) -> ParsedXml:
    """Parse one Cognex TestRun XML file.

    Expected structure, based on Cognex TestRun XML summary exports:
    - Image entries appear as ValidationFolder elements named after image files.
    - Individual test rows appear as Validate elements inside each image folder.
    - A Validate row named after the image often stores the image RefPath.
    - Inspection results are usually stored as ExpectedResult or ActualResult.

    The function is deliberately tolerant because Cognex XML exports can vary
    slightly between versions/jobs.
    """

    parsed = ParsedXml(xml_path=xml_path)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for folder in root.iter():
        if local_name(folder.tag) != "ValidationFolder":
            continue

        parsed.validation_folders_seen += 1
        image_name = (folder.attrib.get("Name") or "").strip()

        # Ignore folders that are not image-level entries.
        if not is_image_name(image_name):
            continue

        parsed.image_records_seen += 1
        record = ImageRecord(image_name=image_name, source_files={str(xml_path)})

        for validate in direct_children(folder, "Validate"):
            validate_name = (validate.attrib.get("Name") or "").strip()
            if not validate_name:
                continue

            result = normalise_result(child_text(validate, RESULT_TAGS))
            ref_path = child_text(validate, PATH_TAGS)

            # Cognex commonly stores the image path on a Validate row named after
            # the image file. Treat that as metadata, not as an inspection test.
            if validate_name == image_name or is_image_name(validate_name):
                if ref_path:
                    record.image_path = ref_path
                continue

            # Remaining Validate rows are treated as inspection tests.
            if result:
                record.results[validate_name] = result
                parsed.test_counts[validate_name] += 1
                parsed.test_values[validate_name].add(result)

        if record.results or record.image_path:
            parsed.records[image_name] = record

    return parsed


def merge_parsed_xmls(parsed_files: Sequence[ParsedXml]) -> MergedData:
    """Merge several XML result sets by image name.

    This supports workflows where different test results are exported from
    separate Cognex runs. If the same image/test appears in multiple XML files,
    the later file in the selected list overwrites the earlier value.
    """

    merged = MergedData(source_files=[p.xml_path for p in parsed_files])

    for parsed in parsed_files:
        merged.test_counts.update(parsed.test_counts)
        for test_name, values in parsed.test_values.items():
            merged.test_values[test_name].update(values)

        for image_name, incoming in parsed.records.items():
            existing = merged.records.get(image_name)
            if existing is None:
                merged.records[image_name] = ImageRecord(
                    image_name=image_name,
                    image_path=incoming.image_path,
                    results=dict(incoming.results),
                    source_files=set(incoming.source_files),
                )
                continue

            if not existing.image_path and incoming.image_path:
                existing.image_path = incoming.image_path
            existing.source_files.update(incoming.source_files)

            for test_name, result in incoming.results.items():
                if test_name in existing.results and existing.results[test_name] != result:
                    merged.duplicate_result_overwrites += 1
                existing.results[test_name] = result

    return merged


# -----------------------------------------------------------------------------
# Filtering and output file generation
# -----------------------------------------------------------------------------

def condition_is_filter(condition: Condition) -> bool:
    """Return True when a selected condition should filter matched rows."""

    return condition.target_result not in ("", ANY_TARGET)


def record_matches(record: ImageRecord, conditions: Sequence[Condition], match_mode: str) -> bool:
    """Return True if an image record satisfies the selected filters."""

    filters = [condition for condition in conditions if condition_is_filter(condition)]
    if not filters:
        return True

    checks: List[bool] = []
    for condition in filters:
        value = (record.results.get(condition.test_name, "") or "").strip()
        target = (condition.target_result or "").strip()
        if target == MISSING_TARGET:
            checks.append(value == "")
        else:
            checks.append(value.lower() == target.lower())

    if match_mode.lower().startswith("any"):
        return any(checks)
    return all(checks)


def selected_test_order(conditions: Sequence[Condition]) -> List[str]:
    """Return selected tests in output order while removing duplicates."""

    output_order: List[str] = []
    seen: Set[str] = set()
    for condition in conditions:
        if condition.test_name not in seen:
            output_order.append(condition.test_name)
            seen.add(condition.test_name)
    return output_order


def sorted_records(records: Dict[str, ImageRecord]) -> List[ImageRecord]:
    """Return image records sorted by image filename."""

    return [records[name] for name in sorted(records, key=natural_key)]


def write_results_csv(
    records: Sequence[ImageRecord],
    selected_tests: Sequence[str],
    csv_path: Path,
    image_root_override: Optional[str],
) -> None:
    """Write image result rows to CSV."""

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["image name", "image path"] + [f"{test} result" for test in selected_tests]

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            row = {
                "image name": record.image_name,
                "image path": output_image_path(record.image_name, record.image_path, image_root_override),
            }
            for test in selected_tests:
                row[f"{test} result"] = record.results.get(test, "")
            writer.writerow(row)


def write_paths_txt(records: Sequence[ImageRecord], txt_path: Path, image_root_override: Optional[str]) -> None:
    """Write one image path per line for matched images."""

    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with txt_path.open("w", encoding="utf-8") as txt_file:
        for record in records:
            txt_file.write(output_image_path(record.image_name, record.image_path, image_root_override) + "\n")


def process_outputs(
    merged: MergedData,
    conditions: Sequence[Condition],
    output_folder: Path,
    image_root_override: Optional[str],
    match_mode: str,
    all_csv_name: str = DEFAULT_ALL_RESULTS_CSV,
    matched_csv_name: str = DEFAULT_MATCHED_RESULTS_CSV,
    matched_txt_name: str = DEFAULT_MATCHED_PATHS_TXT,
) -> OutputSummary:
    """Create CSV/TXT outputs based on selected tests and result filters."""

    selected_tests = selected_test_order(conditions)
    if not selected_tests:
        raise ValueError("No tests selected. Add at least one test condition first.")

    all_records = sorted_records(merged.records)
    matched_records = [record for record in all_records if record_matches(record, conditions, match_mode)]

    all_csv = output_folder / all_csv_name
    matched_csv = output_folder / matched_csv_name
    matched_txt = output_folder / matched_txt_name

    write_results_csv(all_records, selected_tests, all_csv, image_root_override)
    write_results_csv(matched_records, selected_tests, matched_csv, image_root_override)
    write_paths_txt(matched_records, matched_txt, image_root_override)

    return OutputSummary(
        total_images=len(all_records),
        tests_selected=len(selected_tests),
        filter_conditions=sum(1 for condition in conditions if condition_is_filter(condition)),
        matched_images=len(matched_records),
        all_results_csv=all_csv,
        matched_results_csv=matched_csv,
        matched_paths_txt=matched_txt,
    )


def copy_images_from_txt(paths_txt: Path, destination_folder: Path) -> CopySummary:
    """Copy images listed in a TXT file into a destination folder.

    The TXT file is expected to contain one image path per line. Missing files are
    counted and reported rather than stopping the whole copy operation.
    """

    if not paths_txt.exists():
        raise FileNotFoundError(f"Could not find matched image path TXT file: {paths_txt}")

    destination_folder.mkdir(parents=True, exist_ok=True)
    summary = CopySummary(destination_folder=destination_folder)

    with paths_txt.open("r", encoding="utf-8") as txt_file:
        for raw_line in txt_file:
            source_text = raw_line.strip().strip('"')
            if not source_text:
                summary.skipped_blank += 1
                continue

            summary.total_paths += 1
            source_path = Path(source_text)

            if not source_path.exists():
                summary.missing += 1
                continue

            try:
                destination_path = unique_destination_path(destination_folder, source_path.name)
                shutil.copy2(source_path, destination_path)
                summary.copied += 1
            except Exception:
                summary.errors += 1

    return summary


# -----------------------------------------------------------------------------
# GUI application
# -----------------------------------------------------------------------------

class CognexXmlToolGui(tk.Tk):
    """Main Tkinter application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        # Keep the default size practical for laptop screens. The main
        # workflow area is scrollable, so the app remains usable even when
        # Windows display scaling or a smaller monitor reduces available height.
        self.geometry("1100x720")
        self.minsize(900, 600)

        # Current working data loaded from XML files.
        self.xml_files: List[Path] = []
        self.parsed_files: List[ParsedXml] = []
        self.merged: Optional[MergedData] = None
        self.conditions: List[Condition] = []

        # Last processed output summary. This is used by the copy button.
        self.last_summary: Optional[OutputSummary] = None

        # Tk variables used by input fields.
        self.output_folder = tk.StringVar(value=str(Path.cwd()))
        self.image_root = tk.StringVar(value="")
        self.copy_folder = tk.StringVar(value=str(Path.cwd() / DEFAULT_COPY_FOLDER))
        self.target_result = tk.StringVar(value="Fail")
        self.match_mode = tk.StringVar(value=MATCH_MODE_ALL)

        self.all_csv_name = tk.StringVar(value=DEFAULT_ALL_RESULTS_CSV)
        self.matched_csv_name = tk.StringVar(value=DEFAULT_MATCHED_RESULTS_CSV)
        self.matched_txt_name = tk.StringVar(value=DEFAULT_MATCHED_PATHS_TXT)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_styles()
        self._build_ui()
        self._load_config_if_available()

    # ------------------------------------------------------------------
    # UI layout
    # ------------------------------------------------------------------

    def _configure_styles(self) -> None:
        """Configure lightweight custom ttk styles used by the GUI.

        The Run button intentionally uses ttk styling rather than a classic
        tk.Button. This keeps the native Windows button shape/height and avoids
        the chunky square look, while still making the primary action a little
        more obvious. Some Windows themes ignore custom button backgrounds, so
        the green foreground acts as a reliable fallback.
        """

        style = ttk.Style(self)
        base_font = ("Segoe UI", 9, "bold")

        style.configure(
            "Run.TButton",
            font=base_font,
            foreground="#0b5d1e",
            background="#dff3e5",
            padding=(8, 3),
        )
        style.map(
            "Run.TButton",
            foreground=[("disabled", "#7a7a7a"), ("active", "#063d14")],
            background=[("disabled", "#eeeeee"), ("active", "#cbead4")],
        )

    def _build_ui(self) -> None:
        """Create all widgets and arrange them in a scrollable main window."""

        # The early versions placed every section directly in the root window.
        # That worked on large monitors, but on smaller laptop displays the lower
        # sections could be hidden off-screen. A canvas + internal frame gives the
        # full workflow a normal vertical scrollbar while keeping the rest of the
        # UI code simple.
        scroll_area = ttk.Frame(self)
        scroll_area.pack(fill="both", expand=True)
        scroll_area.rowconfigure(0, weight=1)
        scroll_area.columnconfigure(0, weight=1)

        self.main_canvas = tk.Canvas(scroll_area, borderwidth=0, highlightthickness=0)
        vertical_scrollbar = ttk.Scrollbar(scroll_area, orient="vertical", command=self.main_canvas.yview)
        self.main_canvas.configure(yscrollcommand=vertical_scrollbar.set)

        self.main_canvas.grid(row=0, column=0, sticky="nsew")
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")

        outer = ttk.Frame(self.main_canvas, padding=12)
        self._scroll_window_id = self.main_canvas.create_window((0, 0), window=outer, anchor="nw")

        # Keep the scroll region and inner-frame width in sync with the visible
        # canvas. This avoids horizontal clipping while still allowing vertical
        # scrolling when the content is taller than the window.
        outer.bind(
            "<Configure>",
            lambda _event: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all")),
        )
        self.main_canvas.bind(
            "<Configure>",
            lambda event: self.main_canvas.itemconfigure(self._scroll_window_id, width=event.width),
        )

        # Enable mouse-wheel scrolling when the cursor is anywhere over the app
        # background. Individual widgets such as Treeviews still keep their own
        # scrollbars for long lists.
        outer.bind("<Enter>", self._bind_mousewheel)
        outer.bind("<Leave>", self._unbind_mousewheel)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text=APP_NAME, font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")

        # Top-right info button: keeps version/author/GitHub details in the
        # conventional "about" location without crowding the workflow buttons.
        info_button = ttk.Button(header, text="ⓘ", width=3, command=self._show_about)
        info_button.grid(row=0, column=1, sticky="e")
        ToolTip(info_button, "About this app")

        subtitle = ttk.Label(
            outer,
            text=(
                "Load Cognex XML(s), detect all test names, choose tests/results, "
                "create CSV/TXT outputs, then copy matched images."
            ),
        )
        subtitle.pack(anchor="w", pady=(2, 8))

        top = ttk.Frame(outer)
        top.pack(fill="both", expand=False)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        self._build_xml_frame(top).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_settings_frame(top).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        middle = ttk.Frame(outer)
        middle.pack(fill="both", expand=True, pady=(8, 8))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)
        middle.rowconfigure(0, weight=1)

        self._build_detected_tests_frame(middle).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_conditions_frame(middle).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_action_frame(outer).pack(fill="x", pady=(0, 8))
        self._build_log_frame(outer).pack(fill="both", expand=True)

        self._log("Ready. Add one or more Cognex XML files, then click Scan XML(s).")

    def _bind_mousewheel(self, _event: Optional[tk.Event] = None) -> None:
        """Bind mouse-wheel events to the main vertical scrollbar."""

        self.main_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.main_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.main_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: Optional[tk.Event] = None) -> None:
        """Remove mouse-wheel bindings when the cursor leaves the app body."""

        self.main_canvas.unbind_all("<MouseWheel>")
        self.main_canvas.unbind_all("<Button-4>")
        self.main_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        """Scroll the main workflow area with Windows/macOS/Linux wheels."""

        if getattr(event, "num", None) == 4:
            self.main_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.main_canvas.yview_scroll(1, "units")
        else:
            delta = getattr(event, "delta", 0)
            if delta:
                # Windows usually reports +/-120. Some touchpads/macOS builds
                # report smaller values, so keep at least one scroll unit.
                if abs(delta) >= 120:
                    steps = int(-1 * (delta / 120))
                else:
                    steps = -1 if delta > 0 else 1
                self.main_canvas.yview_scroll(steps, "units")

    def _build_xml_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """Build the XML file selection panel."""

        frame = ttk.LabelFrame(parent, text="1. XML files", padding=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.xml_listbox = tk.Listbox(frame, height=5, exportselection=False)
        self.xml_listbox.grid(row=0, column=0, columnspan=4, sticky="nsew", pady=(0, 8))

        ttk.Button(frame, text="Add XML(s)", command=self._add_xml_files).grid(row=1, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(frame, text="Remove selected", command=self._remove_selected_xml).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(frame, text="Clear", command=self._clear_xml_files).grid(row=1, column=2, sticky="ew", padx=4)
        ttk.Button(frame, text="Scan XML(s)", command=self._scan_xml_files).grid(row=1, column=3, sticky="ew", padx=(4, 0))
        return frame

    def _build_settings_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """Build output file/folder settings panel."""

        frame = ttk.LabelFrame(parent, text="2. Settings", padding=10)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Output folder:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.output_folder).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="Browse", command=lambda: self._browse_folder(self.output_folder)).grid(row=0, column=2, padx=(8, 0), pady=3)

        ttk.Label(frame, text="Image folder override:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.image_root).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="Browse", command=lambda: self._browse_folder(self.image_root)).grid(row=1, column=2, padx=(8, 0), pady=3)
        ttk.Label(frame, text="Optional. Leave blank to use image paths stored in the XML.").grid(row=2, column=1, sticky="w", pady=(0, 5))

        ttk.Label(frame, text="Copy images to:").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.copy_folder).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="Browse", command=lambda: self._browse_folder(self.copy_folder)).grid(row=3, column=2, padx=(8, 0), pady=3)

        ttk.Label(frame, text="All results CSV:").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.all_csv_name).grid(row=4, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="Matched results CSV:").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.matched_csv_name).grid(row=5, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="Matched paths TXT:").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.matched_txt_name).grid(row=6, column=1, sticky="ew", pady=3)

        separator = ttk.Separator(frame, orient="horizontal")
        separator.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 8))

        ttk.Label(frame, text="Config:").grid(row=8, column=0, sticky="w", padx=(0, 8), pady=3)
        config_buttons = ttk.Frame(frame)
        config_buttons.grid(row=8, column=1, columnspan=2, sticky="w", pady=3)
        ttk.Button(config_buttons, text="Save config", command=self._save_config_with_message).pack(side="left")
        ttk.Button(config_buttons, text="Load config", command=self._load_config_from_file).pack(side="left", padx=(8, 0))
        ttk.Button(config_buttons, text="Open app folder", command=lambda: self._open_folder(self._app_directory())).pack(side="left", padx=(8, 0))
        ttk.Label(
            frame,
            text="The last saved config auto-loads on startup if found beside the script/EXE.",
        ).grid(row=9, column=1, columnspan=2, sticky="w", pady=(0, 2))
        return frame

    def _build_detected_tests_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """Build detected Cognex test list panel."""

        frame = ttk.LabelFrame(parent, text="3. Detected tests", padding=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ("count", "values")
        self.tests_tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="browse")
        self.tests_tree.heading("#0", text="Test name")
        self.tests_tree.heading("count", text="Rows")
        self.tests_tree.heading("values", text="Detected results")
        self.tests_tree.column("#0", width=250, stretch=True)
        self.tests_tree.column("count", width=70, anchor="e", stretch=False)
        self.tests_tree.column("values", width=190, stretch=True)
        self.tests_tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
        self.tests_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_result_choices())
        self.tests_tree.bind("<Double-1>", lambda _event: self._add_condition())

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tests_tree.yview)
        self.tests_tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=3, sticky="ns")

        ttk.Label(frame, text="Result of interest:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.result_combo = ttk.Combobox(frame, textvariable=self.target_result, values=["Pass", "Fail", ANY_TARGET, MISSING_TARGET], width=24)
        self.result_combo.grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Button(frame, text="Add to output/filter", command=self._add_condition).grid(row=1, column=2, sticky="e", pady=(8, 0))

        ttk.Label(
            frame,
            text="Use '(Any / output only)' to include a test as a CSV column without filtering on it.",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(5, 0))
        return frame

    def _build_conditions_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """Build selected output/filter conditions panel."""

        frame = ttk.LabelFrame(parent, text="4. Selected tests / conditions", padding=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ("order", "test", "target")
        self.conditions_tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        self.conditions_tree.heading("order", text="Order")
        self.conditions_tree.heading("test", text="Test name")
        self.conditions_tree.heading("target", text="Result of interest")
        self.conditions_tree.column("order", width=55, anchor="center", stretch=False)
        self.conditions_tree.column("test", width=250, stretch=True)
        self.conditions_tree.column("target", width=170, stretch=True)
        self.conditions_tree.grid(row=0, column=0, columnspan=5, sticky="nsew")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.conditions_tree.yview)
        self.conditions_tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=5, sticky="ns")

        # Keep these small action buttons in their own frame so each button has
        # the same visual width. This avoids the first button stretching with the
        # resizable table column above it.
        button_bar = ttk.Frame(frame)
        button_bar.grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Button(button_bar, text="Move up", width=12, command=lambda: self._move_condition(-1)).pack(side="left")
        ttk.Button(button_bar, text="Move down", width=12, command=lambda: self._move_condition(1)).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Remove", width=12, command=self._remove_condition).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Clear", width=12, command=self._clear_conditions).pack(side="left", padx=(6, 0))

        ttk.Label(
            frame,
            text="Order controls CSV column order. TXT output only contains images matching the selected result conditions.",
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        return frame

    def _build_action_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """Build the prominent run/copy action area."""

        frame = ttk.LabelFrame(parent, text="Run and copy", padding=10)
        frame.columnconfigure(1, weight=0)
        frame.columnconfigure(2, weight=1)

        match_label = ttk.Label(frame, text="Match mode ⓘ:", cursor="question_arrow")
        match_label.grid(row=0, column=0, sticky="w")
        ToolTip(match_label, self._match_mode_help_text())

        ttk.Combobox(
            frame,
            textvariable=self.match_mode,
            values=[MATCH_MODE_ALL, MATCH_MODE_ANY],
            state="readonly",
            width=34,
        ).grid(row=0, column=1, sticky="w", padx=(6, 14))

        # Primary action button. It uses ttk.Button so it matches the native
        # Windows button aesthetic, with only a subtle green accent applied via
        # the Run.TButton style above.
        run_button = ttk.Button(
            frame,
            text="▶ Run: create outputs",
            command=self._process,
            style="Run.TButton",
            width=22,
        )
        run_button.grid(row=0, column=2, sticky="w", padx=(0, 8))

        ttk.Button(frame, text="Copy matched images", command=self._copy_matched_images).grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Button(frame, text="Open output folder", command=lambda: self._open_folder(Path(self.output_folder.get()))).grid(row=0, column=4, sticky="w", padx=(0, 8))
        ttk.Button(frame, text="Open copy folder", command=lambda: self._open_folder(Path(self.copy_folder.get()))).grid(row=0, column=5, sticky="w")
        return frame

    def _build_log_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """Build application log panel."""

        frame = ttk.LabelFrame(parent, text="Log", padding=8)
        self.log_box = ScrolledText(frame, height=8, wrap="word")
        self.log_box.pack(fill="both", expand=True)
        return frame

    # ------------------------------------------------------------------
    # XML and scan actions
    # ------------------------------------------------------------------

    def _add_xml_files(self) -> None:
        """Prompt the user to add one or more XML files."""

        file_paths = filedialog.askopenfilenames(
            title="Select Cognex XML file(s)",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
        )
        if not file_paths:
            return

        existing = {str(path) for path in self.xml_files}
        for file_path in file_paths:
            path = Path(file_path)
            if str(path) not in existing:
                self.xml_files.append(path)
                existing.add(str(path))

        self._refresh_xml_listbox()

        # When the first XML is added, default outputs beside the XML file.
        if self.xml_files:
            if self.output_folder.get() == str(Path.cwd()):
                self.output_folder.set(str(self.xml_files[0].parent))
            if self.copy_folder.get() == str(Path.cwd() / DEFAULT_COPY_FOLDER):
                self.copy_folder.set(str(self.xml_files[0].parent / DEFAULT_COPY_FOLDER))

        self._autosave_config_quietly()
        self._log(f"Added {len(file_paths)} XML file(s). Click Scan XML(s) to detect tests.")

    def _remove_selected_xml(self) -> None:
        """Remove selected XML files from the list."""

        selection = list(self.xml_listbox.curselection())
        for index in reversed(selection):
            del self.xml_files[index]
        self._refresh_xml_listbox()
        self._clear_scan_results()

    def _clear_xml_files(self) -> None:
        """Clear all selected XML files and scan results."""

        self.xml_files.clear()
        self._refresh_xml_listbox()
        self._clear_scan_results()

    def _refresh_xml_listbox(self) -> None:
        """Refresh XML file list display."""

        self.xml_listbox.delete(0, "end")
        for path in self.xml_files:
            self.xml_listbox.insert("end", str(path))

    def _clear_scan_results(self, clear_conditions: bool = True) -> None:
        """Clear loaded/merged XML data and UI result lists.

        Conditions are only cleared when the user explicitly clears/removes XMLs.
        During a normal scan, keeping conditions allows an auto-loaded config to
        remain ready for processing after new XML files are selected.
        """

        self.parsed_files.clear()
        self.merged = None
        self.last_summary = None
        for item in self.tests_tree.get_children():
            self.tests_tree.delete(item)
        if clear_conditions:
            self.conditions.clear()
            self._refresh_conditions_tree()

    def _scan_xml_files(self) -> None:
        """Parse all selected XML files and populate detected tests."""

        try:
            if not self.xml_files:
                messagebox.showwarning("No XML files", "Please add at least one Cognex XML file first.")
                return

            self._clear_scan_results(clear_conditions=False)
            self._log("Scanning XML file(s)...")

            parsed_files: List[ParsedXml] = []
            for xml_path in self.xml_files:
                if not xml_path.exists():
                    raise FileNotFoundError(f"Could not find XML file: {xml_path}")

                parsed = parse_cognex_xml(xml_path)
                parsed_files.append(parsed)
                tests_found = len(parsed.test_counts)
                self._log(f"Scanned: {xml_path.name} | images: {len(parsed.records)} | tests: {tests_found}")

            self.parsed_files = parsed_files
            self.merged = merge_parsed_xmls(parsed_files)
            self._populate_tests_tree()

            self._log(f"Total merged images: {len(self.merged.records)}")
            self._log(f"Detected test names: {len(self.merged.test_counts)}")
            missing_selected = [
                condition.test_name
                for condition in self.conditions
                if condition.test_name not in self.merged.test_counts
            ]
            if missing_selected:
                self._log(
                    "Warning: selected condition test(s) not found in scanned XML(s): "
                    + ", ".join(dict.fromkeys(missing_selected))
                )
            if self.merged.duplicate_result_overwrites:
                self._log(
                    f"Note: {self.merged.duplicate_result_overwrites} duplicate image/test results "
                    "were overwritten by later XML file(s)."
                )
            self._log("Select a test, choose the result of interest, then add it to the selected conditions.")
        except Exception as exc:
            self._handle_error(exc)

    def _populate_tests_tree(self) -> None:
        """Show detected test names and result values in the test table."""

        for item in self.tests_tree.get_children():
            self.tests_tree.delete(item)
        if self.merged is None:
            return

        test_names = sorted(self.merged.test_counts, key=lambda name: (-self.merged.test_counts[name], name.lower()))
        for test_name in test_names:
            values = sorted(self.merged.test_values.get(test_name, []), key=str.lower)
            self.tests_tree.insert(
                "",
                "end",
                iid=test_name,
                text=test_name,
                values=(self.merged.test_counts[test_name], ", ".join(values)),
            )

        if test_names:
            self.tests_tree.selection_set(test_names[0])
            self.tests_tree.focus(test_names[0])
            self._update_result_choices()

    # ------------------------------------------------------------------
    # Condition selection actions
    # ------------------------------------------------------------------

    def _update_result_choices(self) -> None:
        """Update result dropdown based on the selected test."""

        selected_test = self._selected_test_name()
        values: List[str] = []
        if self.merged and selected_test:
            values = sorted(self.merged.test_values.get(selected_test, []), key=str.lower)

        combo_values = values + [ANY_TARGET, MISSING_TARGET]
        self.result_combo.configure(values=combo_values)

        # Default to Fail where possible because inspection review workflows often
        # focus on failures. The user can still select any detected value.
        if values:
            if "Fail" in values:
                self.target_result.set("Fail")
            elif "Pass" in values:
                self.target_result.set("Pass")
            else:
                self.target_result.set(values[0])
        else:
            self.target_result.set(ANY_TARGET)

    def _selected_test_name(self) -> Optional[str]:
        """Return the currently selected detected test name."""

        selected = self.tests_tree.selection()
        if not selected:
            return None
        return str(selected[0])

    def _add_condition(self) -> None:
        """Add selected detected test to the output/filter list."""

        test_name = self._selected_test_name()
        if not test_name:
            messagebox.showwarning("No test selected", "Please select a detected test first.")
            return

        target = self.target_result.get().strip() or ANY_TARGET
        self.conditions.append(Condition(test_name=test_name, target_result=target))
        self._refresh_conditions_tree()
        self._autosave_config_quietly()

    def _refresh_conditions_tree(self) -> None:
        """Refresh selected condition table."""

        for item in self.conditions_tree.get_children():
            self.conditions_tree.delete(item)
        for index, condition in enumerate(self.conditions, start=1):
            self.conditions_tree.insert(
                "",
                "end",
                iid=str(index - 1),
                values=(index, condition.test_name, condition.target_result),
            )

    def _selected_condition_index(self) -> Optional[int]:
        """Return the index of the selected condition row."""

        selected = self.conditions_tree.selection()
        if not selected:
            return None
        return int(selected[0])

    def _move_condition(self, direction: int) -> None:
        """Move selected condition up or down in output order."""

        index = self._selected_condition_index()
        if index is None:
            return

        new_index = index + direction
        if new_index < 0 or new_index >= len(self.conditions):
            return

        self.conditions[index], self.conditions[new_index] = self.conditions[new_index], self.conditions[index]
        self._refresh_conditions_tree()
        self.conditions_tree.selection_set(str(new_index))
        self.conditions_tree.focus(str(new_index))
        self._autosave_config_quietly()

    def _remove_condition(self) -> None:
        """Remove selected condition from output/filter list."""

        index = self._selected_condition_index()
        if index is None:
            return
        del self.conditions[index]
        self._refresh_conditions_tree()
        self._autosave_config_quietly()

    def _clear_conditions(self) -> None:
        """Clear all selected conditions."""

        self.conditions.clear()
        self._refresh_conditions_tree()
        self._autosave_config_quietly()

    # ------------------------------------------------------------------
    # Processing and copy actions
    # ------------------------------------------------------------------

    def _browse_folder(self, variable: tk.StringVar) -> None:
        """Prompt the user to select a folder and assign it to a Tk variable."""

        folder = filedialog.askdirectory(title="Select folder")
        if folder:
            variable.set(folder)

    def _get_output_folder(self) -> Path:
        """Return output folder, creating it if required."""

        folder = Path(self.output_folder.get().strip() or Path.cwd())
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _process(self) -> None:
        """Create CSV/TXT outputs from current XML data and selected conditions."""

        try:
            if self.merged is None:
                messagebox.showwarning("Scan first", "Please scan the XML file(s) first.")
                return
            if not self.conditions:
                messagebox.showwarning("No selected tests", "Please add at least one test to the selected conditions list.")
                return

            output_folder = self._get_output_folder()
            image_root = self.image_root.get().strip() or None
            all_csv_name = self.all_csv_name.get().strip() or DEFAULT_ALL_RESULTS_CSV
            matched_csv_name = self.matched_csv_name.get().strip() or DEFAULT_MATCHED_RESULTS_CSV
            matched_txt_name = self.matched_txt_name.get().strip() or DEFAULT_MATCHED_PATHS_TXT

            self._log("Processing outputs...")
            summary = process_outputs(
                merged=self.merged,
                conditions=self.conditions,
                output_folder=output_folder,
                image_root_override=image_root,
                match_mode=self.match_mode.get(),
                all_csv_name=all_csv_name,
                matched_csv_name=matched_csv_name,
                matched_txt_name=matched_txt_name,
            )
            self.last_summary = summary
            self._autosave_config_quietly()
            self._show_summary(summary)
        except Exception as exc:
            self._handle_error(exc)

    def _copy_matched_images(self) -> None:
        """Copy matched images from the generated TXT list to the selected folder."""

        try:
            paths_txt = self._resolve_current_matched_txt_path()
            destination = Path(self.copy_folder.get().strip() or (Path(self.output_folder.get()) / DEFAULT_COPY_FOLDER))

            if not destination:
                messagebox.showwarning("No destination", "Please choose a copy destination folder first.")
                return

            self._log(f"Copying matched images from: {paths_txt}")
            self._log(f"Copy destination: {destination}")
            summary = copy_images_from_txt(paths_txt, destination)
            self._show_copy_summary(summary)
        except Exception as exc:
            self._handle_error(exc)

    def _resolve_current_matched_txt_path(self) -> Path:
        """Return the matched TXT path from the last run or current settings."""

        if self.last_summary and self.last_summary.matched_paths_txt:
            return self.last_summary.matched_paths_txt
        return Path(self.output_folder.get().strip() or Path.cwd()) / (self.matched_txt_name.get().strip() or DEFAULT_MATCHED_PATHS_TXT)

    def _show_summary(self, summary: OutputSummary) -> None:
        """Log processing summary and show a popup."""

        self._log("Done.")
        self._log(f"Images processed: {summary.total_images}")
        self._log(f"Selected tests / CSV columns: {summary.tests_selected}")
        self._log(f"Active filter conditions: {summary.filter_conditions}")
        self._log(f"Matched images: {summary.matched_images}")
        self._log(f"All results CSV: {summary.all_results_csv}")
        self._log(f"Matched results CSV: {summary.matched_results_csv}")
        self._log(f"Matched image path TXT: {summary.matched_paths_txt}")
        self._log("-" * 80)

        messagebox.showinfo(
            "Processing complete",
            "Done.\n\n"
            f"Matched images: {summary.matched_images}\n\n"
            f"TXT path list:\n{summary.matched_paths_txt}\n\n"
            "Use 'Copy matched images' to copy those images into the selected folder.",
        )

    def _show_copy_summary(self, summary: CopySummary) -> None:
        """Log copy summary and show a popup."""

        self._log("Copy complete.")
        self._log(f"Paths in TXT: {summary.total_paths}")
        self._log(f"Images copied: {summary.copied}")
        self._log(f"Missing source images: {summary.missing}")
        self._log(f"Copy errors: {summary.errors}")
        self._log(f"Destination folder: {summary.destination_folder}")
        self._log("-" * 80)

        messagebox.showinfo(
            "Copy complete",
            "Copy complete.\n\n"
            f"Images copied: {summary.copied}\n"
            f"Missing source images: {summary.missing}\n"
            f"Copy errors: {summary.errors}\n\n"
            f"Destination folder:\n{summary.destination_folder}",
        )

    # ------------------------------------------------------------------
    # Configuration actions
    # ------------------------------------------------------------------

    def _app_directory(self) -> Path:
        """Return the folder that should contain the app config file.

        When running from a PyInstaller EXE, sys.executable points to the EXE.
        When running from Python, __file__ points to this source file.
        """

        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def _config_path(self) -> Path:
        """Return the path to the auto-loaded JSON config file."""

        return self._app_directory() / CONFIG_FILENAME

    def _current_config(self) -> Dict[str, object]:
        """Build a JSON-serialisable dictionary of the current GUI settings."""

        return {
            "app_name": APP_NAME,
            "version": APP_VERSION,
            "output_folder": self.output_folder.get(),
            "image_root": self.image_root.get(),
            "copy_folder": self.copy_folder.get(),
            "match_mode": self.match_mode.get(),
            "all_csv_name": self.all_csv_name.get(),
            "matched_csv_name": self.matched_csv_name.get(),
            "matched_txt_name": self.matched_txt_name.get(),
            "conditions": [
                {"test_name": condition.test_name, "target_result": condition.target_result}
                for condition in self.conditions
            ],
        }

    def _apply_config(self, config: Dict[str, object]) -> None:
        """Apply settings loaded from the JSON config file.

        The config is intentionally tolerant: missing or old fields are ignored
        so future versions can still read older config files.
        """

        def text_value(key: str, default: str = "") -> str:
            value = config.get(key, default)
            return value if isinstance(value, str) else default

        self.output_folder.set(text_value("output_folder", self.output_folder.get()))
        self.image_root.set(text_value("image_root", self.image_root.get()))
        self.copy_folder.set(text_value("copy_folder", self.copy_folder.get()))
        self.all_csv_name.set(text_value("all_csv_name", DEFAULT_ALL_RESULTS_CSV))
        self.matched_csv_name.set(text_value("matched_csv_name", DEFAULT_MATCHED_RESULTS_CSV))
        self.matched_txt_name.set(text_value("matched_txt_name", DEFAULT_MATCHED_PATHS_TXT))

        mode = text_value("match_mode", MATCH_MODE_ALL)
        if mode not in {MATCH_MODE_ALL, MATCH_MODE_ANY}:
            mode = MATCH_MODE_ALL
        self.match_mode.set(mode)

        loaded_conditions: List[Condition] = []
        raw_conditions = config.get("conditions", [])
        if isinstance(raw_conditions, list):
            for item in raw_conditions:
                if not isinstance(item, dict):
                    continue
                test_name = item.get("test_name", "")
                target_result = item.get("target_result", ANY_TARGET)
                if isinstance(test_name, str) and test_name.strip():
                    loaded_conditions.append(
                        Condition(
                            test_name=test_name.strip(),
                            target_result=target_result if isinstance(target_result, str) else ANY_TARGET,
                        )
                    )

        self.conditions = loaded_conditions
        self._refresh_conditions_tree()

    def _load_config_if_available(self) -> None:
        """Auto-load the last saved config if the config file exists."""

        config_path = self._config_path()
        if not config_path.exists():
            self._log(f"No saved config found. A config will be created at: {config_path}")
            return

        self._load_config_path(config_path, show_popup=False)

    def _load_config_path(self, config_path: Path, show_popup: bool = True) -> None:
        """Load a JSON config file and apply it to the GUI."""

        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                config = json.load(config_file)
            if not isinstance(config, dict):
                raise ValueError("Config file is not a JSON object.")
            self._apply_config(config)
            self._log(f"Loaded config: {config_path}")
            if self.conditions:
                self._log(f"Loaded {len(self.conditions)} saved test condition(s). Add XML(s), scan, then process.")
            if show_popup:
                messagebox.showinfo("Config loaded", f"Loaded config:\n{config_path}")
        except Exception as exc:
            self._log(f"Could not load config file: {config_path}")
            self._log(f"Config load error: {exc}")
            if show_popup:
                messagebox.showerror("Config load error", f"Could not load config:\n{config_path}\n\n{exc}")

    def _load_config_from_file(self) -> None:
        """Prompt the user to manually load a config JSON file."""

        file_path = filedialog.askopenfilename(
            title="Load Cognex XML Tool config",
            filetypes=[("JSON config", "*.json"), ("All files", "*.*")],
            initialdir=str(self._app_directory()),
        )
        if file_path:
            self._load_config_path(Path(file_path), show_popup=True)

    def _save_config(self) -> Path:
        """Save the current GUI config to JSON and return the config path."""

        config_path = self._config_path()
        with config_path.open("w", encoding="utf-8") as config_file:
            json.dump(self._current_config(), config_file, indent=2)
        return config_path

    def _autosave_config_quietly(self) -> None:
        """Best-effort save used after small GUI changes."""

        try:
            self._save_config()
        except Exception:
            # Avoid interrupting normal use for non-critical autosave failures.
            pass

    def _save_config_with_message(self) -> None:
        """Save config and show a user-facing confirmation."""

        try:
            config_path = self._save_config()
            self._log(f"Saved config: {config_path}")
            messagebox.showinfo("Config saved", f"Saved config:\n{config_path}")
        except Exception as exc:
            self._handle_error(exc)

    def _on_close(self) -> None:
        """Save the current config before closing the GUI."""

        try:
            config_path = self._save_config()
            self._log(f"Saved config on close: {config_path}")
        except Exception as exc:
            # Do not block closing if the config cannot be saved.
            self._log(f"Could not save config on close: {exc}")
        self.destroy()

    def _match_mode_help_text(self) -> str:
        """Return short help text used by the match-mode hover tooltip."""

        return (
            "ALL selected result conditions: an image must match every active result filter.\n"
            "Example: Inspection A = Pass AND Inspection B = Fail.\n\n"
            "ANY selected result condition: an image only needs to match at least one active result filter.\n"
            "Example: Inspection B = Fail OR Print = Fail OR Measurement = Fail.\n\n"
            "Use '(Any / output only)' when you want a test included as a CSV column but not used as a filter."
        )

    def _show_match_mode_help(self) -> None:
        """Explain the ALL/ANY matching behaviour to the user."""

        messagebox.showinfo("Match mode help", self._match_mode_help_text())

    def _show_about(self) -> None:
        """Open the app information window from the top-right info button."""

        window = tk.Toplevel(self)
        window.title(f"About {APP_NAME}")
        window.resizable(False, False)
        window.transient(self)
        window.grab_set()

        container = ttk.Frame(window, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text=APP_NAME, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(container, text="Version:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Label(container, text=APP_VERSION).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(container, text="Author:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Label(container, text=APP_AUTHOR).grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(container, text="GitHub:").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=2)
        github_label = ttk.Label(container, text=APP_GITHUB, foreground="blue", cursor="hand2")
        github_label.grid(row=3, column=1, sticky="w", pady=2)
        github_label.bind("<Button-1>", lambda _event: webbrowser.open(APP_GITHUB))

        button_bar = ttk.Frame(container)
        button_bar.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(button_bar, text="Open GitHub", command=lambda: webbrowser.open(APP_GITHUB)).pack(side="left")
        ttk.Button(button_bar, text="Close", command=window.destroy).pack(side="left", padx=(8, 0))

        window.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - window.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - window.winfo_height()) // 2)
        window.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # Utility actions
    # ------------------------------------------------------------------

    def _open_folder(self, folder: Path) -> None:
        """Open a folder using the operating system's default file browser."""

        try:
            folder.mkdir(parents=True, exist_ok=True)
            system = platform.system().lower()
            if system == "windows":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif system == "darwin":
                subprocess.run(["open", str(folder)], check=False)
            else:
                subprocess.run(["xdg-open", str(folder)], check=False)
        except Exception as exc:
            self._log(f"Could not open folder: {exc}")

    def _log(self, message: str) -> None:
        """Write a line to the GUI log box."""

        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.update_idletasks()

    def _handle_error(self, exc: Exception) -> None:
        """Log and display an error in a user-friendly way."""

        if isinstance(exc, ET.ParseError):
            msg = f"Could not read the XML file. XML parse error:\n{exc}"
        else:
            msg = str(exc)

        self._log("ERROR: " + msg)
        self._log(traceback.format_exc())
        messagebox.showerror("Error", msg)


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def main() -> int:
    """Start the GUI application."""

    app = CognexXmlToolGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
