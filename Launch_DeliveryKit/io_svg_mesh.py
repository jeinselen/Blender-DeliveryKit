"""SVG mesh import/export using evaluated Blender geometry."""

import math
import os
import re
import xml.etree.ElementTree as ET

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Vector

from .io_common import EXPORT_BATCH_MODES, export_objects, object_export_path
from .io_svg_curve import SvgSubpath, parse_path_data, svg_number


EPS = 1.0e-8
NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
IDENTITY_2D = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
SVG_TAGS = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _numbers(text):
    return [float(value) for value in NUMBER_RE.findall(text or "")]


def _mat_mul(a, b):
    return tuple(tuple(sum(a[row][k] * b[k][col] for k in range(3)) for col in range(3)) for row in range(3))


def _mat_point(matrix, point):
    x, y = point
    return (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2], matrix[1][0] * x + matrix[1][1] * y + matrix[1][2])


def _svg_transform(text):
    result = IDENTITY_2D
    for name, body in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", text or ""):
        values = _numbers(body)
        name = name.lower()
        if name == "matrix" and len(values) >= 6:
            a, b, c, d, e, f = values[:6]
            current = ((a, c, e), (b, d, f), (0.0, 0.0, 1.0))
        elif name == "translate" and values:
            current = ((1.0, 0.0, values[0]), (0.0, 1.0, values[1] if len(values) > 1 else 0.0), (0.0, 0.0, 1.0))
        elif name == "scale" and values:
            sy = values[1] if len(values) > 1 else values[0]
            current = ((values[0], 0.0, 0.0), (0.0, sy, 0.0), (0.0, 0.0, 1.0))
        elif name == "rotate" and values:
            angle = math.radians(values[0])
            c, s = math.cos(angle), math.sin(angle)
            rotation = ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
            if len(values) >= 3:
                cx, cy = values[1:3]
                current = _mat_mul(((1.0, 0.0, cx), (0.0, 1.0, cy), (0.0, 0.0, 1.0)), _mat_mul(rotation, ((1.0, 0.0, -cx), (0.0, 1.0, -cy), (0.0, 0.0, 1.0))))
            else:
                current = rotation
        elif name == "skewx" and values:
            current = ((1.0, math.tan(math.radians(values[0])), 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        elif name == "skewy" and values:
            current = ((1.0, 0.0, 0.0), (math.tan(math.radians(values[0])), 1.0, 0.0), (0.0, 0.0, 1.0))
        else:
            continue
        result = _mat_mul(result, current)
    return result


NAMED_COLORS = {
    "black": (0.0, 0.0, 0.0), "white": (1.0, 1.0, 1.0), "red": (1.0, 0.0, 0.0),
    "green": (0.0, 0.50196, 0.0), "blue": (0.0, 0.0, 1.0), "yellow": (1.0, 1.0, 0.0),
    "cyan": (0.0, 1.0, 1.0), "aqua": (0.0, 1.0, 1.0), "magenta": (1.0, 0.0, 1.0),
    "fuchsia": (1.0, 0.0, 1.0), "gray": (0.50196, 0.50196, 0.50196),
    "grey": (0.50196, 0.50196, 0.50196), "orange": (1.0, 0.64706, 0.0),
    "purple": (0.50196, 0.0, 0.50196), "transparent": (0.0, 0.0, 0.0),
}


def _color(value, opacity=1.0):
    text = (value or "").strip().lower()
    if not text or text == "none":
        return None
    alpha = max(0.0, min(1.0, float(opacity)))
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) in {3, 4}:
            digits = "".join(char * 2 for char in digits)
        if len(digits) in {6, 8}:
            channels = [int(digits[index:index + 2], 16) / 255.0 for index in range(0, len(digits), 2)]
            if len(channels) == 4:
                alpha *= channels[3]
            return (*channels[:3], alpha)
    match = re.match(r"rgba?\((.*)\)", text)
    if match:
        parts = [part.strip() for part in match.group(1).split(",")]
        if len(parts) >= 3:
            rgb = [float(part[:-1]) / 100.0 if part.endswith("%") else float(part) / 255.0 for part in parts[:3]]
            if len(parts) > 3:
                alpha *= float(parts[3][:-1]) / 100.0 if parts[3].endswith("%") else float(parts[3])
            return (*[max(0.0, min(1.0, item)) for item in rgb], max(0.0, min(1.0, alpha)))
    if text in NAMED_COLORS:
        return (*NAMED_COLORS[text], 0.0 if text == "transparent" else alpha)
    return (0.0, 0.0, 0.0, alpha)


def _style(element, inherited):
    result = dict(inherited)
    inline = {}
    for declaration in (element.get("style") or "").split(";"):
        if ":" in declaration:
            key, value = declaration.split(":", 1)
            inline[key.strip()] = value.strip()
    for key in ("fill", "fill-opacity", "stroke", "stroke-opacity", "stroke-width", "opacity", "fill-rule", "display", "visibility"):
        if element.get(key) is not None:
            result[key] = element.get(key)
        if key in inline:
            result[key] = inline[key]
    return result


def _circle_subpath(cx, cy, rx, ry):
    k = 0.5522847498307936
    points = [(cx + rx, cy), (cx, cy + ry), (cx - rx, cy), (cx, cy - ry)]
    segments = []
    handles = [
        ((cx + rx, cy + k * ry), (cx + k * rx, cy + ry)),
        ((cx - k * rx, cy + ry), (cx - rx, cy + k * ry)),
        ((cx - rx, cy - k * ry), (cx - k * rx, cy - ry)),
        ((cx + k * rx, cy - ry), (cx + rx, cy - k * ry)),
    ]
    for index, (p1, p2) in enumerate(handles):
        segments.append((points[index], p1, p2, points[(index + 1) % 4]))
    return SvgSubpath("BEZIER", [], segments, True)


def _element_subpaths(element):
    name = _tag(element)
    if name == "path":
        paths = parse_path_data(element.get("d", ""))
        for subpath in paths:
            subpath.points = [(point[0], -point[1]) for point in subpath.points]
            subpath.segments = [tuple((point[0], -point[1]) for point in segment) for segment in subpath.segments]
        return paths
    if name in {"polygon", "polyline"}:
        values = _numbers(element.get("points", ""))
        return [SvgSubpath("POLY", [(values[index], values[index + 1]) for index in range(0, len(values) - 1, 2)], [], name == "polygon")]
    if name == "line":
        return [SvgSubpath("POLY", [(float(element.get("x1", 0)), float(element.get("y1", 0))), (float(element.get("x2", 0)), float(element.get("y2", 0)))], [], False)]
    if name == "circle":
        radius = float(element.get("r", 0))
        return [_circle_subpath(float(element.get("cx", 0)), float(element.get("cy", 0)), radius, radius)]
    if name == "ellipse":
        return [_circle_subpath(float(element.get("cx", 0)), float(element.get("cy", 0)), float(element.get("rx", 0)), float(element.get("ry", 0)))]
    if name == "rect":
        x, y = float(element.get("x", 0)), float(element.get("y", 0))
        width, height = float(element.get("width", 0)), float(element.get("height", 0))
        rx = min(abs(float(element.get("rx", element.get("ry", 0)) or 0)), width * 0.5)
        ry = min(abs(float(element.get("ry", element.get("rx", 0)) or 0)), height * 0.5)
        if rx <= EPS or ry <= EPS:
            return [SvgSubpath("POLY", [(x, y), (x + width, y), (x + width, y + height), (x, y + height)], [], True)]
        # Rounded rectangles are expressed as a path so Blender handles their fill and holes.
        d = f"M {x + rx},{y} H {x + width - rx} Q {x + width},{y} {x + width},{y + ry} V {y + height - ry} Q {x + width},{y + height} {x + width - rx},{y + height} H {x + rx} Q {x},{y + height} {x},{y + height - ry} V {y + ry} Q {x},{y} {x + rx},{y} Z"
        proxy = ET.Element("path", {"d": d})
        return _element_subpaths(proxy)
    return []


def _axis_point(point, _plane, _depth, pixels_per_unit):
    x, y = point[0] / pixels_per_unit, -point[1] / pixels_per_unit
    # Blender fills 2D curves in local XY. The evaluated vertices are mapped to
    # the requested orthogonal plane after tessellation.
    return (x, y, 0.0)


def _place_import_vertex(coordinate, plane, depth):
    if plane == "XY":
        return (coordinate.x, coordinate.y, depth)
    if plane == "YZ":
        return (depth, coordinate.x, coordinate.y)
    return (coordinate.x, depth, coordinate.y)


def _add_subpath(curve, subpath, transform, plane, depth, pixels_per_unit):
    convert = lambda point: _axis_point(_mat_point(transform, point), plane, depth, pixels_per_unit)
    if subpath.kind == "BEZIER" and subpath.segments:
        count = len(subpath.segments) if subpath.cyclic else len(subpath.segments) + 1
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(count - 1)
        spline.use_cyclic_u = subpath.cyclic
        for index, point in enumerate(spline.bezier_points):
            segment = subpath.segments[index] if index < len(subpath.segments) else subpath.segments[-1]
            point.co = convert(segment[0] if index < len(subpath.segments) else segment[3])
            point.handle_left_type = point.handle_right_type = "FREE"
        for index, segment in enumerate(subpath.segments):
            spline.bezier_points[index].handle_right = convert(segment[1])
            spline.bezier_points[(index + 1) % count].handle_left = convert(segment[2])
        return
    if len(subpath.points) >= 2:
        spline = curve.splines.new("POLY")
        spline.points.add(len(subpath.points) - 1)
        spline.use_cyclic_u = subpath.cyclic
        for point, coordinate in zip(spline.points, subpath.points):
            point.co = (*convert(coordinate), 1.0)


def import_svg_mesh(context, filepath, plane="XY", layer_offset=0.001, pixels_per_unit=100.0, resolution=12):
    root = ET.parse(filepath).getroot()
    ids = {element.get("id"): element for element in root.iter() if element.get("id")}
    default_style = {"fill": "black", "fill-opacity": "1", "stroke": "none", "stroke-opacity": "1", "stroke-width": "1", "opacity": "1", "fill-rule": "nonzero"}
    elements = []

    def walk(element, parent_transform, inherited_style, use_stack=()):
        name = _tag(element)
        style = _style(element, inherited_style)
        if style.get("display") == "none" or style.get("visibility") == "hidden":
            return
        transform = _mat_mul(parent_transform, _svg_transform(element.get("transform")))
        if name == "use":
            reference = (element.get("href") or element.get("{http://www.w3.org/1999/xlink}href") or "").lstrip("#")
            if reference and reference in ids and reference not in use_stack:
                translate = ((1.0, 0.0, float(element.get("x", 0))), (0.0, 1.0, float(element.get("y", 0))), (0.0, 0.0, 1.0))
                walk(ids[reference], _mat_mul(transform, translate), style, use_stack + (reference,))
            return
        if name in SVG_TAGS:
            elements.append((element, transform, style))
        if name not in {"defs", "symbol"}:
            for child in element:
                walk(child, transform, style, use_stack)

    walk(root, IDENTITY_2D, default_style)
    if not elements:
        raise ValueError("No supported SVG shapes were found")

    vertices, faces, face_colors = [], [], []
    for layer, (element, transform, style) in enumerate(elements):
        subpaths = _element_subpaths(element)
        if not subpaths:
            continue
        opacity = float(style.get("opacity", 1))
        fill = _color(style.get("fill"), opacity * float(style.get("fill-opacity", 1)))
        stroke = _color(style.get("stroke"), opacity * float(style.get("stroke-opacity", 1)))
        color = fill if fill is not None else stroke
        if color is None:
            continue
        curve = bpy.data.curves.new("SVG Import Element", "CURVE")
        curve.dimensions = "2D"
        curve.resolution_u = max(1, int(resolution))
        curve.render_resolution_u = max(1, int(resolution))
        curve.fill_mode = "BOTH"
        for subpath in subpaths:
            _add_subpath(curve, subpath, transform, plane, layer * layer_offset, pixels_per_unit)
        temp_obj = bpy.data.objects.new("SVG Import Element", curve)
        context.collection.objects.link(temp_obj)
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        evaluated = temp_obj.evaluated_get(depsgraph)
        temp_mesh = evaluated.to_mesh()
        base = len(vertices)
        depth = layer * layer_offset
        vertices.extend(_place_import_vertex(vertex.co, plane, depth) for vertex in temp_mesh.vertices)
        for polygon in temp_mesh.polygons:
            faces.append(tuple(base + index for index in polygon.vertices))
            face_colors.append(color)
        evaluated.to_mesh_clear()
        bpy.data.objects.remove(temp_obj, do_unlink=True)
        bpy.data.curves.remove(curve)
    if not faces:
        raise ValueError("SVG shapes did not produce any filled mesh faces")
    name = os.path.splitext(os.path.basename(filepath))[0] or "SVG Mesh"
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    color_attribute = mesh.color_attributes.new(name="Color", type="BYTE_COLOR", domain="CORNER")
    for polygon, color in zip(mesh.polygons, face_colors):
        for loop_index in polygon.loop_indices:
            color_attribute.data[loop_index].color_srgb = color
    mesh.color_attributes.active_color_index = mesh.color_attributes.find("Color")
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def _clip_near(points):
    output = []
    if not points:
        return output
    previous = points[-1]
    previous_distance = previous.z + previous.w
    for current in points:
        distance = current.z + current.w
        if distance >= 0.0:
            if previous_distance < 0.0:
                output.append(previous.lerp(current, previous_distance / (previous_distance - distance)))
            output.append(current)
        elif previous_distance >= 0.0:
            output.append(previous.lerp(current, previous_distance / (previous_distance - distance)))
        previous, previous_distance = current, distance
    return output


def _projection_matrix(context, projection, depsgraph):
    if projection == "VIEW" and context.area and context.area.type == "VIEW_3D" and context.region_data:
        return context.region_data.perspective_matrix.copy()
    if projection == "CAMERA":
        camera = context.scene.camera
        if camera is None:
            raise ValueError("The scene has no active camera")
        render = context.scene.render
        return camera.calc_matrix_camera(depsgraph, x=render.resolution_x, y=render.resolution_y, scale_x=render.pixel_aspect_x, scale_y=render.pixel_aspect_y) @ camera.matrix_world.inverted()
    if projection == "VIEW":
        raise ValueError("Current 3D View projection requires an active 3D View")
    return None


def _project_polygon(coordinates, projection, matrix):
    if matrix is not None:
        clipped = _clip_near([matrix @ coordinate.to_4d() for coordinate in coordinates])
        return [(point.x / point.w, point.y / point.w) for point in clipped if abs(point.w) > EPS]
    if projection == "YZ":
        return [(point.y, point.z) for point in coordinates]
    if projection == "XZ":
        return [(point.x, point.z) for point in coordinates]
    return [(point.x, point.y) for point in coordinates]


def _face_color(mesh, polygon):
    attributes = mesh.color_attributes
    attribute = attributes.get(attributes.active_color_name) if attributes.active_color_name else attributes.get("Color")
    if attribute is None:
        return (0.8, 0.8, 0.8, 1.0)
    if attribute.domain == "CORNER":
        values = [getattr(attribute.data[index], "color_srgb", attribute.data[index].color) for index in polygon.loop_indices]
    elif attribute.domain == "POINT":
        values = [getattr(attribute.data[index], "color_srgb", attribute.data[index].color) for index in polygon.vertices]
    else:
        values = []
    if not values:
        return (0.8, 0.8, 0.8, 1.0)
    return tuple(sum(value[channel] for value in values) / len(values) for channel in range(4))


def _disjoint_groups(mesh, uv_layer=None):
    parent = list(range(len(mesh.polygons)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    edges = {}
    for polygon in mesh.polygons:
        loops = list(polygon.loop_indices)
        for offset, loop_index in enumerate(loops):
            next_loop_index = loops[(offset + 1) % len(loops)]
            loop, next_loop = mesh.loops[loop_index], mesh.loops[next_loop_index]
            key = tuple(sorted((loop.vertex_index, next_loop.vertex_index)))
            signature = None
            if uv_layer is not None:
                a = tuple(round(value, 7) for value in uv_layer.data[loop_index].uv)
                b = tuple(round(value, 7) for value in uv_layer.data[next_loop_index].uv)
                signature = tuple(sorted((a, b)))
            if key in edges:
                other_polygon, other_signature = edges[key]
                if uv_layer is None or signature == other_signature:
                    union(polygon.index, other_polygon)
            else:
                edges[key] = (polygon.index, signature)
    groups = {}
    for polygon in mesh.polygons:
        groups.setdefault(find(polygon.index), []).append(polygon.index)
    return list(groups.values())


def _signed_area(points):
    return 0.5 * sum(points[index][0] * points[(index + 1) % len(points)][1] - points[(index + 1) % len(points)][0] * points[index][1] for index in range(len(points)))


def _point_in_polygon(point, polygon):
    """Even/odd test; boundary samples are deliberately offset by the caller."""
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > y) != (previous[1] > y):
            crossing = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _segment_parameter(point, start, delta):
    length_squared = delta[0] * delta[0] + delta[1] * delta[1]
    return 0.0 if length_squared < EPS else ((point[0] - start[0]) * delta[0] + (point[1] - start[1]) * delta[1]) / length_squared


def _union_loops(_context, polygons):
    """Compute a true planar polygon union and return its outer and hole loops.

    An edge arrangement is used instead of an optional third-party clipping
    dependency: every segment is split at intersections, then subsegments with
    union interior on only one side become the compound silhouette boundary.
    """
    polygons = [list(points) for points in polygons if len(points) >= 3 and abs(_signed_area(points)) > EPS]
    if not polygons:
        return []
    coordinates = [point for polygon in polygons for point in polygon]
    extent = max(max(point[axis] for point in coordinates) - min(point[axis] for point in coordinates) for axis in (0, 1))
    tolerance = max(EPS, extent * 1.0e-9)
    sample_offset = max(EPS * 10.0, extent * 1.0e-7)
    segments = []
    for polygon in polygons:
        for index, start in enumerate(polygon):
            end = polygon[(index + 1) % len(polygon)]
            if math.dist(start, end) > tolerance:
                segments.append((start, end, {0.0, 1.0}))

    for index, (a, b, splits_a) in enumerate(segments):
        da = (b[0] - a[0], b[1] - a[1])
        for c, d, splits_b in segments[index + 1:]:
            db = (d[0] - c[0], d[1] - c[1])
            denominator = da[0] * db[1] - da[1] * db[0]
            offset = (c[0] - a[0], c[1] - a[1])
            if abs(denominator) > tolerance:
                ta = (offset[0] * db[1] - offset[1] * db[0]) / denominator
                tb = (offset[0] * da[1] - offset[1] * da[0]) / denominator
                if -tolerance <= ta <= 1.0 + tolerance and -tolerance <= tb <= 1.0 + tolerance:
                    splits_a.add(max(0.0, min(1.0, ta)))
                    splits_b.add(max(0.0, min(1.0, tb)))
            elif abs(offset[0] * da[1] - offset[1] * da[0]) <= tolerance:
                for point in (c, d):
                    value = _segment_parameter(point, a, da)
                    if -tolerance <= value <= 1.0 + tolerance:
                        splits_a.add(max(0.0, min(1.0, value)))
                for point in (a, b):
                    value = _segment_parameter(point, c, db)
                    if -tolerance <= value <= 1.0 + tolerance:
                        splits_b.add(max(0.0, min(1.0, value)))

    boundary = {}
    for start, end, split_values in segments:
        delta = (end[0] - start[0], end[1] - start[1])
        values = sorted(split_values)
        for low, high in zip(values, values[1:]):
            if high - low <= tolerance:
                continue
            a = (start[0] + delta[0] * low, start[1] + delta[1] * low)
            b = (start[0] + delta[0] * high, start[1] + delta[1] * high)
            length = math.dist(a, b)
            normal = (-(b[1] - a[1]) / length * sample_offset, (b[0] - a[0]) / length * sample_offset)
            middle = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            left = any(_point_in_polygon((middle[0] + normal[0], middle[1] + normal[1]), polygon) for polygon in polygons)
            right = any(_point_in_polygon((middle[0] - normal[0], middle[1] - normal[1]), polygon) for polygon in polygons)
            if left == right:
                continue
            if not left:
                a, b = b, a
            key = (round(a[0] / tolerance), round(a[1] / tolerance), round(b[0] / tolerance), round(b[1] / tolerance))
            boundary[key] = (a, b)

    def point_key(point):
        return round(point[0] / tolerance), round(point[1] / tolerance)

    outgoing = {}
    for key, (start, end) in boundary.items():
        outgoing.setdefault(point_key(start), []).append((key, start, end))
    loops, used = [], set()
    for start, end in boundary.values():
        # Recover the dictionary key so coincident edge values remain unique.
        edge_key = (round(start[0] / tolerance), round(start[1] / tolerance), round(end[0] / tolerance), round(end[1] / tolerance))
        if edge_key in used:
            continue
        loop, current_start, current_end = [start], start, end
        used.add(edge_key)
        while point_key(current_end) != point_key(loop[0]):
            candidates = [item for item in outgoing.get(point_key(current_end), []) if item[0] not in used]
            if not candidates:
                break
            next_key, next_start, next_end = candidates[0]
            loop.append(current_end)
            used.add(next_key)
            current_start, current_end = next_start, next_end
            if len(loop) > len(boundary) + 1:
                break
        if point_key(current_end) == point_key(loop[0]) and len(loop) >= 3:
            loops.append(loop)
    threshold = max(EPS, extent * extent * 1.0e-10)
    return [loop for loop in loops if abs(_signed_area(loop)) > threshold]


def _rgba_hex(color):
    values = [max(0, min(255, round(channel * 255))) for channel in color]
    return "#" + "".join(f"{value:02x}" for value in values[:3]), values[3] / 255.0


def _path_data(loops, scale):
    return " ".join("M " + " L ".join(f"{svg_number(x * scale)} {svg_number(-y * scale)}" for x, y in loop) + " Z" for loop in loops if len(loop) >= 3)


def export_svg_vectors(context, filepath, objects, source="MESH", projection="XY", merge_islands=False, coordinate_scale=100.0):
    depsgraph = context.evaluated_depsgraph_get()
    projection_matrix = _projection_matrix(context, projection, depsgraph)
    shapes = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        try:
            uv_layer = mesh.uv_layers.active if source == "UV" else None
            if source == "UV" and uv_layer is None:
                continue
            projected, colors = {}, {}
            for polygon in mesh.polygons:
                if source == "UV":
                    points = [tuple(uv_layer.data[index].uv) for index in polygon.loop_indices]
                else:
                    points = _project_polygon([evaluated.matrix_world @ mesh.vertices[index].co for index in polygon.vertices], projection, projection_matrix)
                if len(points) >= 3 and abs(_signed_area(points)) > EPS:
                    projected[polygon.index] = points
                    colors[polygon.index] = _face_color(mesh, polygon)
            if merge_islands:
                for group in _disjoint_groups(mesh, uv_layer):
                    indices = [index for index in group if index in projected]
                    if indices:
                        loops = _union_loops(context, [projected[index] for index in indices])
                        if loops:
                            color = tuple(sum(colors[index][channel] for index in indices) / len(indices) for channel in range(4))
                            shapes.append((loops, color))
            else:
                shapes.extend(([points], colors[index]) for index, points in projected.items())
        finally:
            evaluated.to_mesh_clear()
    if not shapes:
        raise ValueError("No exportable evaluated mesh polygons were found")
    all_points = [point for loops, _ in shapes for loop in loops for point in loop]
    min_x, max_x = min(point[0] for point in all_points), max(point[0] for point in all_points)
    min_y, max_y = min(point[1] for point in all_points), max(point[1] for point in all_points)
    width, height = max((max_x - min_x) * coordinate_scale, 1.0), max((max_y - min_y) * coordinate_scale, 1.0)
    root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "version": "1.1", "viewBox": f"{svg_number(min_x * coordinate_scale)} {svg_number(-max_y * coordinate_scale)} {svg_number(width)} {svg_number(height)}", "width": svg_number(width), "height": svg_number(height)})
    for loops, color in shapes:
        fill, opacity = _rgba_hex(color)
        attributes = {"d": _path_data(loops, coordinate_scale), "fill": fill, "fill-rule": "evenodd", "stroke": "none"}
        if opacity < 0.999:
            attributes["fill-opacity"] = svg_number(opacity)
        ET.SubElement(root, "path", attributes)
    ET.ElementTree(root).write(filepath, encoding="utf-8", xml_declaration=True)


class IMPORT_MESH_OT_svg_vectors(bpy.types.Operator, ImportHelper):
    bl_idname = "import_mesh.svg_vectors"
    bl_label = "SVG as Mesh"
    bl_options = {"PRESET", "UNDO"}
    filename_ext = ".svg"
    filter_glob: bpy.props.StringProperty(default="*.svg", options={"HIDDEN"})
    plane: bpy.props.EnumProperty(name="Plane", items=(("XY", "XY", "Import on XY"), ("YZ", "YZ", "Import on YZ"), ("XZ", "XZ", "Import on XZ")), default="XY")
    layer_offset: bpy.props.FloatProperty(name="Layer Offset", description="Depth offset between SVG elements", default=0.001, min=0.0, subtype="DISTANCE", unit="LENGTH")
    pixels_per_unit: bpy.props.FloatProperty(name="Pixels per Blender Unit", default=100.0, min=0.0001, soft_max=1000.0)
    curve_resolution: bpy.props.IntProperty(name="Curve Resolution", default=12, min=1, soft_max=64)

    def execute(self, context):
        try:
            obj = import_svg_mesh(context, self.filepath, self.plane, self.layer_offset, self.pixels_per_unit, self.curve_resolution)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported SVG mesh: {obj.name}")
        return {"FINISHED"}


class EXPORT_MESH_OT_svg_vectors(bpy.types.Operator, ExportHelper):
    bl_idname = "export_mesh.svg_vectors"
    bl_label = "Mesh or UV as SVG"
    bl_options = {"PRESET"}
    filename_ext = ".svg"
    filter_glob: bpy.props.StringProperty(default="*.svg", options={"HIDDEN"})
    source: bpy.props.EnumProperty(name="Source", items=(("MESH", "Mesh", "Export projected evaluated meshes"), ("UV", "Active UV Map", "Export active UV maps")), default="MESH")
    projection: bpy.props.EnumProperty(name="Projection", items=(("XY", "XY (Top)", "Project on XY"), ("YZ", "YZ (Right)", "Project on YZ"), ("XZ", "XZ (Front)", "Project on XZ"), ("CAMERA", "Active Camera", "Use active camera projection"), ("VIEW", "Current 3D View", "Use current 3D View projection")), default="XY")
    merge_islands: bpy.props.BoolProperty(name="Merge Islands", description="Export the 2D union silhouette of every mesh or UV island", default=False)
    coordinate_scale: bpy.props.FloatProperty(name="SVG Units per Blender Unit", default=100.0, min=0.0001, soft_max=1000.0)
    batch_mode: bpy.props.EnumProperty(name="Batch Mode", items=EXPORT_BATCH_MODES, default="OFF")
    use_selection: bpy.props.BoolProperty(name="Selected Objects", default=True)

    def invoke(self, context, event):
        if context.area and context.area.type == "VIEW_3D":
            self.projection = "VIEW"
        return ExportHelper.invoke(self, context, event)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "source")
        if self.source == "MESH":
            layout.prop(self, "projection")
        layout.prop(self, "merge_islands")
        layout.prop(self, "coordinate_scale")
        layout.prop(self, "batch_mode")
        layout.prop(self, "use_selection")

    def execute(self, context):
        objects = export_objects(context, {"MESH"}, use_selection=self.use_selection)
        if not objects:
            self.report({"ERROR"}, "No mesh objects were found for export")
            return {"CANCELLED"}
        try:
            if self.batch_mode == "OFF":
                export_svg_vectors(context, self.filepath, objects, self.source, self.projection, self.merge_islands, self.coordinate_scale)
                count = 1
            else:
                count = 0
                for obj in objects:
                    export_svg_vectors(context, object_export_path(self.filepath, obj, self.filename_ext), [obj], self.source, self.projection, self.merge_islands, self.coordinate_scale)
                    count += 1
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {count} SVG file(s)")
        return {"FINISHED"}


classes = (IMPORT_MESH_OT_svg_vectors, EXPORT_MESH_OT_svg_vectors)


def import_menu(self, context):
    self.layout.operator(IMPORT_MESH_OT_svg_vectors.bl_idname, text="Scalable Vector Graphics as Mesh (.svg)")


def export_menu(self, context):
    self.layout.operator(EXPORT_MESH_OT_svg_vectors.bl_idname, text="Mesh or UV Layout (.svg)")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(import_menu)
    bpy.types.TOPBAR_MT_file_export.append(export_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(export_menu)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
