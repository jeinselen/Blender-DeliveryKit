import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Matrix, Vector

try:
    from .io_common import EXPORT_BATCH_MODES, export_objects, object_export_path
except ImportError:
    from io_common import EXPORT_BATCH_MODES, export_objects, object_export_path


EPS = 1.0e-9


def vadd(a, b):
    return tuple(x + y for x, y in zip(a, b))


def vsub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def vmul(a, s):
    return tuple(x * s for x in a)


def vdot(a, b):
    return sum(x * y for x, y in zip(a, b))


def vlen(a):
    return math.sqrt(max(0.0, vdot(a, a)))


def vnorm(a):
    length = vlen(a)
    if length < EPS:
        return tuple(0.0 for _ in a)
    return vmul(a, 1.0 / length)


def vlerp(a, b, t):
    return tuple((1.0 - t) * x + t * y for x, y in zip(a, b))


def is_same_point(a, b, eps=1.0e-7):
    return vlen(vsub(a, b)) <= eps


def bezier_point(p0, p1, p2, p3, t):
    u = 1.0 - t
    return vadd(
        vadd(vmul(p0, u * u * u), vmul(p1, 3.0 * u * u * t)),
        vadd(vmul(p2, 3.0 * u * t * t), vmul(p3, t * t * t)),
    )


def chord_parameters(points):
    distances = [0.0]
    total = 0.0
    for i in range(1, len(points)):
        total += vlen(vsub(points[i], points[i - 1]))
        distances.append(total)
    if total < EPS:
        return [i / max(1, len(points) - 1) for i in range(len(points))]
    return [d / total for d in distances]


def generate_bezier(points, params, left_tangent, right_tangent):
    p0 = points[0]
    p3 = points[-1]
    c00 = c01 = c11 = x0 = x1 = 0.0

    for point, u in zip(points, params):
        b0 = (1.0 - u) ** 3
        b1 = 3.0 * u * (1.0 - u) ** 2
        b2 = 3.0 * u * u * (1.0 - u)
        b3 = u ** 3
        a1 = vmul(left_tangent, b1)
        a2 = vmul(right_tangent, b2)
        tmp = vsub(point, vadd(vmul(p0, b0 + b1), vmul(p3, b2 + b3)))
        c00 += vdot(a1, a1)
        c01 += vdot(a1, a2)
        c11 += vdot(a2, a2)
        x0 += vdot(a1, tmp)
        x1 += vdot(a2, tmp)

    det = c00 * c11 - c01 * c01
    alpha_l = alpha_r = 0.0
    if abs(det) > EPS:
        alpha_l = (x0 * c11 - x1 * c01) / det
        alpha_r = (c00 * x1 - c01 * x0) / det

    seg_len = vlen(vsub(p3, p0))
    if alpha_l < EPS or alpha_r < EPS:
        alpha_l = alpha_r = seg_len / 3.0

    return (p0, vadd(p0, vmul(left_tangent, alpha_l)), vadd(p3, vmul(right_tangent, alpha_r)), p3)


def max_bezier_error(points, curve, params):
    max_error = -1.0
    split = len(points) // 2
    for i in range(1, len(points) - 1):
        error = vlen(vsub(bezier_point(*curve, params[i]), points[i]))
        if error > max_error:
            max_error = error
            split = i
    return max_error, split


def fit_cubic_recursive(points, left_tangent, right_tangent, tolerance, out_segments, depth=0):
    if len(points) == 2:
        dist = vlen(vsub(points[1], points[0])) / 3.0
        out_segments.append((points[0], vadd(points[0], vmul(left_tangent, dist)), vadd(points[1], vmul(right_tangent, dist)), points[1]))
        return

    params = chord_parameters(points)
    curve = generate_bezier(points, params, left_tangent, right_tangent)
    error, split = max_bezier_error(points, curve, params)
    if error <= tolerance or depth >= 24:
        out_segments.append(curve)
        return

    center = vnorm(vsub(points[split + 1], points[split - 1]))
    if vlen(center) < EPS:
        center = left_tangent
    fit_cubic_recursive(points[: split + 1], left_tangent, vmul(center, -1.0), tolerance, out_segments, depth + 1)
    fit_cubic_recursive(points[split:], center, right_tangent, tolerance, out_segments, depth + 1)


def fit_cubic(points, tolerance=0.01, cyclic=False):
    clean = []
    for p in points:
        if not clean or not is_same_point(clean[-1], p):
            clean.append(tuple(float(v) for v in p))
    if len(clean) < 2:
        return []
    if cyclic and not is_same_point(clean[0], clean[-1]):
        clean.append(clean[0])

    left = vnorm(vsub(clean[1], clean[0]))
    right = vnorm(vsub(clean[-2], clean[-1]))
    segments = []
    fit_cubic_recursive(clean, left, right, max(tolerance, 1.0e-5), segments)
    return segments


def nurbs_point_weight(point):
    return float(getattr(point, "weight", point.co[3] if len(point.co) > 3 else 1.0))


def spline_points(spline, matrix=None, dims=3):
    result = []
    for p in spline.points:
        co = Vector((p.co[0], p.co[1], p.co[2]))
        if matrix is not None:
            co = matrix @ co
        result.append((tuple(co[:dims]), nurbs_point_weight(p)))
    return result


def make_knot_vector(count, degree, endpoint=False, cyclic=False):
    if cyclic:
        total = count + degree
        return [float(i) for i in range(total + degree + 1)], float(degree), float(count + degree)
    if endpoint:
        interior = max(0, count - degree - 1)
        return [0.0] * (degree + 1) + [float(i + 1) for i in range(interior)] + [float(interior + 1)] * (degree + 1), 0.0, float(interior + 1)
    knots = [float(i) for i in range(count + degree + 1)]
    return knots, float(degree), float(count)


def deboor_rational(control, degree, knots, u):
    n = len(control) - 1
    if u >= knots[n + 1]:
        span = n
    else:
        span = degree
        for i in range(degree, n + 1):
            if knots[i] <= u < knots[i + 1]:
                span = i
                break

    d = []
    for j in range(degree + 1):
        point, weight = control[span - degree + j]
        d.append([point[k] * weight for k in range(len(point))] + [weight])

    for r in range(1, degree + 1):
        for j in range(degree, r - 1, -1):
            i = span - degree + j
            denom = knots[i + degree + 1 - r] - knots[i]
            alpha = 0.0 if abs(denom) < EPS else (u - knots[i]) / denom
            d[j] = [(1.0 - alpha) * d[j - 1][k] + alpha * d[j][k] for k in range(len(d[j]))]

    w = d[degree][-1]
    if abs(w) < EPS:
        return tuple(d[degree][:-1])
    return tuple(v / w for v in d[degree][:-1])


def evaluate_nurbs_spline(spline, matrix=None, dims=3, samples=None):
    control = spline_points(spline, matrix, dims)
    count = len(control)
    if count < 2:
        return []
    degree = max(1, min(int(spline.order_u) - 1, count - 1))
    if spline.use_cyclic_u:
        control = control + control[:degree]
    knots, start, end = make_knot_vector(count, degree, bool(spline.use_endpoint_u), bool(spline.use_cyclic_u))
    sample_count = samples or max(24, count * max(8, int(spline.order_u) * 6))
    pts = []
    for i in range(sample_count + 1):
        u = start + (end - start) * (i / sample_count)
        pts.append(deboor_rational(control, degree, knots, u))
    return pts


def all_weights_equal(spline):
    if not spline.points:
        return True
    first = nurbs_point_weight(spline.points[0])
    return all(abs(nurbs_point_weight(p) - first) < 1.0e-6 for p in spline.points)


def nurbs_to_bezier_segments(spline, matrix=None, dims=3, tolerance=0.01):
    direct_possible = int(spline.order_u) < 4 and all_weights_equal(spline)
    samples = evaluate_nurbs_spline(spline, matrix, dims)
    tol = tolerance * (0.25 if direct_possible else 1.0)
    return fit_cubic(samples, tol, bool(spline.use_cyclic_u)), bool(spline.use_cyclic_u)


def bezier_segments_from_spline(spline, matrix=None, dims=3):
    points = spline.bezier_points
    if not points:
        return [], False
    total = len(points) if spline.use_cyclic_u else len(points) - 1
    segments = []
    for i in range(total):
        a = points[i]
        b = points[(i + 1) % len(points)]
        coords = [a.co, a.handle_right, b.handle_left, b.co]
        converted = []
        for co in coords:
            v = Vector((co.x, co.y, co.z))
            if matrix is not None:
                v = matrix @ v
            converted.append(tuple(v[:dims]))
        segments.append(tuple(converted))
    return segments, bool(spline.use_cyclic_u)


def poly_points_from_spline(spline, matrix=None, dims=3):
    points = []
    for p in spline.points:
        v = Vector((p.co[0], p.co[1], p.co[2]))
        if matrix is not None:
            v = matrix @ v
        points.append(tuple(v[:dims]))
    return points, bool(spline.use_cyclic_u)


def add_bezier_spline(curve, segments, cyclic=False):
    if not segments:
        return None
    point_count = len(segments) if cyclic else len(segments) + 1
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(point_count - 1)
    spline.use_cyclic_u = cyclic
    for i, bp in enumerate(spline.bezier_points):
        bp.handle_left_type = "FREE"
        bp.handle_right_type = "FREE"
        bp.co = Vector(segments[i][0] if i < len(segments) else segments[-1][3])
    for i, seg in enumerate(segments):
        spline.bezier_points[i].handle_right = Vector(seg[1])
        spline.bezier_points[(i + 1) % point_count].handle_left = Vector(seg[2])
    return spline


def add_poly_spline(curve, points, cyclic=False):
    if len(points) < 2:
        return None
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    spline.use_cyclic_u = cyclic
    for p, co in zip(spline.points, points):
        p.co = (co[0], co[1], co[2] if len(co) > 2 else 0.0, 1.0)
    return spline


def add_nurbs_segment(curve, segment):
    spline = curve.splines.new("NURBS")
    spline.points.add(3)
    spline.order_u = 4
    spline.use_endpoint_u = True
    for point, co in zip(spline.points, segment):
        point.co = (co[0], co[1], co[2] if len(co) > 2 else 0.0, 1.0)
        if hasattr(point, "weight"):
            point.weight = 1.0
    return spline


def active_curve_objects(context):
    curves = [ob for ob in context.selected_objects if ob.type == "CURVE"]
    if context.object and context.object.type == "CURVE" and context.object not in curves:
        curves.append(context.object)
    return curves


class CURVE_OT_derive_bezier_from_nurbs(bpy.types.Operator):
    bl_idname = "curve.derive_bezier_from_nurbs"
    bl_label = "Derive Bezier from NURBS"
    bl_description = "Replace NURBS splines with sparse Bezier splines while preserving the evaluated curve shape"
    bl_options = {"REGISTER", "UNDO"}

    tolerance: bpy.props.FloatProperty(
        name="Fit Tolerance",
        description="Maximum fitting error in Blender units",
        default=0.01,
        min=0.0001,
        soft_max=1.0,
        precision=4,
    )

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.type == "CURVE")

    def execute(self, context):
        original_mode = context.object.mode
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        converted = 0
        for obj in active_curve_objects(context):
            curve = obj.data
            existing = list(curve.splines)
            for spline in existing:
                if spline.type != "NURBS":
                    continue
                segments, cyclic = nurbs_to_bezier_segments(spline, None, 3, self.tolerance)
                curve.splines.remove(spline)
                add_bezier_spline(curve, segments, cyclic)
                converted += 1
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=original_mode)
        self.report({"INFO"}, f"Derived {converted} Bezier spline(s) from NURBS")
        return {"FINISHED"}


class CURVE_OT_derive_nurbs_from_bezier(bpy.types.Operator):
    bl_idname = "curve.derive_nurbs_from_bezier"
    bl_label = "Derive NURBS from Bezier"
    bl_description = "Replace Bezier splines with exact cubic NURBS segments"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.type == "CURVE")

    def execute(self, context):
        original_mode = context.object.mode
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        converted = 0
        for obj in active_curve_objects(context):
            curve = obj.data
            existing = list(curve.splines)
            for spline in existing:
                if spline.type != "BEZIER":
                    continue
                segments, _cyclic = bezier_segments_from_spline(spline, None, 3)
                curve.splines.remove(spline)
                for segment in segments:
                    add_nurbs_segment(curve, segment)
                    converted += 1
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=original_mode)
        self.report({"INFO"}, f"Derived {converted} NURBS segment(s) from Bezier")
        return {"FINISHED"}


def svg_number(v):
    if abs(v) < 1.0e-9:
        v = 0.0
    return f"{v:.6g}"


def svg_xy(point, scale=1.0):
    return point[0] * scale, -point[1] * scale


def path_from_poly(points, cyclic=False, scale=1.0):
    if not points:
        return ""
    x, y = svg_xy(points[0], scale)
    parts = [f"M {svg_number(x)} {svg_number(y)}"]
    for point in points[1:]:
        x, y = svg_xy(point, scale)
        parts.append(f"L {svg_number(x)} {svg_number(y)}")
    if cyclic:
        parts.append("Z")
    return " ".join(parts)


def path_from_beziers(segments, cyclic=False, scale=1.0):
    if not segments:
        return ""
    x, y = svg_xy(segments[0][0], scale)
    parts = [f"M {svg_number(x)} {svg_number(y)}"]
    for p0, p1, p2, p3 in segments:
        x1, y1 = svg_xy(p1, scale)
        x2, y2 = svg_xy(p2, scale)
        x3, y3 = svg_xy(p3, scale)
        parts.append(f"C {svg_number(x1)} {svg_number(y1)} {svg_number(x2)} {svg_number(y2)} {svg_number(x3)} {svg_number(y3)}")
    if cyclic:
        parts.append("Z")
    return " ".join(parts)


def export_svg(filepath, objects, tolerance=0.01, coordinate_scale=100.0, view_box_mode="SCENE_ORIGIN"):
    paths = []
    bounds = []
    coordinate_scale = max(float(coordinate_scale), EPS)
    for obj in objects:
        if obj.type != "CURVE":
            continue
        matrix = obj.matrix_world
        for spline in obj.data.splines:
            if spline.type == "BEZIER":
                segments, cyclic = bezier_segments_from_spline(spline, matrix, 3)
                d = path_from_beziers(segments, cyclic, coordinate_scale)
                pts = [p for seg in segments for p in (seg[0], seg[1], seg[2], seg[3])]
            elif spline.type == "POLY":
                pts, cyclic = poly_points_from_spline(spline, matrix, 3)
                d = path_from_poly(pts, cyclic, coordinate_scale)
            elif spline.type == "NURBS":
                segments, cyclic = nurbs_to_bezier_segments(spline, matrix, 3, tolerance)
                d = path_from_beziers(segments, cyclic, coordinate_scale)
                pts = [p for seg in segments for p in (seg[0], seg[1], seg[2], seg[3])]
            else:
                continue
            if d:
                paths.append(d)
                bounds.extend(svg_xy(p, coordinate_scale) for p in pts)

    if not paths:
        raise ValueError("No curve splines were found to export")

    min_x = min(p[0] for p in bounds)
    min_y = min(p[1] for p in bounds)
    max_x = max(p[0] for p in bounds)
    max_y = max(p[1] for p in bounds)
    if view_box_mode == "SCENE_ORIGIN":
        min_x = min(min_x, 0.0)
        min_y = min(min_y, 0.0)
        max_x = max(max_x, 0.0)
        max_y = max(max_y, 0.0)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    root = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "version": "1.1",
        "viewBox": f"{svg_number(min_x)} {svg_number(min_y)} {svg_number(width)} {svg_number(height)}",
        "width": svg_number(width),
        "height": svg_number(height),
    })
    for d in paths:
        ET.SubElement(root, "path", {"d": d, "fill": "none", "stroke": "black", "stroke-width": "1"})
    ET.ElementTree(root).write(filepath, encoding="utf-8", xml_declaration=True)


class EXPORT_CURVE_OT_svg_bezier_nurbs(bpy.types.Operator, ExportHelper):
    bl_idname = "export_curve.svg_bezier_nurbs"
    bl_label = "NURBS/Bezier Curves as SVG"
    bl_options = {"PRESET"}

    filename_ext = ".svg"
    filter_glob: bpy.props.StringProperty(default="*.svg", options={"HIDDEN"})
    batch_mode: bpy.props.EnumProperty(
        name="Batch Mode",
        description="How multiple resolved curve objects are written",
        items=EXPORT_BATCH_MODES,
        default="OFF",
    )
    use_selection: bpy.props.BoolProperty(
        name="Selected Objects",
        description="Export selected curve objects only",
        default=True,
    )
    use_active_collection: bpy.props.BoolProperty(
        name="Active Collection",
        description="Export curve objects from the active collection",
        default=False,
    )
    collection: bpy.props.StringProperty(
        name="Collection",
        description="Export curve objects from this collection when set",
        default="",
    )
    tolerance: bpy.props.FloatProperty(
        name="NURBS Fit Tolerance",
        default=0.1,
        min=0.0001,
        max=1.0,
        precision=4
    )
    coordinate_scale: bpy.props.FloatProperty(
        name="Coordinate Scale",
        description="SVG units per Blender unit",
        default=100.0,
        min=0.0001,
        soft_max=1000.0,
        precision=3,
    )
    view_box_mode: bpy.props.EnumProperty(
        name="ViewBox Mode",
        description="How SVG document bounds are calculated",
        items=(
            ("SCENE_ORIGIN", "Scene Origin", "Keep Blender scene origin inside the SVG viewBox"),
            ("BOUNDS", "Curve Bounds", "Use tight bounds around exported curves"),
        ),
        default="SCENE_ORIGIN",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "batch_mode")
        layout.prop(self, "use_selection")
        layout.prop(self, "use_active_collection")
        layout.prop_search(self, "collection", bpy.data, "collections")
        layout.prop(self, "tolerance")
        layout.prop(self, "coordinate_scale")
        layout.prop(self, "view_box_mode")

    def execute(self, context):
        objects = export_objects(
            context,
            {"CURVE"},
            use_selection=self.use_selection,
            use_active_collection=self.use_active_collection,
            collection=self.collection,
        )
        if not objects:
            self.report({"ERROR"}, "No curve objects were found for export")
            return {"CANCELLED"}
        try:
            if self.batch_mode == "OFF":
                export_svg(self.filepath, objects, self.tolerance, self.coordinate_scale, self.view_box_mode)
                export_count = 1
            else:
                export_count = 0
                for obj in objects:
                    output_path = object_export_path(self.filepath, obj, self.filename_ext)
                    export_svg(output_path, [obj], self.tolerance, self.coordinate_scale, self.view_box_mode)
                    export_count += 1
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {export_count} SVG file(s)")
        return {"FINISHED"}


TOKEN_RE = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


@dataclass
class SvgSubpath:
    kind: str
    points: list
    segments: list
    cyclic: bool = False


def parse_float(tokens, index):
    return float(tokens[index]), index + 1


def svg_to_blender(p):
    return (float(p[0]), -float(p[1]), 0.0)


def reflect(point, around):
    return (2.0 * around[0] - point[0], 2.0 * around[1] - point[1])


def parse_path_data(d):
    tokens = TOKEN_RE.findall(d.replace(",", " "))
    paths = []
    i = 0
    cmd = None
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    last_cubic = None
    last_quad = None
    sub = None

    def close_subpath():
        nonlocal sub, current
        if sub and (sub.points or sub.segments):
            if sub.cyclic and sub.kind == "BEZIER" and sub.segments and not is_same_point(svg_to_blender(current), svg_to_blender(start)):
                p0 = svg_to_blender(current)
                p3 = svg_to_blender(start)
                sub.segments.append((p0, vlerp(p0, p3, 1 / 3), vlerp(p0, p3, 2 / 3), p3))
            paths.append(sub)
        sub = None

    def promote_to_bezier():
        if not sub or sub.kind == "BEZIER":
            return
        pts = sub.points
        sub.kind = "BEZIER"
        sub.segments = []
        for a, b in zip(pts, pts[1:]):
            sub.segments.append((a, vlerp(a, b, 1 / 3), vlerp(a, b, 2 / 3), b))

    while i < len(tokens):
        if re.match(r"^[A-Za-z]$", tokens[i]):
            cmd = tokens[i]
            i += 1
        if cmd is None:
            break
        absolute = cmd.isupper()
        c = cmd.upper()
        if c == "Z":
            if sub:
                sub.cyclic = True
            current = start
            close_subpath()
            cmd = None
            last_cubic = last_quad = None
            continue

        def next_point():
            nonlocal i
            x, i2 = parse_float(tokens, i)
            y, i3 = parse_float(tokens, i2)
            i = i3
            if not absolute:
                return (current[0] + x, current[1] + y)
            return (x, y)

        if c == "M":
            close_subpath()
            current = next_point()
            start = current
            sub = SvgSubpath("POLY", [svg_to_blender(current)], [])
            cmd = "L" if absolute else "l"
            last_cubic = last_quad = None
            continue
        if sub is None:
            sub = SvgSubpath("POLY", [svg_to_blender(current)], [])
        if c in {"L", "H", "V"}:
            while i < len(tokens) and not re.match(r"^[A-Za-z]$", tokens[i]):
                if c == "L":
                    target = next_point()
                elif c == "H":
                    x, i = parse_float(tokens, i)
                    target = (x, current[1]) if absolute else (current[0] + x, current[1])
                else:
                    y, i = parse_float(tokens, i)
                    target = (current[0], y) if absolute else (current[0], current[1] + y)
                if sub.kind == "POLY":
                    sub.points.append(svg_to_blender(target))
                else:
                    p0 = svg_to_blender(current)
                    p3 = svg_to_blender(target)
                    sub.segments.append((p0, vlerp(p0, p3, 1 / 3), vlerp(p0, p3, 2 / 3), p3))
                current = target
            last_cubic = last_quad = None
            continue
        if c in {"C", "S", "Q", "T"}:
            if sub.kind == "POLY":
                promote_to_bezier()
            while i < len(tokens) and not re.match(r"^[A-Za-z]$", tokens[i]):
                if c == "C":
                    c1 = next_point()
                    c2 = next_point()
                    target = next_point()
                    last_cubic = c2
                    last_quad = None
                elif c == "S":
                    c1 = reflect(last_cubic, current) if last_cubic else current
                    c2 = next_point()
                    target = next_point()
                    last_cubic = c2
                    last_quad = None
                else:
                    q1 = reflect(last_quad, current) if c == "T" and last_quad else next_point()
                    target = next_point()
                    c1 = (current[0] + (2.0 / 3.0) * (q1[0] - current[0]), current[1] + (2.0 / 3.0) * (q1[1] - current[1]))
                    c2 = (target[0] + (2.0 / 3.0) * (q1[0] - target[0]), target[1] + (2.0 / 3.0) * (q1[1] - target[1]))
                    last_quad = q1
                    last_cubic = None
                sub.segments.append(tuple(svg_to_blender(p) for p in (current, c1, c2, target)))
                current = target
            continue
        if c == "A":
            raise ValueError("SVG arc commands are not supported; convert arcs to paths first")
    close_subpath()
    return paths


def parse_points_attribute(text):
    nums = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", text or "")]
    return [svg_to_blender((nums[i], nums[i + 1])) for i in range(0, len(nums) - 1, 2)]


def import_svg(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    curve = bpy.data.curves.new(os.path.splitext(os.path.basename(filepath))[0] or "SVG Curves", "CURVE")
    curve.dimensions = "2D"
    curve.resolution_u = 24

    def local_name(element):
        return element.tag.rsplit("}", 1)[-1]

    imported = 0
    for elem in root.iter():
        name = local_name(elem)
        if name == "path" and elem.get("d"):
            for sub in parse_path_data(elem.get("d")):
                if sub.kind == "POLY":
                    add_poly_spline(curve, sub.points, sub.cyclic)
                else:
                    add_bezier_spline(curve, sub.segments, sub.cyclic)
                imported += 1
        elif name in {"polyline", "polygon"}:
            pts = parse_points_attribute(elem.get("points", ""))
            add_poly_spline(curve, pts, name == "polygon")
            imported += 1
        elif name == "line":
            pts = [svg_to_blender((elem.get("x1", 0), elem.get("y1", 0))), svg_to_blender((elem.get("x2", 0), elem.get("y2", 0)))]
            add_poly_spline(curve, pts, False)
            imported += 1

    if imported == 0:
        raise ValueError("No supported SVG path, line, polyline, or polygon elements found")

    obj = bpy.data.objects.new(curve.name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


class IMPORT_CURVE_OT_svg_bezier_nurbs(bpy.types.Operator, ImportHelper):
    bl_idname = "import_curve.svg_bezier_nurbs"
    bl_label = "SVG as Blender Curves"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".svg"
    filter_glob: bpy.props.StringProperty(default="*.svg", options={"HIDDEN"})

    def execute(self, context):
        try:
            obj = import_svg(self.filepath)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported SVG curve object: {obj.name}")
        return {"FINISHED"}


classes = (
    CURVE_OT_derive_bezier_from_nurbs,
    CURVE_OT_derive_nurbs_from_bezier,
    EXPORT_CURVE_OT_svg_bezier_nurbs,
    IMPORT_CURVE_OT_svg_bezier_nurbs,
)


def curve_edit_menu(self, context):
    self.layout.separator()
    self.layout.operator(CURVE_OT_derive_bezier_from_nurbs.bl_idname)
    self.layout.operator(CURVE_OT_derive_nurbs_from_bezier.bl_idname)


def export_menu(self, context):
    self.layout.operator(EXPORT_CURVE_OT_svg_bezier_nurbs.bl_idname, text="NURBS/Bezier Curves (.svg)")


def import_menu(self, context):
    self.layout.operator(IMPORT_CURVE_OT_svg_bezier_nurbs.bl_idname, text="SVG as Blender Curves (.svg)")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_edit_curve.append(curve_edit_menu)
    bpy.types.TOPBAR_MT_file_export.append(export_menu)
    bpy.types.TOPBAR_MT_file_import.append(import_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(import_menu)
    bpy.types.TOPBAR_MT_file_export.remove(export_menu)
    bpy.types.VIEW3D_MT_edit_curve.remove(curve_edit_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
