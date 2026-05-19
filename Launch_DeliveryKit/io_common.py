import bpy
import os


EXPORT_BATCH_MODES = (
    ("OFF", "Off", "Export all resolved objects to one file"),
    ("OBJECT", "Object", "Export each resolved object to a separate file"),
)


def export_objects(
    context,
    object_types,
    *,
    use_selection=False,
    use_active_collection=False,
    collection="",
):
    if use_selection:
        objects = list(context.selected_objects)
    elif use_active_collection:
        objects = list(context.collection.all_objects) if context.collection else []
    elif collection:
        source_collection = bpy.data.collections.get(collection)
        objects = list(source_collection.all_objects) if source_collection else []
    else:
        objects = list(context.scene.objects)
    
    allowed_types = set(object_types)
    return [obj for obj in dict.fromkeys(objects) if obj.type in allowed_types]


def object_export_path(filepath, obj, extension):
    base_dir = bpy.path.abspath("//")
    if filepath:
        base_dir = bpy.path.abspath(filepath)
        if base_dir.lower().endswith(extension.lower()):
            base_dir = os.path.dirname(base_dir)
    safe_name = bpy.path.clean_name(obj.name) or "Object"
    return f"{base_dir.rstrip('/')}/{safe_name}{extension}"
