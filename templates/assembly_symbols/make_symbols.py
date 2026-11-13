#!/usr/bin/env python3
"""
Writes the assembly instruction symbols for InDesign, one SVG and one PDF each,
into this folder. Run it with any Python 3 (it does not need Rhino):

    python3 make_symbols.py

The shapes and colours are the ones the Tool call-out in
scripts/python/21 assembly_symbols.py draws, so a symbol placed in InDesign looks
like the one in a Rhino capture. Each file is drawn at the size it should have
on the page (UNIT_MM below), so placing it at 100% gives every drawing the same
size symbol.

Once the files are in the shared CC Library the library copy is the master:
edit it there. Run this again only to start over from the Rhino shapes.
"""

import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# fill colours of the NP Assembly display modes (templates/display_modes)
COLOURS = {
    "glue": (245, 225, 130),
    "grey": (120, 120, 120),
    "white": (245, 242, 235),
    "green": (112, 190, 72),
    "red": (222, 80, 64),
    "arrow": (210, 210, 210),
}
OUTLINE = (40, 40, 40)
OUTLINE_PT = 0.5        # outline weight on the page
MARGIN_MM = 0.5         # clear space around the artwork

# Size on the page, in mm, of one unit of the shape (a tool is about one unit tall).
UNIT_MM = {
    "GlueBottle": 9.0,
    "PhillipsBit": 9.0,
    "RobertsonBit": 9.0,
    "Mallet": 10.0,
    "Hammer": 10.0,
    "Tick": 7.0,
    "Cross": 7.0,
    "Flip": 14.0,
    "FlipLeft": 14.0,
}


# --- shapes, in units, y up ------------------------------------------------------

def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def turned(points, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def drop(cx, cy, r):
    """Teardrop with its point up."""
    points = [(cx, cy + r * 2.2)]
    for step in range(13):
        angle = math.radians(150 + step * 20)
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def stroke(points, half_width):
    """Outline polygon of a thick open polyline with mitred joins."""
    def unit(ax, ay):
        length = math.hypot(ax, ay) or 1.0
        return ax / length, ay / length
    normals = []
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:]):
        dx, dy = unit(x1 - x0, y1 - y0)
        normals.append((-dy, dx))

    def side(sign):
        out = []
        for index, (x, y) in enumerate(points):
            if index == 0:
                nx, ny = normals[0]
            elif index == len(points) - 1:
                nx, ny = normals[-1]
            else:
                ax, ay = normals[index - 1]
                bx, by = normals[index]
                mx, my = unit(ax + bx, ay + by)
                scale = 1.0 / max(mx * ax + my * ay, 0.2)
                nx, ny = mx * scale, my * scale
            out.append((x + sign * half_width * nx, y + sign * half_width * ny))
        return out
    return side(1) + list(reversed(side(-1)))


# A path is a list of commands: ("M", p), ("L", p), ("C", c1, c2, p), closed at the end.

def polygon(points, fillet=0.0):
    """Closed path through `points`, corners rounded with radius `fillet`."""
    count = len(points)
    if fillet <= 0:
        return [("M", points[0])] + [("L", p) for p in points[1:]]
    corners = []
    for i in range(count):
        before, here, after = points[i - 1], points[i], points[(i + 1) % count]
        in_x, in_y = here[0] - before[0], here[1] - before[1]
        out_x, out_y = after[0] - here[0], after[1] - here[1]
        in_len, out_len = math.hypot(in_x, in_y), math.hypot(out_x, out_y)
        in_x, in_y, out_x, out_y = in_x / in_len, in_y / in_len, out_x / out_len, out_y / out_len
        turn = math.acos(max(-1.0, min(1.0, in_x * out_x + in_y * out_y)))   # 0 = straight on
        if turn < 1e-6:
            corners.append((here, here, None, None))
            continue
        cut = min(fillet * math.tan(turn / 2.0), in_len / 2.0, out_len / 2.0)
        radius = cut / math.tan(turn / 2.0)
        handle = 4.0 / 3.0 * math.tan(turn / 4.0) * radius
        start = (here[0] - in_x * cut, here[1] - in_y * cut)
        end = (here[0] + out_x * cut, here[1] + out_y * cut)
        corners.append((start, end,
                        (start[0] + in_x * handle, start[1] + in_y * handle),
                        (end[0] - out_x * handle, end[1] - out_y * handle)))
    path = [("M", corners[0][1])]
    for start, end, c1, c2 in corners[1:] + corners[:1]:
        path.append(("L", start))
        if c1 is not None:
            path.append(("C", c1, c2, end))
    return path


def arc(centre, radius, start_degrees, end_degrees):
    """Curve commands along a circular arc (the start point is not included)."""
    span = end_degrees - start_degrees
    pieces = max(1, int(math.ceil(abs(span) / 90.0)))
    step = math.radians(span / pieces)
    handle = 4.0 / 3.0 * math.tan(step / 4.0) * radius
    out = []
    angle = math.radians(start_degrees)
    for _ in range(pieces):
        nxt = angle + step
        p0 = (centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle))
        p1 = (centre[0] + radius * math.cos(nxt), centre[1] + radius * math.sin(nxt))
        c1 = (p0[0] - handle * math.sin(angle), p0[1] + handle * math.cos(angle))
        c2 = (p1[0] + handle * math.sin(nxt), p1[1] - handle * math.cos(nxt))
        out.append(("C", c1, c2, p1))
        angle = nxt
    return out


def circle(centre, radius):
    return [("M", (centre[0] + radius, centre[1]))] + arc(centre, radius, 0.0, 360.0)


def flip_arrow(mirror=False):
    """Broad arrow curving over the top and down the right side (left when mirrored)."""
    radius, half, head, start, end, head_span = 0.42, 0.085, 0.2, 150.0, -25.0, 38.0
    centre = (0.0, 0.0)

    def at(r, degrees):
        a = math.radians(degrees)
        return (centre[0] + r * math.cos(a), centre[1] + r * math.sin(a))

    path = [("M", at(radius + half, start))]
    path += arc(centre, radius + half, start, end)
    path.append(("L", at(radius + head, end)))
    path.append(("L", at(radius, end - head_span)))
    path.append(("L", at(radius - head, end)))
    path.append(("L", at(radius - half, end)))
    path += arc(centre, radius - half, end, start)
    if mirror:
        path = [tuple([cmd[0]] + [(-p[0], p[1]) for p in cmd[1:]]) for cmd in path]
    return path


def moved(path, degrees):
    """`path` turned anticlockwise about the origin."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [tuple([cmd[0]] + [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in cmd[1:]]) for cmd in path]


def symbol(name):
    """[(path, colour name)] back to front."""
    if name == "GlueBottle":
        centre_y = 0.72
        pieces = [
            (polygon(rect(-0.22, -0.5, 0.22, 0.05), 0.05), "glue"),
            (polygon([(-0.22, 0.05), (0.22, 0.05), (0.09, 0.22), (-0.09, 0.22)]), "glue"),
            (polygon(rect(-0.1, 0.22, 0.1, 0.32)), "grey"),
            (polygon([(-0.06, 0.32), (0.06, 0.32), (0.0, 0.5)]), "grey"),
            # the drop leaves the nozzle along its axis, pointed end toward the tip
            (polygon([(x, 2 * centre_y - y) for x, y in drop(0.0, centre_y, 0.06)]), "glue"),
        ]
        # drawn with the nozzle pointing down to the left; turn it in InDesign to aim it
        return [(moved(path, 135.0), colour) for path, colour in pieces]
    if name in ("PhillipsBit", "RobertsonBit"):
        square = name == "RobertsonBit"
        point = 0.06 if square else 0.03
        pieces = [
            (polygon(rect(-0.11, -0.05, 0.11, 0.5)), "grey"),
            (polygon([(-0.11, -0.05), (0.11, -0.05), (point, -0.5), (-point, -0.5)]), "grey"),
            (circle((0.45, 0.28), 0.19), "white"),      # the screw head seen end on
        ]
        if square:
            pieces.append((polygon(rect(0.45 - 0.085, 0.28 - 0.085, 0.45 + 0.085, 0.28 + 0.085)), "grey"))
        else:
            pieces.append((polygon(rect(0.45 - 0.14, 0.28 - 0.025, 0.45 + 0.14, 0.28 + 0.025)), "grey"))
            pieces.append((polygon(rect(0.45 - 0.025, 0.28 - 0.14, 0.45 + 0.025, 0.28 + 0.14)), "grey"))
        return pieces
    if name == "Mallet":
        return [
            (polygon(rect(-0.3, 0.15, 0.3, 0.5), 0.04), "grey"),
            (polygon(rect(-0.42, 0.15, -0.3, 0.5), 0.04), "white"),
            (polygon(rect(0.3, 0.15, 0.42, 0.5), 0.04), "white"),
            (polygon(rect(-0.06, -0.5, 0.06, 0.15), 0.02), "white"),
        ]
    if name == "Hammer":
        head = [(0.35, 0.22), (0.35, 0.48), (-0.05, 0.48), (-0.42, 0.40), (-0.3, 0.33), (-0.42, 0.14), (-0.05, 0.22)]
        return [
            (polygon(head), "grey"),
            (polygon(rect(0.06, -0.5, 0.18, 0.22), 0.02), "white"),
        ]
    if name == "Tick":
        return [(polygon(stroke([(-0.45, 0.02), (-0.14, -0.42), (0.48, 0.46)], 0.1), 0.03), "green")]
    if name == "Cross":
        arm, half = 0.46, 0.1
        plus = [(-half, -arm), (half, -arm), (half, -half), (arm, -half), (arm, half), (half, half),
                (half, arm), (-half, arm), (-half, half), (-arm, half), (-arm, -half), (-half, -half)]
        return [(polygon(turned(plus, 45.0), 0.02), "red")]
    if name == "Flip":
        return [(flip_arrow(False), "arrow")]
    if name == "FlipLeft":
        return [(flip_arrow(True), "arrow")]
    raise ValueError(name)


# --- output ------------------------------------------------------------------------

def bezier_points(p0, c1, c2, p1, steps=12):
    out = []
    for i in range(1, steps + 1):
        t = i / float(steps)
        u = 1.0 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p1[0],
                    u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p1[1]))
    return out


def extent(pieces):
    xs, ys = [], []
    for path, _colour in pieces:
        last = None
        for cmd in path:
            points = [cmd[-1]] if cmd[0] != "C" else bezier_points(last, cmd[1], cmd[2], cmd[3])
            for x, y in points:
                xs.append(x)
                ys.append(y)
            last = cmd[-1]
    return min(xs), min(ys), max(xs), max(ys)


def layout(name):
    """(pieces, to_page, width_mm, height_mm): to_page maps a unit point to mm from
    the lower left corner of the page."""
    pieces = symbol(name)
    unit = UNIT_MM[name]
    x0, y0, x1, y1 = extent(pieces)
    pad = MARGIN_MM + OUTLINE_PT * 25.4 / 72.0 / 2.0

    def to_page(p):
        return ((p[0] - x0) * unit + pad, (p[1] - y0) * unit + pad)
    return pieces, to_page, (x1 - x0) * unit + 2 * pad, (y1 - y0) * unit + 2 * pad


def number(value):
    return "{:.3f}".format(value).rstrip("0").rstrip(".") or "0"


def write_svg(name, folder=HERE):
    pieces, to_page, width, height = layout(name)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="{0}mm" height="{1}mm" viewBox="0 0 {0} {1}">'.format(
                 number(width), number(height)),
             '  <g id="{}" stroke="rgb({},{},{})" stroke-width="{}" stroke-linejoin="round">'.format(
                 name, OUTLINE[0], OUTLINE[1], OUTLINE[2], number(OUTLINE_PT * 25.4 / 72.0))]
    for path, colour in pieces:
        parts = []
        for cmd in path:
            points = [to_page(p) for p in cmd[1:]]
            parts.append(cmd[0] + " " + " ".join("{},{}".format(number(x), number(height - y)) for x, y in points))
        lines.append('    <path d="{} Z" fill="rgb({},{},{})"/>'.format(" ".join(parts), *COLOURS[colour]))
    lines += ["  </g>", "</svg>", ""]
    path = os.path.join(folder, name + ".svg")
    with open(path, "w") as handle:
        handle.write("\n".join(lines))
    return path


def write_pdf(name, folder=HERE):
    pieces, to_page, width, height = layout(name)
    k = 72.0 / 25.4
    ops = ["{} w 1 j 1 J".format(number(OUTLINE_PT)),
           "{} {} {} RG".format(*[number(c / 255.0) for c in OUTLINE])]
    letters = {"M": "m", "L": "l", "C": "c"}
    for path, colour in pieces:
        ops.append("{} {} {} rg".format(*[number(c / 255.0) for c in COLOURS[colour]]))
        for cmd in path:
            points = [to_page(p) for p in cmd[1:]]
            ops.append(" ".join("{} {}".format(number(x * k), number(y * k)) for x, y in points) + " " + letters[cmd[0]])
        ops.append("h B")
    stream = "\n".join(ops).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {} {}] /Contents 4 0 R /Resources << >> >>".format(
            number(width * k), number(height * k)).encode("ascii"),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(index).encode("ascii") + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(data)
    data += "xref\n0 {}\n".format(len(objects) + 1).encode("ascii")
    data += b"0000000000 65535 f \n"
    for offset in offsets:
        data += "{:010d} 00000 n \n".format(offset).encode("ascii")
    data += "trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(len(objects) + 1, xref).encode("ascii")
    path = os.path.join(folder, name + ".pdf")
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def main():
    for name in sorted(UNIT_MM):
        _pieces, _to_page, width, height = layout(name)
        write_svg(name)
        write_pdf(name)
        print("{:<13} {:>5.1f} x {:>5.1f} mm".format(name, width, height))


if __name__ == "__main__":
    main()
