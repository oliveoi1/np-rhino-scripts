#! python 3
# -*- coding: utf-8 -*-
"""
NP Menu: a dockable Rhino panel that lists every NP tool by category.

Rhino alias NPP runs this file directly. It can also be opened from the
classic NP list ("NP Menu (panel)"). Both front ends read the same tool
table, SCRIPT_CHOICES in np_launcher.py, so adding a tool there puts it in
both menus. The classic NP launcher is untouched by this file.

The menu is a real Rhino panel (like Layers or Properties): it docks as a tab
in the sidebar, floats, collapses and is listed in the sidebar's panel menu.
Rhino only accepts a panel class that carries a .NET Guid attribute, which a
Python class cannot, so panel_type() emits a tiny .NET subclass of Eto Panel
at runtime and the RhinoCode plug-in that ships with Rhino 8 hosts it. The
content of each panel instance is built here in Python.

Registration lasts one Rhino session, so NPP also adds np_menu_startup.py to
Rhino's startup commands (Options > General); that script re-registers the
panel and reopens it when it was open last time. Favourites, recents and
open drawers live in _user_data/np_menu_state.json. NPP runs the same daily
update check as NP.
"""

import json
import os
import re
import sys
import time
import traceback

import Rhino
import Rhino.UI
import System
import Eto.Drawing as drawing
import Eto.Forms as forms
import scriptcontext as sc

THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
INSTALL_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
SHARED_DIR = os.path.join(INSTALL_ROOT, "shared")
for _path in (THIS_DIR, SHARED_DIR, INSTALL_ROOT):
    if _path and _path not in sys.path:
        sys.path.insert(0, _path)

import importlib
import importlib.util

import np_launcher

try:
    np_launcher = importlib.reload(np_launcher)
except Exception:
    pass

try:
    import np_deploy
except ImportError:
    np_deploy = None


STATE_FILENAME = "np_menu_state.json"
MENU_FILENAME = "np_menu.py"
STARTUP_FILENAME = "np_menu_startup.py"
MENU_ALIAS = "NPP"
MAX_RECENT = 6
OTHER_TITLE = "Other"
CHOICE_FILENAME = "np_menu_choice.json"

PANEL_TITLE = "NP Tools"
PANEL_GUID = "6e2f4a9c-3b7d-4c15-9a8e-5d1f0b2c7e43"   # fixed: Rhino remembers the panel by it
PANEL_ASSEMBLY = "NPMenuPanel_" + PANEL_GUID.replace("-", "")
PANEL_TYPE_NAME = PANEL_ASSEMBLY + ".NPMenuPanel"
HOST_PLUGIN_ID = "c9cba87a-23ce-4f15-a918-97645c05cde7"  # RhinoCodePlugin, ships with Rhino 8
STICKY_VIEWS = "np_menu_views"            # live NPMenuView instances, one per panel
STICKY_SHOW_HANDLER = "np_menu_show_handler"
STICKY_CLOSING_HANDLER = "np_menu_closing_handler"
STICKY_CLOSING = "np_menu_rhino_closing"
HEADING_BACKGROUND = drawing.Color.FromArgb(78, 78, 82)   # category title bars
HEADING_HEIGHT = 24

# Tools whose first step is a list: the window shows that list as a drawer under
# the tool. Each script exposes menu_items() and reads the chosen entry from
# _user_data/np_menu_choice.json, skipping its own list dialog.
SUBMENU_TOOLS = [
    "01 extrude_curves.py",
    "15 insert_block.py",
    "16 snapshot_2d_export.py",
    "19 display_modes.py",
    "18 annotation_styles.py",
    "20 assembly_steps.py",
    "21 assembly_symbols.py",
]

# Category -> (menu label, script filename), in display order. The window uses
# these labels; the classic NP list keeps the labels in np_launcher.SCRIPT_CHOICES.
# A script in SCRIPT_CHOICES that is missing here still appears, under "Other".
# Order and names come from the "NP Rhino Tools - Menu Order" sheet.
CATEGORIES = [
    ("Joinery", [
        ("Extrude Curves", "01 extrude_curves.py"),
        ("Extrude Ply Bands", "01a_extrude_ply_bands.py"),
        ("Dado Recess", "02 dado_recess.py"),
        ("Dado Tongue", "02 dado_tongue.py"),
        ("Surface Recess", "02b Surface recess.py"),
        ("Engrave", "02c engrave.py"),
    ]),
    ("Auto Inserts", [
        ("Hole Insert Points Auto", "03a hole_insertpoints_auto.py"),
        ("Grub Screws + Holes", "03b grub_screws_and_holes.py"),
        ("Dimple Hole", "03c dimple_hole.py"),
        ("Custom Holes", "03d custom_holes.py"),
        ("Cam Inserts", "04a cam_inserts.py"),
        ("Cam Holes + Cams", "04b cam_holes_+_cams.py"),
        ("Flipper Insert Auto", "05a flipper_insert_auto.py"),
        ("Flipper Holes + Flippers", "05b flipper_holes_+flippers.py"),
        ("Shelf Holes", "05c shelf_holes.py"),
        ("Logo Cut", "10 logo_cut.py"),
    ]),
    ("Hardware", [
        ("Insert Block", "15 insert_block.py"),
        ("Castor Insert", "06a castor_insert.py"),
        ("Castor Small Insert + Holes", "06b castor_(SM)_insert_+_holes.py"),
        ("Castor Large Insert + Holes", "06b castor_(LG)_insert_+_holes.py"),
        ("Glides", "07 Glides.py"),
        ("Explode Fittings", "17 explode_fittings.py"),
    ]),
    ("Blocks", [
        ("Create / Redefine Block", "create_or_redefine_block.py"),
        ("Create / Redefine Block + Add Instance", "create_or_redefine_block_and_insert_copy.py"),
        ("Create / Redefine Block Using SKU Insertion Point", "create_or_redefine_block_from_sku_insert_point.py"),
        ("Zero SKU Insertion Z", "12 zero_sku_insertion_z.py"),
    ]),
    ("Drawings + Annotation", [
        ("Bounding Dimensions", "13 bounding_dimensions.py"),
        ("Numbered Dots", "14 numbered_dots.py"),
        ("Plan View with Block names", "09 plan view.py"),
        ("Assembly Steps", "20 assembly_steps.py"),
        ("Assembly Symbols", "21 assembly_symbols.py"),
    ]),
    ("Export", [
        ("Snapshot 2D Export", "16 snapshot_2d_export.py"),
        ("Export Blocks to SketchUp", "11 export_blocks_to_skp.py"),
        ("Export Blocks to Rhino", "11a export_blocks_to_3dm.py"),
    ]),
    ("Templates", [
        ("Annotation Styles", "18 annotation_styles.py"),
        ("Display Modes", "19 display_modes.py"),
    ]),
]


# ---------------------------------------------------------------- state ---

def state_path():
    return os.path.join(INSTALL_ROOT, "_user_data", STATE_FILENAME)


def load_state():
    state = {"favourites": [], "recent": [], "expanded": [], "collapsed": [], "panel_open": True}
    path = state_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                state["favourites"] = [f for f in saved.get("favourites", []) if isinstance(f, str)]
                state["recent"] = [f for f in saved.get("recent", []) if isinstance(f, str)]
                state["expanded"] = [f for f in saved.get("expanded", []) if isinstance(f, str)]
                state["collapsed"] = [f for f in saved.get("collapsed", []) if isinstance(f, str)]
                state["panel_open"] = bool(saved.get("panel_open", True))
        except Exception:
            pass
    return state


def save_state(state):
    folder = os.path.dirname(state_path())
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(state_path(), "w") as handle:
            json.dump(state, handle, indent=2)
    except Exception:
        pass


# -------------------------------------------------------------- catalog ---

def tool_table():
    """(label, filename) rows from np_launcher, without this menu itself."""
    return [(label, filename) for label, filename in np_launcher.SCRIPT_CHOICES
            if filename != MENU_FILENAME]


def build_groups():
    """[(category, [(menu label, filename), ...]), ...] for scripts the launcher knows."""
    rows = tool_table()
    known = set(filename for _, filename in rows)
    groups = []
    used = set()
    for title, entries in CATEGORIES:
        members = [(label, f) for label, f in entries if f in known and f not in used]
        used.update(f for _, f in members)
        if members:
            groups.append((title, members))
    rest = [(label, f) for label, f in rows if f not in used]
    if rest:
        groups.append((OTHER_TITLE, rest))
    return groups


def make_key(filename, choice=None):
    """State key: a tool is its filename, a drawer choice is 'filename::choice'."""
    return filename if not choice else filename + "::" + choice


def split_key(key):
    parts = str(key).split("::", 1)
    return parts[0], (parts[1] if len(parts) > 1 else None)


def labels_by_file(groups):
    out = {}
    for _, members in groups:
        for label, filename in members:
            out[filename] = label
    return out


def load_tool_module(filename):
    """Import a tool script by path without running it (its main() is guarded)."""
    path = os.path.join(THIS_DIR, filename)
    name = "np_tool_" + re.sub(r"\W+", "_", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def submenu_entries(filename):
    """The choices the tool's list dialog would offer, or [] if it has none."""
    if filename not in SUBMENU_TOOLS:
        return []
    try:
        return [str(item) for item in load_tool_module(filename).menu_items()]
    except Exception:
        log(traceback.format_exc(), "ERROR")
        return []


def write_menu_choice(filename, choice):
    """Hand a drawer choice to the script about to run."""
    folder = os.path.join(INSTALL_ROOT, "_user_data")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(os.path.join(folder, CHOICE_FILENAME), "w") as handle:
        json.dump({"script": filename, "choice": choice, "time": time.time()}, handle)


def version_text():
    version, updated = "unknown", "unknown"
    if np_deploy:
        try:
            root = np_deploy.get_install_root(os.path.join(INSTALL_ROOT, "manifest.json"))
            version, updated = np_deploy.get_version_display(root)
        except Exception:
            pass
    return "Version {}   Updated {}".format(version, updated)


def log(message, level="INFO"):
    if np_deploy:
        try:
            np_deploy.log_message(INSTALL_ROOT, message, level)
            return
        except Exception:
            pass
    Rhino.RhinoApp.WriteLine("NP Menu: " + message)


def style_label(label, size, bold=False, color=None):
    """Font, colour and left alignment for a label. Rhino's panel host restyles
    labels when they load (right-aligned, default font), so apply the style now
    and again on LoadComplete."""
    def apply(sender=None, e=None):
        try:
            label.Font = drawing.Font(drawing.SystemFont.Bold if bold else drawing.SystemFont.Default, size)
            label.TextAlignment = forms.TextAlignment.Left
            if color is not None:
                label.TextColor = color
        except Exception:
            pass
    apply()
    label.LoadComplete += apply
    return label


def no_focus(button):
    """Keep keyboard focus out of the panel's buttons, so a click on a tool
    leaves Rhino's command line ready for Enter (macOS; harmless elsewhere)."""
    try:
        button.ControlObject.RefusesFirstResponder = True
    except Exception:
        pass


def focus_rhino():
    """Hand keyboard focus back to Rhino's main window."""
    try:
        Rhino.RhinoApp.SetFocusToMainWindow()
    except Exception:
        pass


def left_align(button):
    """Eto has no text alignment on Button; set it on the native control."""
    no_focus(button)
    native = button.ControlObject
    try:  # macOS (AppKit NSButton)
        import AppKit
        native.Alignment = AppKit.NSTextAlignment.Left
        return
    except Exception:
        pass
    try:  # Windows (WPF Button)
        import System.Windows
        native.HorizontalContentAlignment = System.Windows.HorizontalAlignment.Left
        native.Padding = System.Windows.Thickness(8, 1, 4, 1)
    except Exception:
        pass


# ----------------------------------------------------------------- view ---

class NPMenuView(forms.Panel):
    """The menu itself. One instance fills each Rhino panel instance."""

    def __init__(self):
        super().__init__()
        self.state = load_state()
        self.groups = build_groups()
        self.by_file = labels_by_file(self.groups)
        self.Padding = drawing.Padding(6)

        self.search = forms.SearchBox()
        self.search.PlaceholderText = "Filter tools...  (Enter runs the first match)"
        self.search.TextChanged += self.on_search_changed
        self.search.KeyDown += self.on_search_key

        self.scroll = forms.Scrollable()
        try:
            self.scroll.Border = forms.BorderType.None_  # pythonnet spelling of None
        except Exception:
            pass
        self.scroll.ExpandContentWidth = True

        self.version_label = forms.Label()
        self.version_label.Text = version_text()
        style_label(self.version_label, 9, color=drawing.Colors.Gray)

        guide_btn = forms.Button()
        guide_btn.Text = "Guide"
        guide_btn.ToolTip = "Open the NP guide in your browser"
        guide_btn.Click += self.on_guide

        update_btn = forms.Button()
        update_btn.Text = "Force Update"
        update_btn.ToolTip = "Download the latest tools now"
        update_btn.Click += self.on_force_update
        no_focus(guide_btn)
        no_focus(update_btn)

        footer = forms.DynamicLayout()
        footer.Spacing = drawing.Size(6, 6)
        footer.AddRow(self.version_label)
        footer.AddRow(guide_btn, update_btn, None)

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 8)
        layout.AddRow(self.search)
        layout.Add(self.scroll, True, True)
        layout.AddRow(footer)
        self.Content = layout

        self._entries = {}
        self.rebuild()

    # ------------------------------------------------------------ build --

    def query_words(self):
        return [w for w in (self.search.Text or "").lower().split() if w]

    def matches(self, label, filename, choice=None):
        words = self.query_words()
        if not words:
            return True
        haystack = (label + " " + filename + " " + (choice or "")).lower()
        return all(w in haystack for w in words)

    def visible_tools(self):
        """Ordered (label, filename, choice) rows that pass the filter, no repeats."""
        seen = set()
        out = []
        for _, rows in self.sections():
            for label, filename, choice in rows:
                key = make_key(filename, choice)
                if key not in seen and self.matches(label, filename, choice):
                    seen.add(key)
                    out.append((label, filename, choice))
        return out

    def row_label(self, filename, choice=None):
        tool = self.by_file.get(filename, filename)
        return tool if choice is None else "{}  ({})".format(choice, tool)

    def pick_rows(self, keys):
        """(label, filename, choice) rows for saved keys that still exist."""
        out = []
        for key in keys:
            filename, choice = split_key(key)
            if filename not in self.by_file:
                continue
            if choice is not None and choice not in self.entries_for(filename):
                continue
            out.append((self.row_label(filename, choice), filename, choice))
        return out

    def sections(self):
        """Favourites and Recent first, then the categories. Rows are
        (label, filename, choice); choice is None for a tool, or the drawer
        entry for a favourited or recently used choice."""
        out = []
        favs = self.pick_rows(self.state["favourites"])
        if favs:
            out.append(("Favourites", favs))
        recent = self.pick_rows(self.state["recent"])
        if recent:
            out.append(("Recent", recent))
        for title, members in self.groups:
            out.append((title, [(label, filename, None) for label, filename in members]))
        return out

    def entries_for(self, filename):
        if filename not in self._entries:
            self._entries[filename] = submenu_entries(filename)
        return self._entries[filename]

    def entry_matches(self, entry):
        words = self.query_words()
        return bool(words) and all(w in entry.lower() for w in words)

    def rebuild(self):
        try:
            self._entries = {}
            column = forms.StackLayout()
            column.Orientation = forms.Orientation.Vertical
            column.HorizontalContentAlignment = forms.HorizontalAlignment.Stretch
            column.Spacing = 3
            column.Padding = drawing.Padding(0, 0, 8, 0)
            shown = 0
            searching = bool(self.query_words())
            for title, rows in self.sections():
                folded = (not searching) and title in self.state["collapsed"]
                block = []
                for label, filename, choice in rows:
                    if choice is not None:
                        if self.matches(label, filename, choice):
                            block.append((label, filename, choice, False, False, []))
                        continue
                    has_drawer = filename in SUBMENU_TOOLS
                    entries = self.entries_for(filename) if has_drawer else []
                    hits = [e for e in entries if self.entry_matches(e)]
                    tool_hit = self.matches(label, filename)
                    if not tool_hit and not hits:
                        continue
                    if hits and not tool_hit:
                        shown_entries, expanded = hits, True
                    else:
                        expanded = filename in self.state["expanded"]
                        shown_entries = entries if expanded else []
                    block.append((label, filename, None, has_drawer, expanded, shown_entries))
                if not block:
                    continue
                column.Items.Add(forms.StackLayoutItem(self.heading(title, folded), False))
                if folded:
                    shown += len(block)
                    block = []
                for label, filename, choice, has_drawer, expanded, shown_entries in block:
                    column.Items.Add(forms.StackLayoutItem(
                        self.tool_row(label, filename, has_drawer, expanded, choice), False))
                    for entry in shown_entries:
                        column.Items.Add(forms.StackLayoutItem(self.entry_row(filename, entry), False))
                    shown += 1
                gap = forms.Panel()
                gap.Size = drawing.Size(-1, 8)
                column.Items.Add(forms.StackLayoutItem(gap, False))
            if not shown:
                empty = forms.Label()
                empty.Text = "No tools match."
                style_label(empty, 11, color=drawing.Colors.Gray)
                column.Items.Add(forms.StackLayoutItem(empty, False))
            self.scroll.Content = column
        except Exception:
            log(traceback.format_exc(), "ERROR")

    def tool_row(self, label, filename, has_drawer, expanded, choice=None):
        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.VerticalContentAlignment = forms.VerticalAlignment.Center
        row.Spacing = 4
        row.Items.Add(forms.StackLayoutItem(self.star_button(make_key(filename, choice)), False))
        if choice is not None:
            row.Items.Add(forms.StackLayoutItem(self.tool_button(label, filename, choice), True))
        elif has_drawer:
            button = forms.Button()
            button.Text = ("\u25be  " if expanded else "\u25b8  ") + label
            button.ToolTip = "Hide the choices" if expanded else "Show the choices for " + label
            button.Click += lambda sender, e, f=filename: self.toggle_expanded(f)
            left_align(button)
            row.Items.Add(forms.StackLayoutItem(button, True))
        else:
            row.Items.Add(forms.StackLayoutItem(self.tool_button(label, filename), True))
        return row

    def entry_row(self, filename, entry):
        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.VerticalContentAlignment = forms.VerticalAlignment.Center
        row.Spacing = 4
        indent = forms.Panel()
        indent.Size = drawing.Size(16, -1)
        row.Items.Add(forms.StackLayoutItem(indent, False))
        row.Items.Add(forms.StackLayoutItem(self.star_button(make_key(filename, entry)), False))
        row.Items.Add(forms.StackLayoutItem(self.tool_button(entry, filename, entry), True))
        return row

    def collapse(self, filename):
        """Close a drawer (after one of its choices has been run)."""
        if filename in self.state["expanded"]:
            self.state["expanded"].remove(filename)
            save_state(self.state)

    def toggle_expanded(self, filename):
        expanded = self.state["expanded"]
        if filename in expanded:
            expanded.remove(filename)
        else:
            expanded.append(filename)
        save_state(self.state)
        self.refresh_later()

    def heading(self, text, folded=False):
        """Category title: a button drawn as a dark bar with white bold text, so
        it reads as a title and still takes clicks inside Rhino's panel host
        (plain labels and panels get no mouse events there on macOS). Clicking
        folds the category away or opens it again; a search shows every match
        whatever is folded. The host restyles controls when they load, so the
        look is applied again on LoadComplete."""
        button = forms.Button()
        button.Text = ("\u25b8  " if folded else "\u25be  ") + text
        button.ToolTip = "Show " + text if folded else "Fold " + text + " away"
        button.Size = drawing.Size(-1, HEADING_HEIGHT)

        def restyle(sender=None, e=None):
            try:
                button.Font = drawing.Font(drawing.SystemFont.Bold, 12)
                button.TextColor = drawing.Colors.White
                button.BackgroundColor = HEADING_BACKGROUND
            except Exception:
                pass

        restyle()
        button.LoadComplete += restyle
        button.Click += lambda sender, e, t=text: self.toggle_collapsed(t)
        left_align(button)
        return button

    def toggle_collapsed(self, title):
        collapsed = self.state["collapsed"]
        if title in collapsed:
            collapsed.remove(title)
        else:
            collapsed.append(title)
        save_state(self.state)
        self.refresh_later()

    def tool_button(self, label, filename, choice=None):
        button = forms.Button()
        button.Text = label
        button.ToolTip = filename if choice is None else "{}: {}".format(self.by_file.get(filename, filename), choice)
        button.Click += lambda sender, e, f=filename, c=choice: self.run_tool(f, c)
        left_align(button)
        return button

    def star_button(self, key):
        star = forms.Button()
        star.Size = drawing.Size(32, -1)
        star.MinimumSize = drawing.Size(32, 0)
        is_fav = key in self.state["favourites"]
        star.Text = "★" if is_fav else "☆"
        star.ToolTip = "Remove from favourites" if is_fav else "Add to favourites"
        star.Click += lambda sender, e, k=key: self.toggle_favourite(k)
        no_focus(star)
        return star

    def refresh_later(self):
        forms.Application.Instance.AsyncInvoke(self.rebuild)

    # ----------------------------------------------------------- actions --

    def toggle_favourite(self, key):
        favs = self.state["favourites"]
        if key in favs:
            favs.remove(key)
        else:
            favs.append(key)
        save_state(self.state)
        self.refresh_later()

    def remember_recent(self, key):
        recent = [k for k in self.state["recent"] if k != key]
        recent.insert(0, key)
        self.state["recent"] = recent[:MAX_RECENT]
        save_state(self.state)

    def run_tool(self, filename, choice=None):
        """Start a tool, with a drawer choice already made when given. If
        another tool is waiting for input, cancel it first (the "!" keystroke
        is Rhino's cancel) and launch once Rhino is idle; a script started
        straight away would only nest inside the old one."""
        self.remember_recent(make_key(filename, choice))
        script_path = os.path.join(os.path.dirname(os.path.abspath(np_launcher.__file__)), filename)
        if not os.path.isfile(script_path):
            Rhino.UI.Dialogs.ShowMessage("Script file not found:\n{}".format(script_path), "NP Menu")
            return
        if choice is not None:
            try:
                write_menu_choice(filename, choice)
            except Exception:
                log(traceback.format_exc(), "ERROR")
            self.collapse(filename)
        macro = '! _-RunPythonScript "{}"'.format(script_path)
        try:
            if Rhino.Commands.Command.InCommand():
                Rhino.RhinoApp.SendKeystrokes("!", True)
                self.launch_when_idle(macro, filename)
            else:
                self.launch(macro, filename)
        except Exception:
            log(traceback.format_exc(), "ERROR")
        self.refresh_later()

    def launch(self, macro, filename):
        """Run the macro once the click that asked for it has finished. A script
        started inside the button event runs nested in that mouse event, and
        Rhino then wants a second click for every pick and every Done. Rhino's
        own toolbar buttons start macros the same deferred way."""
        def go():
            focus_rhino()
            try:
                if not Rhino.RhinoApp.RunScript(macro, False):
                    Rhino.RhinoApp.WriteLine("NP Menu: could not run {}".format(filename))
            except Exception:
                log(traceback.format_exc(), "ERROR")
        forms.Application.Instance.AsyncInvoke(go)

    def launch_when_idle(self, macro, filename, timeout=3.0):
        """Poll until the cancelled command has exited, then launch."""
        timer = forms.UITimer()
        timer.Interval = 0.1
        state = {"waited": 0.0}

        def tick(sender, e):
            state["waited"] += timer.Interval
            if not Rhino.Commands.Command.InCommand():
                timer.Stop()
                self.launch(macro, filename)
            elif state["waited"] >= timeout:
                timer.Stop()
                Rhino.RhinoApp.WriteLine(
                    "NP Menu: the running tool did not cancel; press Esc and try again.")

        timer.Elapsed += tick
        self._timer = timer
        timer.Start()

    def on_search_changed(self, sender, e):
        self.rebuild()

    def on_search_key(self, sender, e):
        try:
            if e.Key == forms.Keys.Enter:
                e.Handled = True
                rows = self.visible_tools() if self.query_words() else []
                if rows:
                    self.run_tool(rows[0][1], rows[0][2])
                else:
                    focus_rhino()
            elif e.Key == forms.Keys.Escape and self.search.Text:
                e.Handled = True
                self.search.Text = ""
        except Exception:
            log(traceback.format_exc(), "ERROR")

    def on_guide(self, sender, e):
        try:
            np_launcher.open_guide_url()
        except Exception:
            log(traceback.format_exc(), "ERROR")

    def on_force_update(self, sender, e):
        try:
            np_launcher.run_force_update()
        except Exception:
            log(traceback.format_exc(), "ERROR")
        self.reload_tools()

    def reload_tools(self):
        """Re-read the tool table after an update. The menu's own code reloads next open."""
        global np_launcher
        try:
            np_launcher = importlib.reload(np_launcher)
        except Exception:
            try:  # a view from an earlier run holds a module object Rhino has since dropped
                np_launcher = importlib.import_module("np_launcher")
            except Exception:
                log(traceback.format_exc(), "ERROR")
        self.state = load_state()
        self.groups = build_groups()
        self.by_file = labels_by_file(self.groups)
        self.version_label.Text = version_text()
        self.refresh_later()

    def focus_search(self):
        try:
            self.search.Focus()
        except Exception:
            pass


# ---------------------------------------------------------------- panel ---

def panel_type():
    """The .NET panel class Rhino registers. Emitted once per Rhino session:
    a public subclass of Eto.Forms.Panel with a default constructor and the
    Guid attribute Rhino insists on. Later runs find it in the app domain."""
    for asm in System.AppDomain.CurrentDomain.GetAssemblies():
        try:
            if asm.GetName().Name == PANEL_ASSEMBLY:
                found = asm.GetType(PANEL_TYPE_NAME)
                if found is not None and str(found.GUID).lower() == PANEL_GUID.lower():
                    return found
        except Exception:
            pass
    import clr
    import System.Reflection as R
    import System.Reflection.Emit as E
    builder = E.AssemblyBuilder.DefineDynamicAssembly(
        R.AssemblyName(PANEL_ASSEMBLY), E.AssemblyBuilderAccess.Run)
    module = builder.DefineDynamicModule(PANEL_ASSEMBLY)
    type_builder = module.DefineType(
        PANEL_TYPE_NAME, R.TypeAttributes.Public | R.TypeAttributes.Class, clr.GetClrType(forms.Panel))
    type_builder.DefineDefaultConstructor(R.MethodAttributes.Public)
    guid_attr = clr.GetClrType(System.Runtime.InteropServices.GuidAttribute)
    ctor = guid_attr.GetConstructor(System.Array[System.Type]([clr.GetClrType(System.String)]))
    type_builder.SetCustomAttribute(E.CustomAttributeBuilder(ctor, System.Array[System.Object]([PANEL_GUID])))
    return type_builder.CreateType()


def panel_icon():
    """A small 'NP' badge for the panel tab."""
    import System.Drawing as SD
    import System.Drawing.Drawing2D as D2
    bmp = SD.Bitmap(32, 32)
    g = SD.Graphics.FromImage(bmp)
    try:
        g.SmoothingMode = D2.SmoothingMode.AntiAlias
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAlias
        g.Clear(SD.Color.Transparent)
        g.FillEllipse(SD.SolidBrush(SD.Color.FromArgb(255, 36, 36, 36)), 1, 1, 30, 30)
        font = SD.Font("Helvetica", 13.0, SD.FontStyle.Bold, SD.GraphicsUnit.Pixel)
        fmt = SD.StringFormat()
        fmt.Alignment = SD.StringAlignment.Center
        fmt.LineAlignment = SD.StringAlignment.Center
        g.DrawString("NP", font, SD.Brushes.White, SD.RectangleF(0, 1, 32, 32), fmt)
    finally:
        g.Dispose()
    return SD.Icon.FromHandle(bmp.GetHicon())


def panel_guid():
    return System.Guid(PANEL_GUID)


# Plug-ins that may host the panel, in order of preference. Any loaded .NET
# plug-in will do: RegisterPanel only uses it as the panel's owner.
HOST_PLUGIN_NAMES = ("RhinoCodePlugin", "RhinoCode", "IronPython", "Commands",
                     "RDK_EtoUI", "RhinoCycles", "Rhino Render")


def host_plugin(preferred_id=HOST_PLUGIN_ID):
    """A loaded .NET plug-in to own the panel. The RhinoCode plug-in by id
    first, then by name, then any loaded .NET plug-in (ids differ between
    builds and PlugIn.Find only sees plug-ins that are loaded)."""
    try:
        plugin = Rhino.PlugIns.PlugIn.Find(System.Guid(preferred_id))
        if plugin is not None:
            return plugin
    except Exception:
        pass
    installed = []
    try:
        for pair in Rhino.PlugIns.PlugIn.GetInstalledPlugIns():
            installed.append((str(pair.Value), pair.Key))
    except Exception:
        log(traceback.format_exc(), "ERROR")
    by_name = dict((name.lower(), guid) for name, guid in installed)
    for name in HOST_PLUGIN_NAMES:
        guid = by_name.get(name.lower())
        if guid is None:
            continue
        plugin = Rhino.PlugIns.PlugIn.Find(guid)
        if plugin is None and name.lower() in ("rhinocodeplugin", "rhinocode", "ironpython"):
            try:
                Rhino.PlugIns.PlugIn.LoadPlugIn(guid)
                plugin = Rhino.PlugIns.PlugIn.Find(guid)
            except Exception:
                plugin = None
        if plugin is not None:
            return plugin
    for name, guid in installed:
        plugin = Rhino.PlugIns.PlugIn.Find(guid)
        if plugin is not None:
            return plugin
    log("No host plug-in for the panel. Installed: {}".format(
        ", ".join(sorted(name for name, _ in installed))), "ERROR")
    return None


def panel_instances():
    """Every live panel object Rhino holds for our id (one per document window on Mac)."""
    out = []
    getters = [lambda: Rhino.UI.Panels.GetPanel(panel_guid())]
    try:
        for doc in Rhino.RhinoDoc.OpenDocuments():
            getters.append(lambda d=doc: Rhino.UI.Panels.GetPanel(panel_guid(), d))
    except Exception:
        pass
    for get in getters:
        try:
            panel = get()
        except Exception:
            panel = None
        if panel is not None and all(panel is not p and not panel.Equals(p) for p in out):
            out.append(panel)
    return out


def ensure_content(panel, rebuild=False):
    """Give a panel instance its menu, once (or again after an update)."""
    views = sc.sticky.get(STICKY_VIEWS)
    if not isinstance(views, list):
        views = []
        sc.sticky[STICKY_VIEWS] = views
    try:
        current = panel.Content
    except Exception:
        current = None
    if current is not None and not rebuild:
        try:  # a view from an earlier run of this file is a different class; duck-type it
            current.reload_tools()
        except Exception:
            pass
        return current
    view = NPMenuView()
    panel.Content = view
    views[:] = [v for v in views if v is not current] + [view]
    return view


def on_panel_show(sender, e):
    """Rhino shows or hides our panel: fill new instances, remember the choice."""
    try:
        if e.PanelId != panel_guid():
            return
        if e.Show:
            for panel in panel_instances():
                ensure_content(panel)
            set_panel_open(True)
        elif not sc.sticky.get(STICKY_CLOSING):
            set_panel_open(False)
    except Exception:
        log(traceback.format_exc(), "ERROR")


def on_rhino_closing(sender, e):
    sc.sticky[STICKY_CLOSING] = True


def set_panel_open(flag):
    state = load_state()
    if state.get("panel_open") != flag:
        state["panel_open"] = flag
        save_state(state)


def hook_events():
    """(Re)attach the panel show/hide and Rhino closing handlers, without doubling up."""
    old = sc.sticky.get(STICKY_SHOW_HANDLER)
    if old is not None:
        try:
            Rhino.UI.Panels.Show -= old
        except Exception:
            pass
    Rhino.UI.Panels.Show += on_panel_show
    sc.sticky[STICKY_SHOW_HANDLER] = on_panel_show
    old = sc.sticky.get(STICKY_CLOSING_HANDLER)
    if old is not None:
        try:
            Rhino.RhinoApp.Closing -= old
        except Exception:
            pass
    Rhino.RhinoApp.Closing += on_rhino_closing
    sc.sticky[STICKY_CLOSING_HANDLER] = on_rhino_closing


def register_panel():
    """Register the panel with Rhino for this session. Returns False only when
    the host plug-in is missing; an already-registered panel counts as success."""
    plugin = host_plugin()
    if plugin is None:
        Rhino.RhinoApp.WriteLine(
            "NP Menu: no plug-in could host the panel (see _logs/np_deploy.log); the panel needs Rhino 8.")
        return False
    hook_events()
    try:
        Rhino.UI.Panels.RegisterPanel(plugin, panel_type(), PANEL_TITLE, panel_icon(), Rhino.UI.PanelType.System)
    except Exception as exc:
        text = str(exc)
        if "already" not in text.lower():
            log("RegisterPanel: " + text, "ERROR")
            Rhino.RhinoApp.WriteLine("NP Menu: could not register the panel: " + text)
            return False
    return True


def move_on_screen(panel):
    """A panel that floats for the first time can land off screen; pull it back."""
    try:
        form = panel.ParentWindow
        if form is None or not isinstance(form, forms.Form):
            return
        bounds = form.Bounds
        for screen in forms.Screen.Screens:
            if screen.WorkingArea.Intersects(bounds):
                return
        main = Rhino.UI.RhinoEtoApp.MainWindow
        area = main.Bounds if main is not None else forms.Screen.PrimaryScreen.WorkingArea
        width = max(int(bounds.Width), 360)
        height = max(int(bounds.Height), 600)
        x = int(area.Right) - width - 40
        y = int(area.Top) + 80
        form.Location = drawing.Point(x, y)
        form.Size = drawing.Size(width, height)
        form.BringToFront()
    except Exception:
        log(traceback.format_exc(), "ERROR")


def open_panel(rebuild=False):
    """Open the panel, docked beside Layers the first time, and fill it."""
    guid = panel_guid()
    opened = False
    try:
        if not Rhino.UI.Panels.IsPanelVisible(guid):
            opened = bool(Rhino.UI.Panels.OpenPanelAsSibling(guid, Rhino.UI.PanelIds.Layers, True))
    except Exception:
        opened = False
    if not opened:
        try:
            Rhino.UI.Panels.OpenPanel(guid, True)
        except Exception:
            log(traceback.format_exc(), "ERROR")
    view = None
    for panel in panel_instances():
        made = ensure_content(panel, rebuild=rebuild)
        view = made or view
        move_on_screen(panel)
    set_panel_open(True)
    return view


# --------------------------------------------------------------- startup ---

def startup_script_path():
    return os.path.join(THIS_DIR, STARTUP_FILENAME)


def startup_command():
    return '-_RunPythonScript "{}"'.format(os.path.abspath(startup_script_path()))


def general_settings():
    root = Rhino.PersistentSettings.FromPlugInId(Rhino.RhinoApp.CurrentRhinoId)
    return root.GetChild("Options").GetChild("General")


def ensure_startup_command():
    """Add np_menu_startup.py to Rhino's startup commands (Options > General >
    'Run these commands every time Rhino starts') so the panel survives a restart.
    Replaces an older NP entry that points somewhere else. Returns True when changed."""
    if not os.path.isfile(startup_script_path()):
        return False
    try:
        settings = general_settings()
        try:
            current = settings.GetString("StartupCommands", "") or ""
        except Exception:
            current = ""
        wanted = startup_command()
        lines = [line for line in current.replace("\r", "").split("\n") if line.strip()]
        if wanted in lines:
            return False
        lines = [line for line in lines if STARTUP_FILENAME not in line]
        lines.append(wanted)
        settings.SetString("StartupCommands", "\n".join(lines))
        return True
    except Exception:
        log(traceback.format_exc(), "ERROR")
        return False


def ensure_menu_alias():
    """Create the NPP alias if the user does not have one yet."""
    if not np_deploy or not hasattr(np_deploy, "ensure_command_alias"):
        return
    try:
        np_deploy.ensure_command_alias(MENU_ALIAS, np_deploy.build_np_menu_alias_command(INSTALL_ROOT))
    except Exception:
        pass


def update_check():
    """Same daily update check NP runs. Returns True when new files were installed."""
    if not np_deploy:
        return False
    try:
        root = np_deploy.get_install_root(os.path.join(INSTALL_ROOT, "manifest.json"))
        result = np_deploy.check_and_update(root)
        if result.get("updated"):
            Rhino.RhinoApp.WriteLine("NP Rhino Tools: " + (result.get("message") or "updated."))
            return True
        if result.get("error") and not result.get("skipped"):
            Rhino.RhinoApp.WriteLine(
                "NP update check failed (using local tools): {}".format(result["error"]))
    except Exception:
        log(traceback.format_exc(), "ERROR")
    try:
        import run_np_launcher
        run_np_launcher.ensure_material_search_path(INSTALL_ROOT)
    except Exception:
        pass
    return False


def startup():
    """Run by Rhino at startup (np_menu_startup.py): register the panel so the
    sidebar knows it, and reopen it when it was open at the end of the last session."""
    if not register_panel():
        return
    if load_state().get("panel_open", True):
        open_panel()


def main():
    """Alias NPP: register (first time this session), check for updates, open."""
    global np_launcher
    ensure_menu_alias()
    ensure_startup_command()
    updated = update_check()
    if updated:
        try:
            np_launcher = importlib.reload(np_launcher)
        except Exception:
            pass
    if not register_panel():
        return
    open_panel(rebuild=updated)


if __name__ == "__main__":
    main()
