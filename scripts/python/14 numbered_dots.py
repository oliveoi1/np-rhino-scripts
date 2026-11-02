"""
Sequential numbered Rhino text dots.

Starts at a user-selected number (default 1), then adds one Rhino text dot at
each clicked point and increments the text until the user presses Enter/Esc.
"""

import rhinoscriptsyntax as rs

DOT_LAYER = "NP-Annotation"
DEFAULT_START_NUMBER = 1


def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)


def main():
    start_number = rs.GetInteger(
        "Start number for dots",
        DEFAULT_START_NUMBER,
        1,
    )
    if start_number is None:
        return

    ensure_layer(DOT_LAYER)

    current_number = start_number
    dots_added = 0

    while True:
        point = rs.GetPoint(
            "Pick location for dot {}. Press Enter/Esc to finish".format(current_number)
        )
        if point is None:
            break

        dot_id = rs.AddTextDot(str(current_number), point)
        if dot_id:
            rs.ObjectLayer(dot_id, DOT_LAYER)
            dots_added += 1
            current_number += 1

    if dots_added:
        rs.MessageBox(
            "Numbered dots added: {}\nStarted at: {}\nEnded at: {}".format(
                dots_added,
                start_number,
                current_number - 1,
            )
        )


if __name__ == "__main__":
    main()
