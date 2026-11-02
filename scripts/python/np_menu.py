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
import sys
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

# Category -> script filenames (labels come from np_launcher.SCRIPT_CHOICES).
# A script missing from this table still appears, under "Other".
CATEGORIES = [
    ("Joinery", [
        "01 extrude_curves.py",
        "01a_extrude_ply_bands.py",
        "02 dado_recess.py",
        "02 dado_tongue.py",
        "02b Surface recess.py",
        "02c engrave.py",
    ]),
    ("Holes & Inserts", [
        "03a hole_insertpoints_auto.py",
        "03b grub_screws_and_holes.py",
        "03c dimple_hole.py",
        "03d custom_holes.py",
        "04a cam_inserts.py",
        "04b cam_holes_+_cams.py",
        "05a flipper_insert_auto.py",
        "05b flipper_holes_+flippers.py",
        "05c shelf_holes.py",
    ]),
    ("Hardware", [
        "06a castor_insert.py",
        "06b castor_(SM)_insert_+_holes.py",
        "06b castor_(LG)_insert_+_holes.py",
        "07 Glides.py",
        "15 insert_block.py",
        "17 explode_fittings.py",
    ]),
    ("Blocks", [
        "create_or_redefine_block.py",
        "create_or_redefine_block_and_insert_copy.py",
        "create_or_redefine_block_from_sku_insert_point.py",
        "12 zero_sku_insertion_z.py",
    ]),
    ("Annotation", [
        "13 bounding_dimensions.py",
        "14 numbered_dots.py",
        "18 annotation_styles.py",
    ]),
    ("Drawings & Export", [
        "09 plan view.py",
        "10 logo_cut.py",
        "16 snapshot_2d_export.py",
        "11 export_blocks_to_skp.py",
        "11a export_blocks_to_3dm.py",
    ]),
    ("Templates", [
        "19 display_modes.py",
    ]),
]


# ---------------------------------------------------------------- state ---

def state_path():
    return os.path.join(INSTALL_ROOT, "_user_data", STATE_FILENAME)


def load_state():
    state = {"favourites": [], "recent": [], "window": None}
    path = state_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                state["favourites"] = [f for f in saved.get("favourites", []) if isinstance(f, str)]
                state["recent"] = [f for f in saved.get("recent", []) if isinstance(f, str)]
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
    rows = tool_table()
    by_file = dict((filename, label) for label, filename in rows)
    groups = []
    used = set()
    for title, files in CATEGORIES:
        members = [(by_file[f], f) for f in files if f in by_file]
        used.update(f for _, f in members)
        if members:
            groups.append((title, members))
    rest = [(label, f) for label, f in rows if f not in used]
    if rest:
        groups.append((OTHER_TITLE, rest))
    return groups


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


# ----------------------------------------------------------------- form ---

class NPMenuForm(forms.Form):

    def __init__(self):
        super().__init__()
        self.state = load_state()
        self.groups = build_groups()
        self.by_file = dict((f, label) for label, f in tool_table())

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

    def rebuild(self):
        try:
            column = forms.StackLayout()
            column.Orientation = forms.Orientation.Vertical
            column.HorizontalContentAlignment = forms.HorizontalAlignment.Stretch
            column.Spacing = 3
            column.Padding = drawing.Padding(0, 0, 8, 0)
            shown = 0
            for title, rows in self.sections():
                rows = [(label, f) for label, f in rows if self.matches(label, f)]
                if not rows:
                    continue
                column.Items.Add(forms.StackLayoutItem(self.heading(title), False))
                for label, filename in rows:
                    row = forms.StackLayout()
                    row.Orientation = forms.Orientation.Horizontal
                    row.VerticalContentAlignment = forms.VerticalAlignment.Center
                    row.Spacing = 4
                    row.Items.Add(forms.StackLayoutItem(self.star_button(filename), False))
                    row.Items.Add(forms.StackLayoutItem(self.tool_button(label, filename), True))
                    column.Items.Add(forms.StackLayoutItem(row, False))
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
        self.remember_recent(filename)
        try:
            ok = np_launcher.run_script_file(filename)
            if not ok:
                Rhino.RhinoApp.WriteLine("NP Menu: could not run {}".format(filename))
        except Exception:
            log(traceback.format_exc(), "ERROR")
            Rhino.UI.Dialogs.ShowMessage(
                "Failed to run {}.\nSee _logs/np_deploy.log".format(filename), "NP Menu")
        self.refresh_later()

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
        self.by_file = dict((f, label) for label, f in tool_table())
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
