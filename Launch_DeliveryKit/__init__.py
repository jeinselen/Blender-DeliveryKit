import bpy
import os

# Local imports
from .delivery_panel import DELIVERYKIT_OT_output, DELIVERYKIT_PT_delivery
from .io_csv_points import ImportCSVPoints, ExportCSVPoints
from .io_csv_position import ImportCSVPosition, ExportCSVPosition
from .io_volume_field import ImportVF, ExportVF
from .io_volume_texture import ImportVT, ExportVT



###########################################################################
# Global user preferences and UI rendering class

class DeliveryKitPreferences(bpy.types.AddonPreferences):
	bl_idname = __package__
		
	########## Colour Palette ##########
	
	def update_delivery_category(self, context):
		category = bpy.context.preferences.addons[__package__].preferences.delivery_category
		try:
			bpy.utils.unregister_class(DELIVERYKIT_PT_delivery)
		except RuntimeError:
			pass
		if len(category) > 0:
			DELIVERYKIT_PT_delivery.bl_category = category
			bpy.utils.register_class(DELIVERYKIT_PT_delivery)
			
	delivery_category: bpy.props.StringProperty(
		name="Delivery Panel",
		description="Choose a category for the panel to be placed in",
		default="Launch",
		update=update_delivery_category)
		# Consider adding search_options=(list of currently available tabs) for easier operation
	
	
	
	############################## Preferences UI ##############################
	
	# User Interface
	def draw(self, context):
		settings = context.scene.delivery_kit_settings
		
		layout = self.layout
		
		########## Delivery Panel ##########
		layout.label(text="Delivery Interface", icon="FILE") # FILE CURRENT_FILE FILE_BLEND DUPLICATE
		layout.prop(self, "delivery_category", text='Sidebar Tab')



###########################################################################
# Local project settings

class DeliveryKitSettings(bpy.types.PropertyGroup):
	file_type: bpy.props.EnumProperty(
		name = 'Pipeline',
		description = 'Sets the format for delivery output',
		items = [
			('FBX-1', 'FBX — Unity 3D', 'Export FBX binary file for Unity 3D'),
			('FBX-2', 'FBX — Unreal Engine', 'Export FBX binary file for Unreal Engine'),
			('GLB', 'GLB — ThreeJS', 'Export GLTF compressed binary file for ThreeJS'),
			('OBJ', 'OBJ — Element3D', 'Export OBJ file for VideoCopilot Element 3D'),
#			('USDZ', 'USDZ — Xcode', 'Export USDZ file for Apple platforms including Xcode'),
			(None),
			('STL', 'STL — 3D Printing', 'Export individual STL file of each selected object for 3D printing'),
			(None),
			('VF', 'VF — Unity 3D Volume Field', 'Export volume field for Unity 3D (best used with the VFX Graph)'),
			('PNG', 'PNG — 3D Texture Strip', 'Export volume field as an image strip for Godot, Unity 3D, or Unreal Engine'),
			('EXR', 'EXR — 3D Texture Strip', 'Export volume field as an image strip for Godot, Unity 3D, or Unreal Engine'),
			(None),
			('CSV-1', 'CSV — Item Position', 'Export CSV file of the selected object\'s position for all frames within the render range'),
			('CSV-2', 'CSV — Point Position', 'Export CSV file of the selected object\'s points in object space')
			],
		default = 'FBX-1')
	file_location: bpy.props.StringProperty(
		name = "Delivery Location",
		description = "Delivery location for all exported files",
		default = "//",
		maxlen = 4096,
		subtype = "DIR_PATH")
	file_grouping: bpy.props.EnumProperty(
		name = 'Grouping',
		description = 'Sets combined or individual file outputs',
		items = [
			('COMBINED', 'Combined', 'Export selection in one file'),
			('INDIVIDUAL', 'Individual', 'Export selection as individual files')
			],
		default = 'COMBINED')
	data_range: bpy.props.FloatVectorProperty(
		name='Range',
		description='Range of data to be normalised within 0-1 image values',
		size=2,
		default=(-1.0, 1.0),
		step=1,
		precision=2,
		soft_min=-1.0,
		soft_max= 1.0,
		min=-1000.0,
		max= 1000.0)
	csv_position: bpy.props.EnumProperty(
		name = 'Position',
		description = 'Sets local or world space coordinates',
		items = [
			('WORLD', 'World', 'World space'),
			('LOCAL', 'Local', 'Local object space')
			],
		default = 'WORLD')
#	csv_rotation: bpy.props.EnumProperty(
#		name = 'Rotation',
#		description = 'Sets the formatting of rotation values',
#		items = [
#			('RAD', 'Radians', 'Output rotation in radians'),
#			('DEG', 'Degrees', 'Output rotation in degrees')
#			],
#		default = 'RAD')



###########################################################################
# Import/Export menu items

def menu_func_import(self, context):
	self.layout.operator(ImportCSVPoints.bl_idname, text="Custom Format (.custom)")
	self.layout.operator(ImportCSVPosition.bl_idname, text="Custom Format (.custom)")
	self.layout.operator(ImportVF.bl_idname, text="Custom Format (.custom)")
	self.layout.operator(ImportVT.bl_idname, text="Custom Format (.custom)")

def menu_func_export(self, context):
	self.layout.operator(ExportCSVPoints.bl_idname, text="Custom Format (.custom)")
	self.layout.operator(ExportCSVPosition.bl_idname, text="Custom Format (.custom)")
	self.layout.operator(ExportVF.bl_idname, text="Custom Format (.custom)")
	self.layout.operator(ExportVT.bl_idname, text="Custom Format (.custom)")



###########################################################################
# Addon registration functions
# •Define classes being registered
# •Define keymap array
# •Registration function
# •Unregistration function

classes = (DeliveryKitPreferences, DeliveryKitSettings,
	DELIVERYKIT_OT_output, DELIVERYKIT_PT_delivery,
#	ImportCSVPoints, ExportCSVPoints,
#	ImportCSVPosition, ExportCSVPosition,
#	ImportVF, ExportVF,
#	ImportVT, ExportVT)
	ImportCSVPoints, ExportCSVPoints)

keymaps = []



def register():
	# Register classes
	for cls in classes:
		bpy.utils.register_class(cls)
	
	# Add extension settings reference
	bpy.types.Scene.delivery_kit_settings = bpy.props.PointerProperty(type=DeliveryKitSettings)
	
	# Add to import/export menu sections
#	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
#	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
	
	# Add keymaps for project versioning and viewport shading
	wm = bpy.context.window_manager
	kc = wm.keyconfigs.addon
	if kc:
		# Global export
		km = wm.keyconfigs.addon.keymaps.new(name='Window')
		kmi = km.keymap_items.new(DELIVERYKIT_OT_output.bl_idname, 'E', 'PRESS', oskey=True, alt=True, shift=True)
		keymaps.append((km, kmi))
		
		# 3D View export
		km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
		kmi = km.keymap_items.new(DELIVERYKIT_OT_output.bl_idname, 'E', 'PRESS', oskey=True, alt=True, shift=True)
		keymaps.append((km, kmi))



def unregister():
	# Remove keymaps
	for km, kmi in keymaps:
		km.keymap_items.remove(kmi)
	keymaps.clear()
	
	# Remove from import/export menu sections
#	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
#	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
	
	# Remove extension settings reference
	del bpy.types.Scene.delivery_kit_settings
	
	# Deregister classes
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)



if __package__ == "__main__":
	register()
