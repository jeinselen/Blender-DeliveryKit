import bpy
import os

# Local imports
from . import delivery_panel
from . import io_csv_points
#from . import io_csv_position
#from . import io_volume_field
#from . import io_volume_texture



###########################################################################
# Global user preferences and UI rendering class

class DeliveryKitPreferences(bpy.types.AddonPreferences):
	bl_idname = __package__
	
	########## Delivery Panel Location ##########
	
	def update_delivery_category(self, context):
		category = bpy.context.preferences.addons[__package__].preferences.delivery_category
		try:
			bpy.utils.unregister_class(delivery_panel.DELIVERYKIT_PT_delivery)
		except RuntimeError:
			pass
		if len(category) > 0:
			delivery_panel.DELIVERYKIT_PT_delivery.bl_category = category
			bpy.utils.register_class(delivery_panel.DELIVERYKIT_PT_delivery)
	
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
			('CSV-2', 'CSV — Point Position', 'Export CSV file of the selected object\'s points in object space'),
			('CSV-3', 'CSV — Unity Coordinates', 'Export CSV file of the selected object\'s points in object XZY space')
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
# Addon registration functions
# •Define classes being registered
# •Define keymap array
# •Registration function
# •Unregistration function

classes = (DeliveryKitPreferences, DeliveryKitSettings,)

keymaps = []



def register():
	# Register classes
	for cls in classes:
		bpy.utils.register_class(cls)
	
	# Add extension settings reference
	bpy.types.Scene.delivery_kit_settings = bpy.props.PointerProperty(type=DeliveryKitSettings)
	
	# Register Sub Modules
	delivery_panel.register()
	io_csv_points.register()
	
	# Run preferences update
	# DeliveryKitPreferences.update_delivery_category(self, context)



def unregister():
	# Remove keymaps
	for km, kmi in keymaps:
		km.keymap_items.remove(kmi)
	keymaps.clear()
	
	# Remove Sub Modules
	delivery_panel.unregister()
	io_csv_points.unregister()
	
	# Remove extension settings reference
	del bpy.types.Scene.delivery_kit_settings
	
	# Deregister classes
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)



if __package__ == "__main__":
	register()
