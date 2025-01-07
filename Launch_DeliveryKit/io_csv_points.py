import bpy
import csv
import mathutils
import numpy
import os
import re
from bpy_extras.io_utils import ImportHelper, ExportHelper

class ImportCSVPoints(bpy.types.Operator, ImportHelper):
	bl_idname = "import_points.csv"
	bl_label = "Import CSV Points"
	
	filename_ext = ".csv"
	
	filter_glob: bpy.props.StringProperty(
		default="*.csv",
		options={'HIDDEN'},
		maxlen=255,
	)
	
	def execute(self, context):
		return self.read(context, self.filepath)
	
	def read(self, context, filepath):
		try:
			with open(filepath, 'r', newline='', encoding='utf-8') as file:
				reader = csv.DictReader(file)
				headers = reader.fieldnames
				if not headers:
					self.report({'ERROR'}, "No headers found in CSV file.")
					return {'CANCELLED'}
				
				# Read all rows into a list
				rows = list(reader)
				
				# Identify data types and group columns
				attributes = {
					"BOOL": [],
					"FLOAT": [],
					"INT": [],
					"FLOAT2": {},
					"FLOAT_VECTOR": {},
					"FLOAT_COLOR": {},
				}
				scalar_types = {
					"_0": "BOOL",
					"_f": "FLOAT",
					"_i": "INT",
				}
				
				ignore_fields = {"position_x", "position_y", "position_z"}
				
				for header in headers:
					# Skip position columns
					if header in ignore_fields:
						continue
					
					if header.endswith(("_u", "_v")):
						base_name = re.sub(r'_[uv]{1}$', '', header)
						attributes["FLOAT2"].setdefault(base_name, []).append(header)
					elif header.endswith(("_x", "_y", "_z")):
						base_name = re.sub(r'_[xyz]{1}$', '', header)
						attributes["FLOAT_VECTOR"].setdefault(base_name, []).append(header)
					elif header.endswith(("_r", "_g", "_b", "_a")):
						base_name = re.sub(r'_[rgba]{1}$', '', header)
						attributes["FLOAT_COLOR"].setdefault(base_name, []).append(header)
					else:
						for suffix, attr_type in scalar_types.items():
							if header.endswith(suffix):
								attributes[attr_type].append(header)
								break
				
				# Create mesh object
				mesh_name = os.path.splitext(os.path.basename(filepath))[0]
				mesh_data = bpy.data.meshes.new(name=mesh_name)
				mesh_obj = bpy.data.objects.new(mesh_name, mesh_data)
				context.scene.collection.objects.link(mesh_obj)
				
				# Collect vertex positions and store them
				vertices = []
				for row in rows:
					pos_x = float(row.get("position_x", row.get("x", 0)))
					pos_y = float(row.get("position_y", row.get("y", 0)))
					pos_z = float(row.get("position_z", row.get("z", 0)))
					vertices.append((pos_x, pos_y, pos_z))
				
				# Create the mesh geometry
				mesh_data.from_pydata(vertices, [], [])
				
				# Process attributes
				for attr_type, columns in attributes.items():
					if attr_type in {"FLOAT_COLOR", "FLOAT_VECTOR", "FLOAT2"}:
						# Multi-component attributes
						for base_name, channels in columns.items():
							if len(channels) == 2 and attr_type == "FLOAT2":
								# FLOAT2 (u, v)
								float2_values = []
								for row in rows:
									f1 = float(row[channels[0]])
									f2 = float(row[channels[1]])
									# Flatten
									float2_values.extend([f1, f2])
								
								float2_attr = mesh_data.attributes.new(
									name=base_name,
									type='FLOAT2',
									domain='POINT'
								)
								float2_attr.data.foreach_set("vector", float2_values)
							elif len(channels) == 3 and attr_type == "FLOAT_VECTOR":
								# FLOAT_VECTOR (x, y, z)
								vector_values = []
								for row in rows:
									f1 = float(row[channels[0]])
									f2 = float(row[channels[1]])
									f3 = float(row[channels[2]])
									vector_values.extend([f1, f2, f3])
								
								vector_attr = mesh_data.attributes.new(
									name=base_name,
									type='FLOAT_VECTOR',
									domain='POINT'
								)
								vector_attr.data.foreach_set("vector", vector_values)
							elif len(channels) == 4 and attr_type == "FLOAT_COLOR":
								# FLOAT_COLOR (r, g, b, a)
								color_values = []
								for row in rows:
									f1 = float(row[channels[0]])
									f2 = float(row[channels[1]])
									f3 = float(row[channels[2]])
									f4 = float(row[channels[3]])
									color_values.extend([f1, f2, f3, f4])
								
								color_attr = mesh_data.attributes.new(
									name=base_name,
									type='FLOAT_COLOR',
									domain='POINT'
								)
								color_attr.data.foreach_set("color", color_values)
					
					else:
						# Scalar attributes (BOOL, INT, FLOAT)
						for attr in columns:
							name = re.sub(r'_[0fiuvxyzrgba]{1}$', '', attr)
							values_raw = [row[attr] for row in rows]
							
							if attr_type == "BOOL":
#								bool_values = [bool(int(v)) for v in values_raw]
								bool_values = [bool(True if float(v) > 0.5 else False) for v in values_raw]
								bool_attr = mesh_data.attributes.new(
									name=name,
									type='BOOL',
									domain='POINT'
								)
								bool_attr.data.foreach_set("boolean", bool_values)
							elif attr_type == "INT":
								int_values = [int(v) for v in values_raw]
								int_attr = mesh_data.attributes.new(
									name=name,
									type='INT',
									domain='POINT'
								)
								int_attr.data.foreach_set("value", int_values)
							elif attr_type == "FLOAT":
								float_values = [float(v) for v in values_raw]
								float_attr = mesh_data.attributes.new(
									name=name,
									type='FLOAT',
									domain='POINT'
								)
								float_attr.data.foreach_set("value", float_values)
				
				# Select imported object and set it as as active
				for obj in bpy.context.selected_objects:
					obj.select_set(False)
				mesh_obj.select_set(True)
				context.view_layer.objects.active = mesh_obj
				
				return {'FINISHED'}
		
		except Exception as e:
			self.report({'ERROR'}, f"Failed to import CSV: {str(e)}")
			return {'CANCELLED'}

class ExportCSVPoints(bpy.types.Operator, ExportHelper):
	bl_idname = "export_points.csv"
	bl_label = "Export CSV Points"
	
	filename_ext = ".csv"
	
	filter_glob: bpy.props.StringProperty(
		default="*.csv",
		options={'HIDDEN'},
		maxlen=255,
	)
	
	channel_x: bpy.props.EnumProperty(
		name="X",
		description="X Output Value",
		items=[
			('x',  "X",  "Positive X"),
			('-x', "-X", "Inverted X"),
			('y',  "Y",  "Positive Y"),
			('-y', "-Y", "Inverted Y"),
			('z',  "Z",  "Positive Z"),
			('-z', "-Z", "Inverted Z"),
		],
		default='x',
	)
	
	channel_y: bpy.props.EnumProperty(
		name="Y",
		description="Y Output Value",
		items=[
			('x',  "X",  "Positive X"),
			('-x', "-X", "Inverted X"),
			('y',  "Y",  "Positive Y"),
			('-y', "-Y", "Inverted Y"),
			('z',  "Z",  "Positive Z"),
			('-z', "-Z", "Inverted Z"),
		],
		default='y',
	)
	
	channel_z: bpy.props.EnumProperty(
		name="Z",
		description="Z Output Value",
		items=[
			('x',  "X",  "Positive X"),
			('-x', "-X", "Inverted X"),
			('y',  "Y",  "Positive Y"),
			('-y', "-Y", "Inverted Y"),
			('z',  "Z",  "Positive Z"),
			('-z', "-Z", "Inverted Z"),
		],
		default='z',
	)
	
	
	enable_bezier: bpy.props.BoolProperty(
		name="Enable Bezier",
		description="Export Bézier handles relative to the associated Bézier control point",
		default=False,
	)
	
	relative_handles: bpy.props.BoolProperty(
		name="Relative Handles",
		description="Export Bézier handles relative to the associated Bézier control point",
		default=True,
	)
	
	include_attributes: bpy.props.BoolProperty(
		name="Include Attributes",
		description="Export custom attributes",
		default=True,
	)
	
	def draw(self, context):
		layout = self.layout
		
		channels = layout.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=False, align=False)
		channels.label(text="data", icon="EVENT_X")
		channels.label(text="data", icon="EVENT_Y")
		channels.label(text="data", icon="EVENT_Z")
		xcol = channels.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
		xcol.prop(self, "channel_x", expand=True)
		ycol = channels.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
		ycol.prop(self, "channel_y", expand=True)
		zcol = channels.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
		zcol.prop(self, "channel_z", expand=True)
		
		layout.separator(factor=1.0, type='AUTO')
#		layout.label(text="General Options", icon="MESH_GRID") # MESH_GRID GROUP_VERTEX LATTICE_DATA OUTLINER_DATA_LATTICE HANDLE_VECTOR OUTLINER_DATA_POINTCLOUD POINTCLOUD_DATA POINTCLOUD_POINT OUTLINER_OB_POINTCLOUD SNAP_MIDPOINT
		row = layout.row()
		if self.enable_bezier:
			row.active = False
			row.enabled = False
		row.prop(self, "include_attributes")
		
#		layout.separator(factor=1.0, type='AUTO')
#		layout.label(text="Bézier Options", icon="IPO_BEZIER") # CURVE_BEZCIRCLE CURVE_BEZCURVE IPO_BEZIER HANDLE_ALIGNED HANDLE_FREE
#		layout.prop(self, "enable_bezier")
#		layout.prop(self, "relative_handles")
	
	def execute(self, context):
		return self.write(context, self.filepath)
	
	def write(self, context, filepath):
		# Get evaluated object
		obj = bpy.context.evaluated_depsgraph_get().objects.get(bpy.context.active_object.name)
		obj_mesh = obj.to_mesh()
		
		array = []
		
		# If Bézier mode is enabled and the object is a curve object, try to find Bézier curves to get their handle data
		if self.enable_bezier and obj and obj.type == 'CURVE':
			# Loop over all splines in the curve
			for spline in obj.data.splines:
				# Check if it's a Bézier spline
				if spline.type == 'BEZIER':
					# Array headers
					headers = ["bezier_x", "bezier_y", "bezier_z", "bezier_left_x", "bezier_left_y", "bezier_left_z", "bezier_right_x", "bezier_right_y", "bezier_right_z"]
					array.append(headers)
					
					# Loop over all Bézier points in the spline
					for point in spline.bezier_points:
						# Get the coordinates of the control point
						coord = point.co
						# Get the coordinates of the left and right handles
						handle_left = point.handle_left - coord if self.relative_handles else point.handle_left
						handle_right = point.handle_right - coord if self.relative_handles else point.handle_right
						
						# Swizzle output channels
						coord = swizzleChannels(coord, self.channel_x, self.channel_y, self.channel_z)
						coord.append(swizzleChannels(handle_left, self.channel_x, self.channel_y, self.channel_z))
						coord.append(swizzleChannels(handle_right, self.channel_x, self.channel_y, self.channel_z))
						
						array.append(coord)
		
		# If Bézier mode is deactivated
		else:
			# Collect data with temporary mesh conversion
			headers = ["x", "y", "z"]
			if self.include_attributes:
				headers = customAttributeHeaders(obj_mesh, headers)
			
			array.append(headers)
			print(headers)
			
			# Loop over all vertices in the mesh
			for point in obj_mesh.vertices:
				coord = point.co
				
				# Swizzle output channels
				values = swizzleChannels(coord, self.channel_x, self.channel_y, self.channel_z)
				
				# Add custom attributes
				if self.include_attributes:
					values = customAttributeValues(obj_mesh, point.index, values)
				
				array.append(values)
				print(values)
			
			# Remove temporary mesh conversion
#			obj_mesh.to_mesh_clear()
		
		# Save out CSV file
		numpy.savetxt(filepath, array, delimiter=",", newline='\n', fmt='% s')
		
		return {'FINISHED'}



# Utilities

def swizzleChannels(vector, x, y, z):
	output = []
	# I know this is a mess, but Python doesn't have nice switching, so here you go! Totally illegal usage of nested ternary notation
	output.append(vector.x if x == "x" else (-vector.x if x == "-x" else (vector.y if x == "y" else (-vector.y if x == "-y" else (vector.z if x == "z" else -vector.z)))))
	output.append(vector.x if y == "x" else (-vector.x if y == "-x" else (vector.y if y == "y" else (-vector.y if y == "-y" else (vector.z if y == "z" else -vector.z)))))
	output.append(vector.x if z == "x" else (-vector.x if z == "-x" else (vector.y if z == "y" else (-vector.y if z == "-y" else (vector.z if z == "z" else -vector.z)))))
	return output

def customAttributeHeaders(obj, headers):
	if hasattr(obj, 'data') and obj.data is not None:
		obj = obj.data
	
	if hasattr(obj, 'attributes') and obj.attributes is not None:
		for attr in obj.attributes:
			# Only operate on attributes applied to points
			if attr.domain != "POINT" or attr.name.startswith(".") or 1 > len(attr.data):
				continue
			
			# Single values
			elif attr.data_type == 'BOOLEAN':
				headers.append(f"{attr.name}_b")
			elif attr.data_type == 'INT':
				headers.append(f"{attr.name}_i")
			if attr.data_type == 'FLOAT':
				headers.append(f"{attr.name}_f")
			# Multiple values
			elif attr.data_type == 'FLOAT2':
				headers.extend([f"{attr.name}_u", f"{attr.name}_v"])
			elif attr.data_type == 'FLOAT_VECTOR':
				headers.extend([f"{attr.name}_x", f"{attr.name}_y", f"{attr.name}_z"])
			elif attr.data_type == 'FLOAT_COLOR':
				headers.extend([f"{attr.name}_r", f"{attr.name}_g", f"{attr.name}_b", f"{attr.name}_a"])
#			elif attr.data_type == 'QUATERNION':
#				headers.extend([f"{attr.name}_rx", f"{attr.name}_ry", f"{attr.name}_rz", f"{attr.name}_rw"])
	
	return headers

def customAttributeValues(obj, i, row):
	if hasattr(obj, 'data') and obj.data is not None:
		obj = obj.data
	
	if hasattr(obj, 'attributes') and obj.attributes is not None:
		for attr in obj.attributes:
			# Only operate on attributes applied to points
			if attr.domain != "POINT" or attr.name.startswith(".") or i >= len(attr.data):
				continue
			
			# Single values (extend)
			elif attr.data_type == 'BOOLEAN':
				row.append(int(attr.data[i].value)) # Convert boolean to int (0 or 1)
			elif attr.data_type == 'INT':
				row.append(attr.data[i].value)
			if attr.data_type == 'FLOAT':
				row.append(attr.data[i].value)
			# Multiple values (append)
			elif attr.data_type == 'FLOAT2':
				vec2 = attr.data[i].vector
				row.extend([vec2.x, vec2.y])
			elif attr.data_type == 'FLOAT_VECTOR':
				vec = attr.data[i].vector
				row.extend([vec.x, vec.y, vec.z])
			elif attr.data_type == 'FLOAT_COLOR':
				color = attr.data[i].color
				row.extend([color[0], color[1], color[2], color[3]])
#			elif attr.data_type == 'QUATERNION':
#				quat = attr.data[i].quaternion
#				row.extend([quat[0], quat[1], quat[2], quat[3]])
	
	return row



# Menu items

def menu_func_import(self, context):
	self.layout.operator(ImportCSVPoints.bl_idname, text="Point Data (.csv)")

def menu_func_export(self, context):
	self.layout.operator(ExportCSVPoints.bl_idname, text="Point Data (.csv)")



# Register classes and add menu items

#classes = (ExportCSVPoints,)
classes = (ImportCSVPoints, ExportCSVPoints,)

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
