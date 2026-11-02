"""
18 - Annotation Styles

Apply one dimension style to every annotation in the document (or to the
selected annotations) so drawings from different people look the same.
Clears per-object style overrides, makes the chosen style current, and can
delete the dimension styles that are then unused.

Team styles can be kept in templates/NP_Annotation_Styles.3dm. Styles in that
file are offered alongside the document's own, and "Save a style to the team
template" writes one of the document's styles into it so it can be committed.
"""

import json
import os
import sys

import Rhino
import Rhino.Geometry as rg
import rhinoscriptsyntax as rs
import scriptcontext as sc

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
TEMPLATE_FILE = os.path.join(_INSTALL_ROOT, "templates", "NP_Annotation_Styles.3dm")

STICKY_KEY = "np_annotation_styles"
DEFAULTS_FILENAME = "annotation_styles_defaults.json"
FALLBACK = {"style": "", "purge": False}
TEMPLATE_PREFIX = "Team template: "
SAVE_LABEL = "Save a style to the team template..."
TITLE = "NP Annotation Styles"


# ------------------------------------------------------------- defaults ---

def defaults_path():
    return os.path.join(_INSTALL_ROOT, "_user_data", DEFAULTS_FILENAME)


def load_defaults():
    data = dict(FALLBACK)
    saved = sc.sticky.get(STICKY_KEY)
    if not saved and os.path.isfile(defaults_path()):
        try:
            with open(defaults_path(), "r") as handle:
                saved = json.load(handle)
        except Exception:
            saved = None
    if isinstance(saved, dict):
        data["style"] = str(saved.get("style", data["style"]) or "")
        data["purge"] = bool(saved.get("purge", data["purge"]))
    return data


def save_defaults(data):
    sc.sticky[STICKY_KEY] = dict(data)
    folder = os.path.dirname(defaults_path())
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(defaults_path(), "w") as handle:
            json.dump(data, handle)
    except Exception:
        pass


# ------------------------------------------------------------- template ---

def template_styles():
    """Dimension styles stored in the team template file, if it exists."""
    if not os.path.isfile(TEMPLATE_FILE):
        return []
    try:
        model = Rhino.FileIO.File3dm.Read(TEMPLATE_FILE)
    except Exception:
        return []
    if model is None:
        return []
    styles = [ds for ds in model.AllDimStyles if not ds.IsDeleted]
    styles.sort(key=lambda ds: ds.Name.lower())
    return styles


def import_template_style(style):
    """Bring a template style into the document, replacing a same-named style."""
    table = sc.doc.DimStyles
    existing = table.FindName(style.Name)
    if existing is not None:
        table.Modify(style, existing.Index, True)
        return table.FindName(style.Name)
    index = table.Add(style, False)
    if index < 0:
        return None
    return table[index]


def save_style_to_template(style):
    """Write a document style into the template file, replacing a same-named one."""
    keep = [ds for ds in template_styles() if ds.Name != style.Name]
    model = Rhino.FileIO.File3dm()
    for ds in keep:
        model.AllDimStyles.Add(ds)
    model.AllDimStyles.Add(style)
    folder = os.path.dirname(TEMPLATE_FILE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return model.Write(TEMPLATE_FILE, 8)


# ---------------------------------------------------------- annotations ---

def annotation_objects(selected_only):
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.NormalObjects = True
    settings.LockedObjects = True
    settings.HiddenObjects = True
    settings.IncludeLights = False
    settings.IncludeGrips = False
    settings.ActiveObjects = True
    settings.ReferenceObjects = False
    settings.SelectedObjectsFilter = bool(selected_only)
    out = []
    for obj in sc.doc.Objects.GetObjectList(settings):
        if isinstance(obj.Geometry, rg.AnnotationBase):
            out.append(obj)
    return out


def apply_style(objects, style):
    """Returns (changed, unchanged, failed)."""
    changed = unchanged = failed = 0
    for obj in objects:
        geom = obj.Geometry
        if geom.DimensionStyleId == style.Id and not geom.HasPropertyOverrides:
            unchanged += 1
            continue
        try:
            if geom.HasPropertyOverrides:
                geom.ClearPropertyOverrides()
            geom.DimensionStyleId = style.Id
            if obj.CommitChanges():
                changed += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return changed, unchanged, failed


def purge_unused_styles(keep_id):
    """Delete dimension styles no annotation uses. Returns names removed."""
    table = sc.doc.DimStyles
    in_use = set(obj.Geometry.DimensionStyleId for obj in annotation_objects(False))
    for obj in annotation_objects(False):
        parent = obj.Geometry.ParentDimensionStyle
        if parent is not None:
            in_use.add(parent.Id)
    in_use.add(keep_id)
    in_use.add(table.Current.Id)
    removed = []
    for style in list(table):
        if style.IsDeleted or style.IsReference or style.Id in in_use:
            continue
        name = style.Name
        if table.Delete(style.Index, True):
            removed.append(name)
    return removed


# ----------------------------------------------------------------- main ---

def doc_styles():
    styles = [ds for ds in sc.doc.DimStyles if not ds.IsDeleted and not ds.IsReference]
    styles.sort(key=lambda ds: ds.Name.lower())
    return styles


def choose_style(defaults):
    """Returns (style, saved_to_template). style is None when cancelled."""
    local = doc_styles()
    remote = template_styles()
    items = [ds.Name for ds in local]
    items += [TEMPLATE_PREFIX + ds.Name for ds in remote]
    items.append(SAVE_LABEL)

    default = defaults.get("style") or sc.doc.DimStyles.Current.Name
    if default not in items:
        default = sc.doc.DimStyles.Current.Name
    choice = rs.ListBox(items, "Dimension style to apply to all annotations", TITLE, default)
    if not choice:
        return None, False

    if choice == SAVE_LABEL:
        name = rs.ListBox([ds.Name for ds in local], "Style to save into the team template", TITLE,
                          sc.doc.DimStyles.Current.Name)
        if name:
            style = sc.doc.DimStyles.FindName(name)
            if style is not None and save_style_to_template(style):
                rs.MessageBox(
                    "Saved '{}' to:\n{}\n\nCommit and push that file so the team receives it."
                    .format(name, TEMPLATE_FILE), 0, TITLE)
            else:
                rs.MessageBox("Could not write the template file.", 0, TITLE)
        return None, True

    if choice.startswith(TEMPLATE_PREFIX):
        name = choice[len(TEMPLATE_PREFIX):]
        for ds in remote:
            if ds.Name == name:
                style = import_template_style(ds)
                if style is None:
                    rs.MessageBox("Could not import '{}'.".format(name), 0, TITLE)
                return style, False
        return None, False

    return sc.doc.DimStyles.FindName(choice), False


def main():
    defaults = load_defaults()
    preselected = rs.SelectedObjects(False, False) or []
    style, _ = choose_style(defaults)
    if style is None:
        return

    scope_default = "Selected" if preselected else "All"
    scope = rs.GetString("Apply to", scope_default, ["All", "Selected"])
    if scope is None:
        return
    if scope.lower().startswith("s") and not preselected:
        ids = rs.GetObjects("Select annotations", rs.filter.annotation, preselect=True)
        if not ids:
            return
    selected_only = scope.lower().startswith("s")

    purge_default = "Yes" if defaults.get("purge") else "No"
    purge = rs.GetString("Delete unused dimension styles afterwards", purge_default, ["Yes", "No"])
    if purge is None:
        return
    purge = purge.lower().startswith("y")

    save_defaults({"style": style.Name, "purge": purge})

    record = sc.doc.BeginUndoRecord("NP Annotation Styles")
    try:
        objects = annotation_objects(selected_only)
        changed, unchanged, failed = apply_style(objects, style)
        sc.doc.DimStyles.SetCurrent(style.Index, True)
        removed = purge_unused_styles(style.Id) if (purge and not selected_only) else []
    finally:
        sc.doc.EndUndoRecord(record)
    sc.doc.Views.Redraw()

    summary = "'{}' applied: {} changed, {} already matched".format(style.Name, changed, unchanged)
    if failed:
        summary += ", {} could not be changed".format(failed)
    if removed:
        summary += ". Removed unused styles: {}".format(", ".join(removed))
    elif purge and selected_only:
        summary += ". (Unused styles are only purged when applying to All.)"
    print(summary)
    if changed or removed:
        rs.MessageBox(summary, 0, TITLE)


if __name__ == "__main__":
    main()
