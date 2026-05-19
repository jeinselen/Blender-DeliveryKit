from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

try:
    from .io_common import EXPORT_BATCH_MODES, export_objects, object_export_path
except ImportError:
    from io_common import EXPORT_BATCH_MODES, export_objects, object_export_path

DEFAULT_OBJECT_NAME = "SplineMakerCurves"
DEFAULT_PROJECT_VERSION = 1
DEFAULT_CURVE_SMOOTHNESS = 0.5
DEFAULT_ACTION_AREA_SIZE = 0.1
DEFAULT_RESOLUTION_U = 8
DEFAULT_ORDER_U = 4
MIN_POINT_COUNT = 2

PROP_MARKER = "spline_maker_project"
PROP_PROJECT_NAME = "spline_maker_project_name"
PROP_SOURCE_PATH = "spline_maker_source_path"
PROP_VERSION = "spline_maker_version"
PROP_CURVE_SMOOTHNESS = "spline_maker_curve_smoothness"
PROP_ACTION_LEFT = "spline_maker_action_area_left"
PROP_ACTION_RIGHT = "spline_maker_action_area_right"


def spline_to_blender_coords(x: float, y: float, z: float) -> tuple[float, float, float]:
    return float(x), -float(z), float(y)


def blender_to_spline_coords(x: float, y: float, z: float) -> tuple[float, float, float]:
    return float(x), float(z), -float(y)


@dataclass
class SplineMakerPoint:
    x: float
    y: float
    z: float
    size: float = DEFAULT_ACTION_AREA_SIZE
    weight: float = 1.0


@dataclass
class SplineMakerSpline:
    points: list[SplineMakerPoint] = field(default_factory=list)
    cyclic: bool = False
    order_u: int = DEFAULT_ORDER_U
    resolution_u: int = DEFAULT_RESOLUTION_U


@dataclass
class SplineMakerProject:
    project_name: str = ""
    source_path: str = ""
    version: int = DEFAULT_PROJECT_VERSION
    curve_smoothness: float = DEFAULT_CURVE_SMOOTHNESS
    action_area_left: float = DEFAULT_ACTION_AREA_SIZE
    action_area_right: float = DEFAULT_ACTION_AREA_SIZE
    splines: list[SplineMakerSpline] = field(default_factory=list)


def clamp_order(order_u: int, point_count: int) -> int:
    if point_count <= 0:
        return MIN_POINT_COUNT
    return max(MIN_POINT_COUNT, min(int(order_u), int(point_count)))


def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def load_project(filepath: str) -> tuple[SplineMakerProject, list[str]]:
    path = Path(filepath)
    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"JSON file not found: {filepath}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read JSON file: {filepath}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON parse error in {filepath}: {exc}") from exc
    
    if not isinstance(raw_data, dict):
        raise ValueError("SplineMaker JSON root must be an object")
    
    warnings: list[str] = []
    project = SplineMakerProject(
        project_name=path.stem,
        source_path=str(path),
        version=max(1, _coerce_int(raw_data.get("version"), DEFAULT_PROJECT_VERSION)),
        curve_smoothness=_coerce_float(
            raw_data.get("curve_smoothness"),
            DEFAULT_CURVE_SMOOTHNESS,
        ),
    )
    
    action_area_sizes = raw_data.get("action_area_sizes", {})
    if isinstance(action_area_sizes, dict):
        project.action_area_left = max(
            0.001,
            _coerce_float(action_area_sizes.get("left"), DEFAULT_ACTION_AREA_SIZE),
        )
        project.action_area_right = max(
            0.001,
            _coerce_float(action_area_sizes.get("right"), DEFAULT_ACTION_AREA_SIZE),
        )
    else:
        warnings.append("action_area_sizes is not an object; default sizes were used")
        project.action_area_left = DEFAULT_ACTION_AREA_SIZE
        project.action_area_right = DEFAULT_ACTION_AREA_SIZE
    
    splines_data = raw_data.get("splines", [])
    if not isinstance(splines_data, list):
        raise ValueError("SplineMaker JSON field 'splines' must be an array")
    
    for spline_index, spline_data in enumerate(splines_data):
        if not isinstance(spline_data, dict):
            warnings.append(f"Spline {spline_index} is not an object and was skipped")
            continue
        
        points_data = spline_data.get("points", [])
        if not isinstance(points_data, list):
            warnings.append(f"Spline {spline_index} points are not an array and were skipped")
            continue
        
        points: list[SplineMakerPoint] = []
        for point_index, point_data in enumerate(points_data):
            if not isinstance(point_data, dict):
                warnings.append(
                    f"Spline {spline_index} point {point_index} is not an object and was skipped"
                )
                continue
            
            points.append(
                SplineMakerPoint(
                    x=_coerce_float(point_data.get("x"), 0.0),
                    y=_coerce_float(point_data.get("y"), 0.0),
                    z=_coerce_float(point_data.get("z"), 0.0),
                    size=max(0.001, _coerce_float(point_data.get("size"), DEFAULT_ACTION_AREA_SIZE)),
                    weight=max(0.001, _coerce_float(point_data.get("weight"), 1.0)),
                )
            )
        
        if len(points) < MIN_POINT_COUNT:
            warnings.append(
                f"Spline {spline_index} has fewer than {MIN_POINT_COUNT} valid points and was skipped"
            )
            continue
        
        project.splines.append(
            SplineMakerSpline(
                points=points,
                cyclic=_coerce_bool(spline_data.get("cyclic"), False),
                order_u=clamp_order(
                    _coerce_int(spline_data.get("order_u"), DEFAULT_ORDER_U),
                    len(points),
                ),
                resolution_u=max(
                    1,
                    _coerce_int(spline_data.get("resolution_u"), DEFAULT_RESOLUTION_U),
                ),
            )
        )
    
    return project, warnings


def save_project(filepath: str, project: SplineMakerProject) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": max(1, int(project.version)),
        "curve_smoothness": float(project.curve_smoothness),
        "splines": [
            {
                "cyclic": bool(spline.cyclic),
                "order_u": clamp_order(spline.order_u, len(spline.points)),
                "points": [
                    {
                        "x": float(point.x),
                        "y": float(point.y),
                        "z": float(point.z),
                        "size": max(0.001, float(point.size)),
                        "weight": max(0.001, float(point.weight)),
                    }
                    for point in spline.points
                ],
            }
            for spline in project.splines
            if len(spline.points) >= MIN_POINT_COUNT
        ],
        "action_area_sizes": {
            "left": max(0.001, float(project.action_area_left)),
            "right": max(0.001, float(project.action_area_right)),
        },
    }
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def _ensure_single_user_curve_data(curve_object: bpy.types.Object) -> bpy.types.Curve:
    curve_data = curve_object.data
    if curve_data.users > 1:
        curve_object.data = curve_data.copy()
        curve_data = curve_object.data
    return curve_data


def clear_curve_splines(curve_data: bpy.types.Curve) -> None:
    while curve_data.splines:
        last_index = len(curve_data.splines) - 1
        curve_data.splines.remove(curve_data.splines[last_index])


def _set_idprop_value(id_owner, key: str, value, description: str) -> None:
    id_owner[key] = value
    ui_manager = getattr(id_owner, "id_properties_ui", None)
    if callable(ui_manager):
        ui_manager(key).update(description=description)


def store_project_metadata(curve_object: bpy.types.Object, project: SplineMakerProject) -> None:
    curve_data = curve_object.data
    
    _set_idprop_value(curve_object, PROP_MARKER, True, "Marks this object as SplineMaker data")
    _set_idprop_value(
        curve_object,
        PROP_PROJECT_NAME,
        project.project_name or curve_object.name,
        "Original SplineMaker project name",
    )
    _set_idprop_value(
        curve_object,
        PROP_SOURCE_PATH,
        project.source_path,
        "Last imported or exported SplineMaker JSON path",
    )
    _set_idprop_value(
        curve_object,
        PROP_VERSION,
        max(1, int(project.version)),
        "SplineMaker JSON format version",
    )
    _set_idprop_value(
        curve_object,
        PROP_CURVE_SMOOTHNESS,
        float(project.curve_smoothness),
        "SplineMaker project curve smoothness value",
    )
    _set_idprop_value(
        curve_object,
        PROP_ACTION_LEFT,
        float(project.action_area_left),
        "SplineMaker left controller action area size",
    )
    _set_idprop_value(
        curve_object,
        PROP_ACTION_RIGHT,
        float(project.action_area_right),
        "SplineMaker right controller action area size",
    )
    
    curve_data[PROP_MARKER] = True
    curve_data[PROP_PROJECT_NAME] = project.project_name or curve_object.name
    curve_data[PROP_VERSION] = max(1, int(project.version))


def build_curve_object_from_project(
    context: bpy.types.Context,
    project: SplineMakerProject,
    *,
    object_name: str = DEFAULT_OBJECT_NAME,
    target_object: bpy.types.Object | None = None,
) -> tuple[bpy.types.Object, list[str]]:
    warnings: list[str] = []
    
    if target_object is None:
        curve_data = bpy.data.curves.new(name=f"{object_name}Data", type="CURVE")
        curve_object = bpy.data.objects.new(object_name, curve_data)
        collection = context.collection or context.view_layer.active_layer_collection.collection
        collection.objects.link(curve_object)
    else:
        if target_object.type != "CURVE":
            raise ValueError("Target object must be a curve")
        curve_object = target_object
        curve_data = _ensure_single_user_curve_data(curve_object)
    
    curve_data.dimensions = "3D"
    clear_curve_splines(curve_data)
    
    for spline_index, spline_spec in enumerate(project.splines):
        point_count = len(spline_spec.points)
        if point_count < MIN_POINT_COUNT:
            warnings.append(
                f"Spline {spline_index} has fewer than {MIN_POINT_COUNT} points and was skipped"
            )
            continue
        
        blender_spline = curve_data.splines.new("NURBS")
        blender_spline.points.add(point_count - 1)
        
        for point_index, point in enumerate(spline_spec.points):
            blender_point = blender_spline.points[point_index]
            blender_x, blender_y, blender_z = spline_to_blender_coords(point.x, point.y, point.z)
            blender_point.co = (
                blender_x,
                blender_y,
                blender_z,
                max(0.001, float(point.weight)),
            )
            blender_point.radius = max(0.001, float(point.size))
            blender_point.tilt = 0.0
        
        blender_spline.order_u = clamp_order(spline_spec.order_u, point_count)
        blender_spline.resolution_u = max(1, int(spline_spec.resolution_u))
        blender_spline.use_cyclic_u = bool(spline_spec.cyclic)
        blender_spline.use_endpoint_u = not blender_spline.use_cyclic_u
    
    if project.project_name and target_object is None:
        curve_object.name = project.project_name

    store_project_metadata(curve_object, project)
    
    return curve_object, warnings


def read_project_metadata(
    curve_object: bpy.types.Object,
) -> SplineMakerProject:
    return SplineMakerProject(
        project_name=str(curve_object.get(PROP_PROJECT_NAME, curve_object.name)),
        source_path=str(curve_object.get(PROP_SOURCE_PATH, "")),
        version=max(1, _coerce_int(curve_object.get(PROP_VERSION), DEFAULT_PROJECT_VERSION)),
        curve_smoothness=_coerce_float(
            curve_object.get(PROP_CURVE_SMOOTHNESS),
            DEFAULT_CURVE_SMOOTHNESS,
        ),
        action_area_left=max(
            0.001,
            _coerce_float(curve_object.get(PROP_ACTION_LEFT), DEFAULT_ACTION_AREA_SIZE),
        ),
        action_area_right=max(
            0.001,
            _coerce_float(curve_object.get(PROP_ACTION_RIGHT), DEFAULT_ACTION_AREA_SIZE),
        ),
    )


def project_from_curve_objects(
    curve_objects: Sequence[bpy.types.Object],
    *,
    project_name: str = "",
    source_path: str = "",
    version: int | None = None,
    curve_smoothness: float | None = None,
    action_area_left: float | None = None,
    action_area_right: float | None = None,
) -> tuple[SplineMakerProject, list[str]]:
    if not curve_objects:
        raise ValueError("No curve objects were provided for export")
    
    warnings: list[str] = []
    primary_object = curve_objects[0]
    metadata = read_project_metadata(primary_object)
    
    project = SplineMakerProject(
        project_name=project_name or metadata.project_name or primary_object.name,
        source_path=source_path or metadata.source_path,
        version=max(1, int(version if version is not None else metadata.version)),
        curve_smoothness=float(
            curve_smoothness if curve_smoothness is not None else metadata.curve_smoothness
        ),
        action_area_left=max(
            0.001,
            float(action_area_left if action_area_left is not None else metadata.action_area_left),
        ),
        action_area_right=max(
            0.001,
            float(
                action_area_right
                if action_area_right is not None
                else metadata.action_area_right
            ),
        ),
    )
    
    for obj in curve_objects[1:]:
        other_meta = read_project_metadata(obj)
        if (
            other_meta.version != metadata.version
            or abs(other_meta.curve_smoothness - metadata.curve_smoothness) > 1e-6
            or abs(other_meta.action_area_left - metadata.action_area_left) > 1e-6
            or abs(other_meta.action_area_right - metadata.action_area_right) > 1e-6
        ):
            warnings.append(
                "Multiple curve objects had different SplineMaker metadata; export used the first object's values"
            )
            break
    
    for curve_object in curve_objects:
        if curve_object.type != "CURVE":
            warnings.append(f"Object '{curve_object.name}' is not a curve and was skipped")
            continue
        
        for spline_index, spline in enumerate(curve_object.data.splines):
            if spline.type != "NURBS":
                warnings.append(
                    f"Object '{curve_object.name}' spline {spline_index} is not NURBS and was skipped"
                )
                continue
            
            if len(spline.points) < MIN_POINT_COUNT:
                warnings.append(
                    f"Object '{curve_object.name}' spline {spline_index} has too few points and was skipped"
                )
                continue
            
            points: list[SplineMakerPoint] = []
            for point in spline.points:
                blender_x, blender_y, blender_z, w = point.co
                spline_x, spline_y, spline_z = blender_to_spline_coords(
                    blender_x,
                    blender_y,
                    blender_z,
                )
                points.append(
                    SplineMakerPoint(
                        x=spline_x,
                        y=spline_y,
                        z=spline_z,
                        size=max(0.001, float(point.radius)),
                        weight=max(0.001, float(w)),
                    )
                )
            
            project.splines.append(
                SplineMakerSpline(
                    points=points,
                    cyclic=bool(spline.use_cyclic_u),
                    order_u=clamp_order(int(spline.order_u), len(points)),
                    resolution_u=max(1, int(spline.resolution_u)),
                )
            )
    
    return project, warnings


def suggest_project_name(
    context: bpy.types.Context,
    curve_objects: Sequence[bpy.types.Object],
) -> str:
    if curve_objects:
        project_name = str(curve_objects[0].get(PROP_PROJECT_NAME, "")).strip()
        if project_name:
            return project_name
        return curve_objects[0].name
    
    blend_path = getattr(context.blend_data, "filepath", "")
    if blend_path:
        return Path(blend_path).stem
    return "SplineMakerProject"


def _report_messages(operator: Operator, level: set[str], messages: list[str]) -> None:
    for message in messages:
        operator.report(level, message)


class IMPORT_SCENE_OT_spline_maker_json(Operator, ImportHelper):
    bl_idname = "import_scene.spline_maker_json"
    bl_label = "Import SplineMaker JSON"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    files: CollectionProperty(
        name="Files",
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN", "SKIP_SAVE"},
    )
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})
    select_result: BoolProperty(
        name="Select Result",
        description="Select and activate the imported curve object or objects after import",
        default=True,
    )
    
    def _iter_filepaths(self) -> list[str]:
        if self.files:
            base_dir = Path(self.directory)
            return [str(base_dir / entry.name) for entry in self.files]
        return [self.filepath]
    
    def execute(self, context: bpy.types.Context):
        filepaths = self._iter_filepaths()
        imported_objects = []
        all_warnings: list[str] = []
        
        for filepath in filepaths:
            try:
                project, warnings = load_project(filepath)
                object_name = Path(filepath).stem or DEFAULT_OBJECT_NAME
                curve_object, build_warnings = build_curve_object_from_project(
                    context,
                    project,
                    object_name=object_name,
                    target_object=None,
                )
                imported_objects.append(curve_object)
                all_warnings.extend([f"{Path(filepath).name}: {msg}" for msg in warnings + build_warnings])
            except ValueError as exc:
                all_warnings.append(f"{Path(filepath).name}: {exc}")
            except Exception as exc:
                self.report({"ERROR"}, f"SplineMaker import failed: {exc}")
                return {"CANCELLED"}
        
        if not imported_objects:
            _report_messages(self, {"WARNING"}, all_warnings)
            self.report({"ERROR"}, "No SplineMaker files were imported")
            return {"CANCELLED"}
        
        if self.select_result:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in imported_objects:
                obj.select_set(True)
            context.view_layer.objects.active = imported_objects[-1]
        
        _report_messages(self, {"WARNING"}, all_warnings)
        self.report(
            {"INFO"},
            "Imported %d file(s) as %d new curve object(s)"
            % (len(imported_objects), len(imported_objects)),
        )
        return {"FINISHED"}


class EXPORT_SCENE_OT_spline_maker_json(Operator, ExportHelper):
    bl_idname = "export_scene.spline_maker_json"
    bl_label = "Export SplineMaker JSON"
    
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    
    batch_mode: EnumProperty(
        name="Batch Mode",
        description="How multiple resolved curve objects are written",
        items=EXPORT_BATCH_MODES,
        default="OFF",
    )
    use_selection: BoolProperty(
        name="Selected Objects",
        description="Export selected curve objects only",
        default=False,
    )
    use_active_collection: BoolProperty(
        name="Active Collection",
        description="Export curve objects from the active collection",
        default=False,
    )
    collection: StringProperty(
        name="Collection",
        description="Export curve objects from this collection when set",
        default="",
    )
    def invoke(self, context: bpy.types.Context, event):
        curve_objects = self._resolve_curve_objects(context)
        if not self.filepath:
            suggested_name = suggest_project_name(context, curve_objects)
            self.filepath = str(Path(bpy.path.abspath("//")) / f"{suggested_name}.json")
        
        return ExportHelper.invoke(self, context, event)
    
    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "batch_mode")
        layout.prop(self, "use_selection")
        layout.prop(self, "use_active_collection")
        layout.prop_search(self, "collection", bpy.data, "collections")
    
    def _resolve_curve_objects(self, context: bpy.types.Context) -> list[bpy.types.Object]:
        return export_objects(
            context,
            {"CURVE"},
            use_selection=self.use_selection,
            use_active_collection=self.use_active_collection,
            collection=self.collection,
        )
    
    def execute(self, context: bpy.types.Context):
        try:
            curve_objects = self._resolve_curve_objects(context)
            if not curve_objects:
                raise ValueError("No curve objects were found for export")
            
            warnings: list[str] = []
            export_count = 0
            
            if self.batch_mode == "OFF":
                output_path = Path(self.filepath)
                project_name = Path(output_path).stem or suggest_project_name(context, curve_objects)
                project, object_warnings = project_from_curve_objects(
                    curve_objects,
                    project_name=project_name,
                    source_path=str(output_path),
                    version=DEFAULT_PROJECT_VERSION,
                    curve_smoothness=DEFAULT_CURVE_SMOOTHNESS,
                    action_area_left=DEFAULT_ACTION_AREA_SIZE,
                    action_area_right=DEFAULT_ACTION_AREA_SIZE,
                )
                if not project.splines:
                    raise ValueError("No valid NURBS splines were available for export")
                save_project(str(output_path), project)
                for curve_object in curve_objects:
                    store_project_metadata(curve_object, project)
                warnings.extend(object_warnings)
                export_count = 1
            else:
                base_path = Path(self.filepath)
                export_dir = base_path if base_path.suffix.lower() != ".json" else base_path.parent
                if len(curve_objects) > 1:
                    warnings.append(
                        "Multiple objects selected; exporting one JSON file per object into '%s'"
                        % str(export_dir)
                    )
                for curve_object in curve_objects:
                    output_path = Path(object_export_path(str(export_dir), curve_object, self.filename_ext))
                    project, object_warnings = project_from_curve_objects(
                        [curve_object],
                        project_name=output_path.stem,
                        source_path=str(output_path),
                        version=DEFAULT_PROJECT_VERSION,
                        curve_smoothness=DEFAULT_CURVE_SMOOTHNESS,
                        action_area_left=DEFAULT_ACTION_AREA_SIZE,
                        action_area_right=DEFAULT_ACTION_AREA_SIZE,
                    )
                    
                    if not project.splines:
                        warnings.append(f"{curve_object.name}: no valid NURBS splines were available for export")
                        continue
                    
                    save_project(str(output_path), project)
                    store_project_metadata(curve_object, project)
                    export_count += 1
                    warnings.extend([f"{curve_object.name}: {msg}" for msg in object_warnings])
            
            if export_count == 0:
                raise ValueError("No valid NURBS splines were available for export")
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, f"SplineMaker export failed: {exc}")
            return {"CANCELLED"}
        
        _report_messages(self, {"WARNING"}, warnings)
        self.report({"INFO"}, f"Exported {export_count} SplineMaker project file(s)")
        return {"FINISHED"}



def menu_func_import(self, _context):
    self.layout.operator(
        IMPORT_SCENE_OT_spline_maker_json.bl_idname,
        text="SplineMaker Project (.json)",
    )


def menu_func_export(self, _context):
    self.layout.operator(
        EXPORT_SCENE_OT_spline_maker_json.bl_idname,
        text="SplineMaker Project (.json)",
    )


classes = (
    IMPORT_SCENE_OT_spline_maker_json,
    EXPORT_SCENE_OT_spline_maker_json,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
