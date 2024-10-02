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
	
	def draw(self, context):
		layout = self.layout
		
#		layout.label(text="Output Coordinates", icon="EMPTY_AXIS") # EMPTY_AXIS EMPTY_ARROWS
#		col = layout.column(align=True)
#		row0 = col.row(align=True)
#		row0.prop(self, "channel_x", expand=True)
#		row1 = col.row(align=True)
#		row1.prop(self, "channel_y", expand=True)
#		row2 = col.row(align=True)
#		row2.prop(self, "channel_z", expand=True)
		
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
		
#		layout.separator_spacer()
		layout.separator(factor=1.0, type='AUTO')
		
		layout.label(text="Bézier Options", icon="IPO_BEZIER") # CURVE_BEZCIRCLE CURVE_BEZCURVE IPO_BEZIER HANDLE_ALIGNED HANDLE_FREE
		layout.prop(self, "relative_handles")
	
	def execute(self, context):
		return self.write(context, self.filepath)
	
	def write(self, context, filepath):
		# Get evaluated object
		obj = bpy.context.evaluated_depsgraph_get().objects.get(bpy.context.active_object.name)
		
		bezier_curve = False
		
		# If the object is a curve object, try to find Bézier curves to get their handle data
		if obj and obj.type == 'CURVE':
			# Loop over all splines in the curve
			for spline in obj.data.splines:
				# Check if it's a Bézier spline
				if spline.type == 'BEZIER':
					# Start array if not already started
					if not bezier_curve:
						array = [["bezier x","bezier y","bezier z","left x","left y","left z","right x","right y","right z"]]
					
					# Set Bézier boolean
					bezier_curve = True
					
					# Loop over all Bézier points in the spline
					for point in spline.bezier_points:
						# Get the coordinates of the control point
						coord = point.co
						# Get the coordinates of the left and right handles
						handle_left = point.handle_left - coord if self.relative_handles else point.handle_left
						handle_right = point.handle_right - coord if self.relative_handles else point.handle_right
						
						# Swizzle output channels
						coord = swizzleChannels(coord, self.channel_x, self.channel_y, self.channel_z)
						handle_left = swizzleChannels(handle_left, self.channel_x, self.channel_y, self.channel_z)
						handle_right = swizzleChannels(handle_right, self.channel_x, self.channel_y, self.channel_z)
						
						array.append([coord.x, coord.y, coord.z, handle_left.x, handle_left.y, handle_left.z, handle_right.x, handle_right.y, handle_right.z])
		
		# If no Bézier curves are found, treat everything like a mesh
		if not bezier_curve:
			# Collect data with temporary mesh conversion
			array = [["x","y","z"]]
			for v in obj.to_mesh().vertices:
				coord = v.co
				
				# Swizzle output channels
				coord = swizzleChannels(coord, self.channel_x, self.channel_y, self.channel_z)
				
				array.append(coord)
			
			# Remove temporary mesh conversion
			obj.to_mesh_clear()
		
		# Save out CSV file
		numpy.savetxt(filepath, array, delimiter=",", newline='\n', fmt='% s')
		
		return {'FINISHED'}



# Utility

def swizzleChannels(vector, x, y, z):
	output = mathutils.Vector((0.0, 0.0, 0.0))
	# I know this is a mess, but Python doesn't have nice switching, so here you go! Totally illegal usage of nested ternary notation
	output.x = vector.x if x == "x" else (-vector.x if x == "-x" else (vector.y if x == "y" else (-vector.y if x == "-y" else (vector.z if x == "z" else -vector.z))))
	output.y = vector.x if y == "x" else (-vector.x if y == "-x" else (vector.y if y == "y" else (-vector.y if y == "-y" else (vector.z if y == "z" else -vector.z))))
	output.z = vector.x if z == "x" else (-vector.x if z == "-x" else (vector.y if z == "y" else (-vector.y if z == "-y" else (vector.z if z == "z" else -vector.z))))
	return output



# Menu items

def menu_func_import(self, context):
	self.layout.operator(ImportCSVPoints.bl_idname, text="Comma Separated Values (.csv)")

def menu_func_export(self, context):
	self.layout.operator(ExportCSVPoints.bl_idname, text="Comma Separated Values (.csv)")



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
	