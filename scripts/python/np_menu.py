"""
NP Menu: a window that lists every NP tool by category.

Rhino alias NPM runs this file directly. It can also be opened from the
classic NP list ("NP Menu (window)"). Both front ends read the same tool
table, SCRIPT_CHOICES in np_launcher.py, so adding a tool there puts it in
both menus. The classic NP launcher is untouched by this file.

The window stays open while tools run, remembers favourites, recent tools
and its position in _user_data/np_menu_state.json, and runs the same daily
update check as NP when it is opened.
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


STICKY_KEY = "np_menu_form"
STATE_FILENAME = "np_menu_state.json"
MENU_FILENAME = "np_menu.py"
MENU_ALIAS = "NPM"
MAX_RECENT = 6
OTHER_TITLE = "Other"
CHOICE_FILENAME = "np_menu_choice.json"

# Tools whose first step is a list: the window shows that list as a drawer under
# the tool. Each script exposes menu_items() and reads the chosen entry from
# _user_data/np_menu_choice.json, skipping its own list dialog.
SUBMENU_TOOLS = [
    "15 insert_block.py",
    "19 display_modes.py",
    "18 annotation_styles.py",
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
    state = {"favourites": [], "recent": [], "expanded": [], "window": None}
    path = state_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                state["favourites"] = [f for f in saved.get("favourites", []) if isinstance(f, str)]
                state["recent"] = [f for f in saved.get("recent", []) if isinstance(f, str)]
                state["expanded"] = [f for f in saved.get("expanded", []) if isinstance(f, str)]
                window = saved.get("window")
                if isinstance(window, dict):
                    state["window"] = window
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


def left_align(button):
    """Eto has no text alignment on Button; set it on the native control."""
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


# ----------------------------------------------------------------- form ---

class NPMenuForm(forms.Form):

    def __init__(self):
        super().__init__()
        self.state = load_state()
        self.groups = build_groups()
        self.by_file = labels_by_file(self.groups)

        self.Title = "NP Rhino Tools"
        self.Padding = drawing.Padding(10)
        self.Resizable = True
        self.Maximizable = False
        self.MinimumSize = drawing.Size(360, 420)
        self.ClientSize = drawing.Size(400, 700)
        try:
            self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        except Exception:
            pass

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
        self.version_label.TextColor = drawing.Colors.Gray
        self.version_label.Font = drawing.Font(drawing.SystemFont.Default, 9)

        guide_btn = forms.Button()
        guide_btn.Text = "Guide"
        guide_btn.ToolTip = "Open the NP guide in your browser"
        guide_btn.Click += self.on_guide

        update_btn = forms.Button()
        update_btn.Text = "Force Update"
        update_btn.ToolTip = "Download the latest tools now"
        update_btn.Click += self.on_force_update

        close_btn = forms.Button()
        close_btn.Text = "Close"
        close_btn.Click += lambda sender, e: self.Close()
        self.AbortButton = close_btn

        footer = forms.DynamicLayout()
        footer.Spacing = drawing.Size(6, 6)
        footer.AddRow(self.version_label)
        footer.AddRow(guide_btn, update_btn, None, close_btn)

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 8)
        layout.AddRow(self.search)
        layout.Add(self.scroll, True, True)
        layout.AddRow(footer)
        self.Content = layout

        self._entries = {}
        self.Closed += self.on_closed
        self.rebuild()

    # ------------------------------------------------------------ build --

    def query_words(self):
        return [w for w in (self.search.Text or "").lower().split() if w]

    def matches(self, label, filename):
        words = self.query_words()
        if not words:
            return True
        haystack = (label + " " + filename).lower()
        return all(w in haystack for w in words)

    def visible_tools(self):
        """Ordered (label, filename) rows that pass the filter, no repeats."""
        seen = set()
        out = []
        for _, rows in self.sections():
            for label, filename in rows:
                if filename not in seen and self.matches(label, filename):
                    seen.add(filename)
                    out.append((label, filename))
        return out

    def sections(self):
        """Favourites and Recent first, then the categories."""
        out = []
        favs = [(self.by_file[f], f) for f in self.state["favourites"] if f in self.by_file]
        if favs:
            out.append(("Favourites", favs))
        recent = [(self.by_file[f], f) for f in self.state["recent"] if f in self.by_file]
        if recent:
            out.append(("Recent", recent))
        out.extend(self.groups)
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
            for title, rows in self.sections():
                block = []
                for label, filename in rows:
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
                    block.append((label, filename, has_drawer, expanded, shown_entries))
                if not block:
                    continue
                column.Items.Add(forms.StackLayoutItem(self.heading(title), False))
                for label, filename, has_drawer, expanded, shown_entries in block:
                    column.Items.Add(forms.StackLayoutItem(
                        self.tool_row(label, filename, has_drawer, expanded), False))
                    for entry in shown_entries:
                        column.Items.Add(forms.StackLayoutItem(self.entry_row(filename, entry), False))
                    shown += 1
                gap = forms.Panel()
                gap.Size = drawing.Size(-1, 8)
                column.Items.Add(forms.StackLayoutItem(gap, False))
            if not shown:
                empty = forms.Label()
                empty.Text = "No tools match."
                empty.TextColor = drawing.Colors.Gray
                column.Items.Add(forms.StackLayoutItem(empty, False))
            self.scroll.Content = column
        except Exception:
            log(traceback.format_exc(), "ERROR")

    def tool_row(self, label, filename, has_drawer, expanded):
        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.VerticalContentAlignment = forms.VerticalAlignment.Center
        row.Spacing = 4
        row.Items.Add(forms.StackLayoutItem(self.star_button(filename), False))
        if has_drawer:
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
        indent.Size = drawing.Size(32 + 4 + 16, -1)
        row.Items.Add(forms.StackLayoutItem(indent, False))
        button = forms.Button()
        button.Text = entry
        button.ToolTip = filename
        button.Click += lambda sender, e, f=filename, c=entry: self.run_entry(f, c)
        left_align(button)
        row.Items.Add(forms.StackLayoutItem(button, True))
        return row

    def toggle_expanded(self, filename):
        expanded = self.state["expanded"]
        if filename in expanded:
            expanded.remove(filename)
        else:
            expanded.append(filename)
        save_state(self.state)
        self.refresh_later()

    def run_entry(self, filename, choice):
        try:
            write_menu_choice(filename, choice)
        except Exception:
            log(traceback.format_exc(), "ERROR")
        self.run_tool(filename)

    @staticmethod
    def heading(text):
        label = forms.Label()
        label.Text = text
        label.Font = drawing.Font(drawing.SystemFont.Bold, 12)
        label.TextAlignment = forms.TextAlignment.Left
        return label

    def tool_button(self, label, filename):
        button = forms.Button()
        button.Text = label
        button.ToolTip = filename
        button.Click += lambda sender, e, f=filename: self.run_tool(f)
        left_align(button)
        return button

    def star_button(self, filename):
        star = forms.Button()
        star.Size = drawing.Size(32, -1)
        star.MinimumSize = drawing.Size(32, 0)
        is_fav = filename in self.state["favourites"]
        star.Text = "★" if is_fav else "☆"
        star.ToolTip = "Remove from favourites" if is_fav else "Add to favourites"
        star.Click += lambda sender, e, f=filename: self.toggle_favourite(f)
        return star

    def refresh_later(self):
        forms.Application.Instance.AsyncInvoke(self.rebuild)

    # ----------------------------------------------------------- actions --

    def toggle_favourite(self, filename):
        favs = self.state["favourites"]
        if filename in favs:
            favs.remove(filename)
        else:
            favs.append(filename)
        save_state(self.state)
        self.refresh_later()

    def remember_recent(self, filename):
        recent = [f for f in self.state["recent"] if f != filename]
        recent.insert(0, filename)
        self.state["recent"] = recent[:MAX_RECENT]
        save_state(self.state)

    def run_tool(self, filename):
        """Start a tool. If another tool is waiting for input, cancel it first
        (the "!" keystroke is Rhino's cancel) and launch once Rhino is idle;
        a script started straight away would only nest inside the old one."""
        self.remember_recent(filename)
        script_path = os.path.join(os.path.dirname(os.path.abspath(np_launcher.__file__)), filename)
        if not os.path.isfile(script_path):
            Rhino.UI.Dialogs.ShowMessage("Script file not found:\n{}".format(script_path), "NP Menu")
            return
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
        if not Rhino.RhinoApp.RunScript(macro, False):
            Rhino.RhinoApp.WriteLine("NP Menu: could not run {}".format(filename))

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
                rows = self.visible_tools()
                if rows:
                    e.Handled = True
                    self.run_tool(rows[0][1])
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
            log(traceback.format_exc(), "ERROR")
        self.groups = build_groups()
        self.by_file = labels_by_file(self.groups)
        self.version_label.Text = version_text()
        self.refresh_later()

    # ------------------------------------------------------------ window --

    def restore_window(self):
        window = self.state.get("window") or {}
        try:
            w, h = int(window.get("w", 0)), int(window.get("h", 0))
            if w >= 300 and h >= 300:
                self.ClientSize = drawing.Size(w, h)
            if "x" in window and "y" in window:
                self.Location = drawing.Point(int(window["x"]), int(window["y"]))
        except Exception:
            pass

    def on_closed(self, sender, e):
        try:
            self.state["window"] = {
                "x": self.Location.X, "y": self.Location.Y,
                "w": self.ClientSize.Width, "h": self.ClientSize.Height,
            }
            save_state(self.state)
        except Exception:
            pass
        if sc.sticky.get(STICKY_KEY) is self:
            sc.sticky[STICKY_KEY] = None

    def show(self):
        self.restore_window()
        self.Show()
        try:
            self.search.Focus()
        except Exception:
            pass


# --------------------------------------------------------------- startup ---

def ensure_menu_alias():
    """Create the NPM alias if the user does not have one yet."""
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


def main():
    global np_launcher
    existing = sc.sticky.get(STICKY_KEY)
    if existing is not None:
        try:
            if existing.Visible:
                existing.reload_tools()
                existing.BringToFront()
                return
        except Exception:
            pass
        sc.sticky[STICKY_KEY] = None

    ensure_menu_alias()
    if update_check():
        try:
            np_launcher = importlib.reload(np_launcher)
        except Exception:
            pass

    form = NPMenuForm()
    sc.sticky[STICKY_KEY] = form
    form.show()


if __name__ == "__main__":
    main()
