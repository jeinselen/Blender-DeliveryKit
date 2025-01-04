import bpy
import mathutils
import numpy
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
		# Implement your import logic here
		with open(filepath, 'r') as file:
			data = file.read()
		print("CSV import data:", data)
		return {'FINISHED'}

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
		layout.label(text="General Options", icon="MESH_GRID") # MESH_GRID GROUP_VERTEX LATTICE_DATA OUTLINER_DATA_LATTICE HANDLE_VECTOR OUTLINER_DATA_POINTCLOUD POINTCLOUD_DATA POINTCLOUD_POINT OUTLINER_OB_POINTCLOUD SNAP_MIDPOINT
		layout.prop(self, "include_attributes")
		
		layout.separator(factor=1.0, type='AUTO')
		layout.label(text="Bézier Options", icon="IPO_BEZIER") # CURVE_BEZCIRCLE CURVE_BEZCURVE IPO_BEZIER HANDLE_ALIGNED HANDLE_FREE
		layout.prop(self, "relative_handles")
	
	def execute(self, context):
		return self.write(context, self.filepath)
	
	def write(self, context, filepath):
		# Get evaluated object
		obj = bpy.context.evaluated_depsgraph_get().objects.get(bpy.context.active_object.name)
		
		array = []
		
		# If the object is a curve object, try to find Bézier curves to get their handle data
		if obj and obj.type == 'CURVE':
			# Loop over all splines in the curve
			for spline in obj.data.splines:
				# Check if it's a Bézier spline
				if spline.type == 'BEZIER':
					# Array headers
					headers = ["bezier_x", "bezier_y", "bezier_z", "bezier_left_x", "bezier_left_y", "bezier_left_z", "bezier_right_x", "bezier_right_y", "bezier_right_z"]
					if self.include_attributes:
						headers = customAttributeHeaders(obj, headers)
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
						
						# Add custom attributes
						if self.include_attributes:
							coord = customAttributeValues(obj, point.index, coord)
						
						array.append(coord)
		
		# If no curves are found, treat everything like a mesh
		else:
			# Collect data with temporary mesh conversion
			headers = ["x", "y", "z"]
			if self.include_attributes:
				headers = customAttributeHeaders(obj, headers)
			
			array.append(headers)
			print(headers)
			
			# Loop over all vertices in the mesh
			for point in obj.to_mesh().vertices:
				coord = point.co
				
				# Swizzle output channels
				values = swizzleChannels(coord, self.channel_x, self.channel_y, self.channel_z)
				
				# Add custom attributes
				if self.include_attributes:
					values = customAttributeValues(obj, point.index, values)
				
				array.append(values)
				print(values)
			
			# Remove temporary mesh conversion
			obj.to_mesh_clear()
		
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
	for attr in obj.data.attributes:
		# Only operate on attributes applied to points
		if attr.domain != "POINT":
			continue
		
		if attr.name.startswith("."):
			continue
		
		if 2 >= len(attr.data):
			continue
		
#		print(attr.domain)
#		print(attr.name)
		
		# Single values
		if attr.data_type == 'FLOAT':
			headers.append(f"{attr.name}_f")
		elif attr.data_type == 'INT':
			headers.append(f"{attr.name}_i")
		elif attr.data_type == 'BOOLEAN':
			headers.append(f"{attr.name}_b")
		# Vector values
		elif attr.data_type == 'FLOAT_VECTOR':
			headers.extend([f"{attr.name}_x", f"{attr.name}_y", f"{attr.name}_z"])
		elif attr.data_type == 'FLOAT_COLOR':
			headers.extend([f"{attr.name}_r", f"{attr.name}_g", f"{attr.name}_b", f"{attr.name}_a"])
		elif attr.data_type == 'FLOAT2':
			headers.extend([f"{attr.name}_u", f"{attr.name}_v"])
#		elif attr.data_type == 'QUATERNION':
#			headers.extend([f"{attr.name}_rw", f"{attr.name}_rx", f"{attr.name}_ry", f"{attr.name}_rz"])
	return headers

def customAttributeValues(obj, i, row):
	for attr in obj.data.attributes:
		# Only operate on attributes applied to points, and only if the index exists
		if attr.domain != "POINT":
			continue
		
		if attr.name.startswith("."):
			continue
		
		if i >= len(attr.data):
			continue
		
#		print(attr.domain)
#		print(attr.name)
		
		# Single values
		if attr.data_type == 'FLOAT':
			row.append(attr.data[i].value)
		elif attr.data_type == 'INT':
			row.append(attr.data[i].value)
		elif attr.data_type == 'BOOLEAN':
			row.append(int(attr.data[i].value)) # Convert boolean to int (0 or 1)
		# Vector values
		elif attr.data_type == 'FLOAT_VECTOR':
			vec = attr.data[i].vector
			row.extend([vec.x, vec.y, vec.z])
		elif attr.data_type == 'FLOAT_COLOR':
			color = attr.data[i].color
			row.extend([color[0], color[1], color[2], color[3]])
		elif attr.data_type == 'FLOAT2':
			vec2 = attr.data[i].vector
			row.extend([vec2.x, vec2.y])
#		elif attr.data_type == 'QUATERNION':
#			quat = attr.data[i].quaternion
#			row.extend([quat[0], quat[1], quat[2], quat[3]])
	return row



# Menu items

def menu_func_import(self, context):
	self.layout.operator(ImportCSVPoints.bl_idname, text="Point Data (.csv)")

def menu_func_export(self, context):
	self.layout.operator(ExportCSVPoints.bl_idname, text="Point Data (.csv)")



# Register classes and add menu items

classes = (ExportCSVPoints,)
#classes = (ImportCSVPoints, ExportCSVPoints,)

def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	
#	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
#	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
	
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)

if __name__ == "__main__":
	register()
