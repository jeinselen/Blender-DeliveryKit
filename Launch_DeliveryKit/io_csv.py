import csv
import os
import re

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

try:
	from .io_common import EXPORT_BATCH_MODES, export_objects, object_export_path
except ImportError:
	from io_common import EXPORT_BATCH_MODES, export_objects, object_export_path


CSV_MODES = (
	('POINTS', 'Points', 'Import/export mesh vertex points'),
	('POSITIONS', 'Positions', 'Import/export object transform keyframes'),
)

CSV_IMPORT_MODES = (
	('SEPARATE', 'Separate', 'Read each CSV file as its own object or animation set'),
	('COMBINED', 'Combined', 'Read all selected CSV files as one imported data set'),
)

CHANNELS = (
	('x', 'X', 'Positive X'),
	('-x', '-X', 'Inverted X'),
	('y', 'Y', 'Positive Y'),
	('-y', '-Y', 'Inverted Y'),
	('z', 'Z', 'Positive Z'),
	('-z', '-Z', 'Inverted Z'),
)


def clean_name(filepath):
	name = os.path.splitext(os.path.basename(filepath))[0]
	return name or "CSV Data"


def swizzle_value(vector, channel):
	sign = -1.0 if channel.startswith('-') else 1.0
	axis = channel[-1]
	return sign * getattr(vector, axis)


def swizzle_vector(vector, channel_x, channel_y, channel_z):
	return (
		swizzle_value(vector, channel_x),
		swizzle_value(vector, channel_y),
		swizzle_value(vector, channel_z),
	)


def float_or_none(value):
	if value is None or value == "":
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def first_existing(row, names):
	for name in names:
		if name in row:
			return row.get(name)
	return None


def read_csv_rows(filepath):
	with open(filepath, 'r', newline='', encoding='utf-8-sig') as handle:
		reader = csv.DictReader(handle)
		if not reader.fieldnames:
			return [], []
		rows = list(reader)
		return reader.fieldnames, rows


def write_csv_rows(filepath, headers, rows):
	os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
	with open(filepath, 'w', newline='', encoding='utf-8') as handle:
		writer = csv.DictWriter(handle, fieldnames=headers, extrasaction='ignore')
		writer.writeheader()
		writer.writerows(rows)


def coordinate_from_row(row):
	x = float_or_none(first_existing(row, ('x', 'X', 'position_x', 'Position X')))
	y = float_or_none(first_existing(row, ('y', 'Y', 'position_y', 'Position Y')))
	z = float_or_none(first_existing(row, ('z', 'Z', 'position_z', 'Position Z')))
	if x is None or y is None or z is None:
		return None
	return (x, y, z)


def ordered_headers(rows, preferred):
	headers = list(preferred)
	for row in rows:
		for key in row.keys():
			if key not in headers:
				headers.append(key)
	return headers


def attribute_specs(mesh):
	specs = []
	if not hasattr(mesh, 'attributes') or mesh.attributes is None:
		return specs
	for attr in mesh.attributes:
		if attr.domain != 'POINT' or attr.name.startswith('.') or len(attr.data) == 0:
			continue
		if attr.data_type == 'INT':
			specs.append((attr, [f"{attr.name}_i"]))
		elif attr.data_type == 'FLOAT':
			specs.append((attr, [f"{attr.name}_f"]))
		elif attr.data_type == 'FLOAT2':
			specs.append((attr, [f"{attr.name}_u", f"{attr.name}_v"]))
		elif attr.data_type == 'FLOAT_VECTOR':
			specs.append((attr, [f"{attr.name}_x", f"{attr.name}_y", f"{attr.name}_z"]))
		elif attr.data_type == 'FLOAT_COLOR':
			specs.append((attr, [f"{attr.name}_r", f"{attr.name}_g", f"{attr.name}_b", f"{attr.name}_a"]))
	return specs


def add_attribute_values(row, vertex_index, specs):
	for attr, headers in specs:
		if attr.data_type == 'INT':
			row[headers[0]] = attr.data[vertex_index].value
		elif attr.data_type == 'FLOAT':
			row[headers[0]] = attr.data[vertex_index].value
		elif attr.data_type == 'FLOAT2':
			value = attr.data[vertex_index].vector
			row[headers[0]] = value.x
			row[headers[1]] = value.y
		elif attr.data_type == 'FLOAT_VECTOR':
			value = attr.data[vertex_index].vector
			row[headers[0]] = value.x
			row[headers[1]] = value.y
			row[headers[2]] = value.z
		elif attr.data_type == 'FLOAT_COLOR':
			value = attr.data[vertex_index].color
			row[headers[0]] = value[0]
			row[headers[1]] = value[1]
			row[headers[2]] = value[2]
			row[headers[3]] = value[3]


def points_rows_from_object(context, obj, channel_x, channel_y, channel_z, include_object=False, include_attributes=True):
	depsgraph = context.evaluated_depsgraph_get()
	obj_eval = obj.evaluated_get(depsgraph)
	mesh = obj_eval.to_mesh()
	try:
		rows = []
		specs = attribute_specs(mesh) if include_attributes else []
		for vertex in mesh.vertices:
			x, y, z = swizzle_vector(vertex.co, channel_x, channel_y, channel_z)
			row = {'x': x, 'y': y, 'z': z}
			if include_object:
				row = {'object': obj.name, **row}
			add_attribute_values(row, vertex.index, specs)
			rows.append(row)
		return rows
	finally:
		obj_eval.to_mesh_clear()


def classify_attribute_columns(headers):
	columns = {
		'INT': [],
		'FLOAT': [],
		'FLOAT2': {},
		'FLOAT_VECTOR': {},
		'FLOAT_COLOR': {},
	}
	ignored = {
		'object', 'Object',
		'x', 'y', 'z', 'X', 'Y', 'Z',
		'position_x', 'position_y', 'position_z',
		'Position X', 'Position Y', 'Position Z',
	}
	for header in headers:
		if header in ignored:
			continue
		if header.endswith('_i'):
			columns['INT'].append(header)
		elif header.endswith('_f'):
			columns['FLOAT'].append(header)
		elif header.endswith(('_u', '_v')):
			base = re.sub(r'_[uv]$', '', header)
			columns['FLOAT2'].setdefault(base, []).append(header)
		elif header.endswith(('_x', '_y', '_z')):
			base = re.sub(r'_[xyz]$', '', header)
			columns['FLOAT_VECTOR'].setdefault(base, []).append(header)
		elif header.endswith(('_r', '_g', '_b', '_a')):
			base = re.sub(r'_[rgba]$', '', header)
			columns['FLOAT_COLOR'].setdefault(base, []).append(header)
	return columns


def valid_values(rows, headers, converter=float):
	values = []
	for row in rows:
		row_values = []
		for header in headers:
			value = row.get(header)
			if value is None or value == "":
				return None
			try:
				row_values.append(converter(value))
			except (TypeError, ValueError):
				return None
		values.append(row_values)
	return values


def add_imported_attributes(mesh, headers, rows):
	columns = classify_attribute_columns(headers)
	for header in columns['INT']:
		values = valid_values(rows, [header], int)
		if values is None:
			continue
		attr = mesh.attributes.new(name=re.sub(r'_i$', '', header), type='INT', domain='POINT')
		for item, value in zip(attr.data, values):
			item.value = value[0]
	for header in columns['FLOAT']:
		values = valid_values(rows, [header], float)
		if values is None:
			continue
		attr = mesh.attributes.new(name=re.sub(r'_f$', '', header), type='FLOAT', domain='POINT')
		for item, value in zip(attr.data, values):
			item.value = value[0]
	for base, group in columns['FLOAT2'].items():
		headers_ordered = [f"{base}_u", f"{base}_v"]
		if sorted(group) != sorted(headers_ordered):
			continue
		values = valid_values(rows, headers_ordered, float)
		if values is None:
			continue
		attr = mesh.attributes.new(name=base, type='FLOAT2', domain='POINT')
		for item, value in zip(attr.data, values):
			item.vector[0] = value[0]
			item.vector[1] = value[1]
	for base, group in columns['FLOAT_VECTOR'].items():
		headers_ordered = [f"{base}_x", f"{base}_y", f"{base}_z"]
		if sorted(group) != sorted(headers_ordered):
			continue
		values = valid_values(rows, headers_ordered, float)
		if values is None:
			continue
		attr = mesh.attributes.new(name=base, type='FLOAT_VECTOR', domain='POINT')
		for item, value in zip(attr.data, values):
			item.vector[0] = value[0]
			item.vector[1] = value[1]
			item.vector[2] = value[2]
	for base, group in columns['FLOAT_COLOR'].items():
		headers_ordered = [f"{base}_r", f"{base}_g", f"{base}_b", f"{base}_a"]
		if sorted(group) != sorted(headers_ordered):
			continue
		values = valid_values(rows, headers_ordered, float)
		if values is None:
			continue
		attr = mesh.attributes.new(name=base, type='FLOAT_COLOR', domain='POINT')
		for item, value in zip(attr.data, values):
			item.color[0] = value[0]
			item.color[1] = value[1]
			item.color[2] = value[2]
			item.color[3] = value[3]


def create_points_object(context, name, rows, headers):
	vertices = []
	valid_rows = []
	for row in rows:
		coord = coordinate_from_row(row)
		if coord is None:
			continue
		vertices.append(coord)
		valid_rows.append(row)
	mesh = bpy.data.meshes.new(name=name)
	mesh.from_pydata(vertices, [], [])
	mesh.update()
	add_imported_attributes(mesh, headers, valid_rows)
	obj = bpy.data.objects.new(name, mesh)
	context.collection.objects.link(obj)
	return obj


def import_points_file(context, filepath):
	headers, rows = read_csv_rows(filepath)
	return create_points_object(context, clean_name(filepath), rows, headers)


def import_points_file_split_objects(context, filepath):
	headers, rows = read_csv_rows(filepath)
	if 'object' not in headers and 'Object' not in headers:
		return [create_points_object(context, clean_name(filepath), rows, headers)]
	grouped = {}
	for row in rows:
		name = row.get('object') or row.get('Object') or clean_name(filepath)
		grouped.setdefault(name, []).append(row)
	return [create_points_object(context, name, object_rows, headers) for name, object_rows in grouped.items()]


def import_points_combined(context, filepaths, name):
	rows_all = []
	headers_all = []
	for filepath in filepaths:
		headers, rows = read_csv_rows(filepath)
		headers_all = ordered_headers([dict.fromkeys(headers), dict.fromkeys(headers_all)], headers_all)
		rows_all.extend(rows)
	return create_points_object(context, name, rows_all, headers_all)


def transform_channels(row):
	location = tuple(float_or_none(first_existing(row, names)) for names in (
		('x', 'X', 'position_x', 'Position X'),
		('y', 'Y', 'position_y', 'Position Y'),
		('z', 'Z', 'position_z', 'Position Z'),
	))
	rotation = tuple(float_or_none(first_existing(row, names)) for names in (
		('rotation_x', 'rot_x', 'Rotation X'),
		('rotation_y', 'rot_y', 'Rotation Y'),
		('rotation_z', 'rot_z', 'Rotation Z'),
	))
	scale = tuple(float_or_none(first_existing(row, names)) for names in (
		('scale_x', 'Scale X'),
		('scale_y', 'Scale Y'),
		('scale_z', 'Scale Z'),
	))
	return location, rotation, scale


def has_complete_channel(values):
	return all(value is not None for value in values)


def row_frame(row, fallback):
	value = float_or_none(first_existing(row, ('frame', 'Frame')))
	return int(value) if value is not None else fallback


def ensure_empty(name):
	obj = bpy.data.objects.get(name)
	if obj is not None:
		return obj
	obj = bpy.data.objects.new(name, None)
	bpy.context.collection.objects.link(obj)
	return obj


def position_object_name(row, default_name):
	return row.get('object') or row.get('Object') or row.get('name') or row.get('Name') or default_name


def apply_position_row(context, obj, row, frame):
	location, rotation, scale = transform_channels(row)
	inserted = False
	if has_complete_channel(location):
		obj.location = location
		obj.keyframe_insert(data_path='location', frame=frame)
		inserted = True
	if has_complete_channel(rotation):
		obj.rotation_euler = rotation
		obj.keyframe_insert(data_path='rotation_euler', frame=frame)
		inserted = True
	if has_complete_channel(scale):
		obj.scale = scale
		obj.keyframe_insert(data_path='scale', frame=frame)
		inserted = True
	return inserted


def import_position_rows(context, rows, default_name):
	targets = {}
	next_frames = {}
	for row in rows:
		obj_name = position_object_name(row, default_name)
		obj = targets.setdefault(obj_name, ensure_empty(obj_name))
		fallback = next_frames.setdefault(obj_name, context.scene.frame_start)
		frame = row_frame(row, fallback)
		if apply_position_row(context, obj, row, frame):
			next_frames[obj_name] = frame + 1
	return list(targets.values())


def import_positions_file(context, filepath):
	_headers, rows = read_csv_rows(filepath)
	return import_position_rows(context, rows, clean_name(filepath))


def import_positions_combined(context, filepaths):
	rows_all = []
	default_name = clean_name(filepaths[0])
	for filepath in filepaths:
		_headers, rows = read_csv_rows(filepath)
		if len(filepaths) > 1:
			source_name = clean_name(filepath)
			for row in rows:
				if not position_object_name(row, None):
					row['object'] = source_name
		rows_all.extend(rows)
	return import_position_rows(context, rows_all, default_name)


def position_rows_from_object(context, obj, include_object=False, space='WORLD'):
	rows = []
	current = context.scene.frame_current
	try:
		for frame in range(context.scene.frame_start, context.scene.frame_end + 1):
			context.scene.frame_set(frame)
			matrix = obj.matrix_world if space == 'WORLD' else obj.matrix_local
			loc, rot, scale = matrix.decompose()
			rot = rot.to_euler()
			row = {
				'frame': frame,
				'x': loc.x,
				'y': loc.y,
				'z': loc.z,
				'rotation_x': rot.x,
				'rotation_y': rot.y,
				'rotation_z': rot.z,
				'scale_x': scale.x,
				'scale_y': scale.y,
				'scale_z': scale.z,
			}
			if include_object:
				row = {'object': obj.name, **row}
			rows.append(row)
	finally:
		context.scene.frame_set(current)
	return rows


class IMPORT_SCENE_OT_csv_data(bpy.types.Operator, ImportHelper):
	bl_idname = "import_scene.csv_data"
	bl_label = "Import CSV Data"
	bl_options = {'PRESET', 'UNDO'}

	filename_ext = ".csv"
	filter_glob: bpy.props.StringProperty(default="*.csv", options={'HIDDEN'}, maxlen=255)
	files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement)
	directory: bpy.props.StringProperty(subtype='DIR_PATH')
	mode: bpy.props.EnumProperty(name="Mode", items=CSV_MODES, default='POINTS')
	import_mode: bpy.props.EnumProperty(name="Import Mode", items=CSV_IMPORT_MODES, default='SEPARATE')

	def draw(self, context):
		layout = self.layout
		layout.prop(self, "mode", expand=True)
		layout.prop(self, "import_mode", expand=True)

	def execute(self, context):
		filepaths = [os.path.join(self.directory, item.name) for item in self.files] if self.files else [self.filepath]
		filepaths = [path for path in filepaths if path.lower().endswith('.csv')]
		if not filepaths:
			self.report({'ERROR'}, "No CSV files selected.")
			return {'CANCELLED'}
		try:
			imported = []
			if self.mode == 'POINTS':
				if self.import_mode == 'COMBINED':
					imported.append(import_points_combined(context, filepaths, clean_name(filepaths[0])))
				else:
					for filepath in filepaths:
						imported.extend(import_points_file_split_objects(context, filepath))
			else:
				if self.import_mode == 'COMBINED':
					imported.extend(import_positions_combined(context, filepaths))
				else:
					for filepath in filepaths:
						imported.extend(import_positions_file(context, filepath))
			for obj in context.selected_objects:
				obj.select_set(False)
			for obj in imported:
				obj.select_set(True)
			if imported:
				context.view_layer.objects.active = imported[-1]
		except Exception as exc:
			self.report({'ERROR'}, f"Failed to import CSV: {exc}")
			return {'CANCELLED'}
		return {'FINISHED'}


class EXPORT_SCENE_OT_csv_data(bpy.types.Operator, ExportHelper):
	bl_idname = "export_scene.csv_data"
	bl_label = "Export CSV Data"
	bl_options = {'PRESET'}

	filename_ext = ".csv"
	filter_glob: bpy.props.StringProperty(default="*.csv", options={'HIDDEN'}, maxlen=255)
	mode: bpy.props.EnumProperty(name="Mode", items=CSV_MODES, default='POINTS')
	batch_mode: bpy.props.EnumProperty(
		name="Batch Mode",
		description="How multiple resolved objects are written",
		items=EXPORT_BATCH_MODES,
		default='OFF',
	)
	use_selection: bpy.props.BoolProperty(
		name="Selected Objects",
		description="Export selected objects only",
		default=False,
	)
	use_active_collection: bpy.props.BoolProperty(
		name="Active Collection",
		description="Export objects from the active collection",
		default=False,
	)
	collection: bpy.props.StringProperty(
		name="Collection",
		description="Export objects from this collection when set",
		default="",
	)
	space: bpy.props.EnumProperty(
		name="Space",
		items=(('WORLD', 'World', 'World space'), ('LOCAL', 'Local', 'Local object space')),
		default='WORLD',
	)
	channel_x: bpy.props.EnumProperty(name="X", items=CHANNELS, default='x')
	channel_y: bpy.props.EnumProperty(name="Y", items=CHANNELS, default='y')
	channel_z: bpy.props.EnumProperty(name="Z", items=CHANNELS, default='z')
	include_attributes: bpy.props.BoolProperty(
		name="Include Attributes",
		description="Export point-domain custom mesh attributes",
		default=True,
	)

	def draw(self, context):
		layout = self.layout
		layout.prop(self, "mode", expand=True)
		layout.prop(self, "batch_mode")
		layout.prop(self, "use_selection")
		layout.prop(self, "use_active_collection")
		layout.prop_search(self, "collection", bpy.data, "collections")
		if self.mode == 'POINTS':
			layout.prop(self, "include_attributes")
			channels = layout.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=False, align=False)
			channels.prop(self, "channel_x", expand=True)
			channels.prop(self, "channel_y", expand=True)
			channels.prop(self, "channel_z", expand=True)
		else:
			layout.prop(self, "space", expand=True)

	def invoke(self, context, event):
		obj = context.active_object
		if obj and not self.filepath:
			self.filepath = bpy.path.ensure_ext(bpy.path.abspath(f"//{obj.name}"), self.filename_ext)
		return super().invoke(context, event)

	def execute(self, context):
		objects = export_objects(
			context,
			{'MESH'} if self.mode == 'POINTS' else {'CURVE', 'EMPTY', 'FONT', 'MESH', 'META', 'SURFACE'},
			use_selection=self.use_selection,
			use_active_collection=self.use_active_collection,
			collection=self.collection,
		)
		if not objects:
			self.report({'ERROR'}, "No exportable objects found.")
			return {'CANCELLED'}
		try:
			if self.mode == 'POINTS':
				preferred = ['x', 'y', 'z'] if self.batch_mode == 'OBJECT' else ['object', 'x', 'y', 'z']
				if self.batch_mode == 'OFF':
					rows = []
					for obj in objects:
						rows.extend(points_rows_from_object(context, obj, self.channel_x, self.channel_y, self.channel_z, True, self.include_attributes))
					headers = ordered_headers(rows, preferred)
					write_csv_rows(self.filepath, headers, rows)
				else:
					for obj in objects:
						filepath = object_export_path(self.filepath, obj, self.filename_ext)
						rows = points_rows_from_object(context, obj, self.channel_x, self.channel_y, self.channel_z, False, self.include_attributes)
						headers = ordered_headers(rows, preferred)
						write_csv_rows(filepath, headers, rows)
			else:
				headers = ['frame', 'x', 'y', 'z', 'rotation_x', 'rotation_y', 'rotation_z', 'scale_x', 'scale_y', 'scale_z']
				if self.batch_mode == 'OFF':
					headers = ['object'] + headers
					rows = []
					for obj in objects:
						rows.extend(position_rows_from_object(context, obj, True, self.space))
					write_csv_rows(self.filepath, headers, rows)
				else:
					for obj in objects:
						filepath = object_export_path(self.filepath, obj, self.filename_ext)
						rows = position_rows_from_object(context, obj, False, self.space)
						write_csv_rows(filepath, headers, rows)
		except Exception as exc:
			self.report({'ERROR'}, f"Failed to export CSV: {exc}")
			return {'CANCELLED'}
		return {'FINISHED'}


def menu_func_import(self, context):
	self.layout.operator(IMPORT_SCENE_OT_csv_data.bl_idname, text="CSV Data (.csv)")


def menu_func_export(self, context):
	self.layout.operator(EXPORT_SCENE_OT_csv_data.bl_idname, text="CSV Data (.csv)")


classes = (
	IMPORT_SCENE_OT_csv_data,
	EXPORT_SCENE_OT_csv_data,
)


def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)


if __name__ == "__main__":
	register()
