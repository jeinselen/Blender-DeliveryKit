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
				
				for header in headers:
					if header.endswith(("_u", "_v")):
#						base_name = header.rsplit("_", 1)[0]
						base_name = re.sub('_[uv]{1}$', '', header)
						attributes["FLOAT2"].setdefault(base_name, []).append(header)
					elif header.endswith(("_x", "_y", "_z")):
#						base_name = header.rsplit("_", 1)[0]
						base_name = re.sub('_[xyz]{1}$', '', header)
						attributes["FLOAT_VECTOR"].setdefault(base_name, []).append(header)
					elif header.endswith(("_r", "_g", "_b", "_a")):
#						base_name = header.rsplit("_", 1)[0]
						base_name = re.sub('_[rgba]{1}$', '', header)
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
				bpy.context.scene.collection.objects.link(mesh_obj)
				
				# Prepare data storage
				vertices = []
				attr_data = {attr: [] for attr in headers if attr not in vertices}
				
				# Read data
				for row in reader:
					# Read position
					pos_x = float(row.get("position_x", row.get("x", 0)))
					pos_y = float(row.get("position_y", row.get("y", 0)))
					pos_z = float(row.get("position_z", row.get("z", 0)))
					vertices.append((pos_x, pos_y, pos_z))
					
					# Collect attribute data
					for attr in headers:
						if attr not in {"position_x", "position_y", "position_z", "x", "y", "z"}:
							attr_data[attr].append(row[attr])
				
				# Assign vertex positions
				mesh_data.from_pydata(vertices, [], [])
				
				# Process attributes
				for attr_type, columns in attributes.items():
					# Multiple values
					if attr_type in {"FLOAT_COLOR", "FLOAT_VECTOR", "FLOAT2"}:
						for base_name, channels in columns.items():
							if len(channels) == 2 and attr_type == "FLOAT2":
								# FLOAT2 (u, v)
								float2_values = [
									(float(row[channels[0]]), float(row[channels[1]]))
									for row in reader
								]
								float2_attr = mesh_data.attributes.new(name=base_name, type='FLOAT2', domain='POINT')
								float2_attr.data.foreach_set("value", float2_values)
							elif len(channels) == 3 and attr_type == "FLOAT_VECTOR":
								# FLOAT_VECTOR (x, y, z)
								vector_values = [
									(float(row[channels[0]]), float(row[channels[1]]), float(row[channels[2]]))
									for row in reader
								]
								vector_attr = mesh_data.attributes.new(name=base_name, type='FLOAT_VECTOR', domain='POINT')
								vector_attr.data.foreach_set("vector", vector_values)
							elif len(channels) == 4 and attr_type == "FLOAT_COLOR":
								# FLOAT_COLOR (r, g, b, a)
								color_values = [
									(float(row[channels[0]]), float(row[channels[1]]), float(row[channels[2]]), float(row[channels[3]]))
									for row in reader
								]
								color_attr = mesh_data.attributes.new(name=base_name, type='FLOAT_COLOR', domain='POINT')
								color_attr.data.foreach_set("color", color_values)
					# Single values
					else:
						# Scalar attributes
						for attr in columns:
							values = [row[attr] for row in reader]
							name = re.sub('_[0fiuvxyzrgba]{1}$', '', attr)
							if attr_type == "BOOL":
								bool_values = [bool(int(v)) for v in values]
								bool_attr = mesh_data.attributes.new(name=name, type='BOOL', domain='POINT')
								bool_attr.data.foreach_set("value", bool_values)
							elif attr_type == "INT":
								int_values = [int(v) for v in values]
								int_attr = mesh_data.attributes.new(name=name, type='INT', domain='POINT')
								int_attr.data.foreach_set("value", int_values)
							elif attr_type == "FLOAT":
								float_values = [float(v) for v in values]
								float_attr = mesh_data.attributes.new(name=name, type='FLOAT', domain='POINT')
								float_attr.data.foreach_set("value", float_values)
				
				return {'FINISHED'}
				
				# Create Bezier curve (if data exists)
#				if any(header.startswith("bezier_") for header in headers) and any(header.startswith("bezier_left_") for header in headers) and any(header.startswith("bezier_right_") for header in headers):
#					curve_data = bpy.data.curves.new(name=obj_name, type='CURVE')
#					curve_data.dimensions = '3D'
#					spline = curve_data.splines.new(type='BEZIER')
#					
#					for row in reader:
#						if "bezier_x" in row and "bezier_y" in row and "bezier_z" in row and "bezier_left_x" in row and "bezier_left_y" in row and "bezier_left_z" in row and "bezier_right_x" in row and "bezier_right_y" in row and "bezier_right_z" in row:
#							bez_point = spline.bezier_points.add(1)
#							bez_point.co = (
#								float(row.get("bezier_x", 0)),
#								float(row.get("bezier_y", 0)),
#								float(row.get("bezier_z", 0))
#							)
#							bez_point.handle_left = (
#								float(row.get("bezier_left_x", 0)),
#								float(row.get("bezier_left_y", 0)),
#								float(row.get("bezier_left_z", 0))
#							)
#							bez_point.handle_right = (
#								float(row.get("bezier_right_x", 0)),
#								float(row.get("bezier_right_y", 0)),
#								float(row.get("bezier_right_z", 0))
#							)
#				
#				# Otherwise, create mesh
#				else:
#					# Detect position columns
#					pos_x = "position_x" if "position_x" in headers else "x"
#					pos_y = "position_y" if "position_y" in headers else "y"
#					pos_z = "position_z" if "position_z" in headers else "z"
#					
#					mesh_data = bpy.data.meshes.new(name=obj_name)
#					mesh_obj = bpy.data.objects.new(obj_name, mesh_data)
#					bpy.context.scene.collection.objects.link(mesh_obj)
#					
#					vertices = []
#					attributes = {header: [] for header in headers if header not in {pos_x, pos_y, pos_z}}
#					
#					for row in reader:
#						if pos_x in row and pos_y in row and pos_z in row:
#							vertices.append((float(row[pos_x]), float(row[pos_y]), float(row[pos_z])))
#							for attr, values in attributes.items():
#								values.append(row[attr])
#					
#					mesh_data.from_pydata(vertices, [], [])
#					
#					for attr, values in attributes.items():
#						attr_data = mesh_data.attributes.new(name=attr, type='FLOAT', domain='POINT')
#						attr_data.data.foreach_set("value", [float(v) for v in values])
#				
#				return {'FINISHED'}
		
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
