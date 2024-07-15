import bpy
from bpy.app.handlers import persistent
import mathutils
import struct
import numpy as np
import os

# Define allowed object types
delivery_object_types = ['CURVE', 'MESH', 'META', 'SURFACE', 'FONT']
# Not all types are supported by all exporters, see the GitHub documentation for more details

###########################################################################
# Main class

class DELIVERYKIT_OT_output(bpy.types.Operator):
	bl_idname = "deliverykit.output"
	bl_label = "Deliver File"
	bl_description = "Quickly export selected objects or collection to a specified directory"
#	bl_options = {'REGISTER', 'UNDO'}
	
	def remap(self, val, start, stop):
		val = (val - start) / (stop - start)
		return val
	
	def execute(self, context):
		settings = context.scene.delivery_kit_settings
		
		# Set up local variables
		location = bpy.path.abspath(settings.file_location)
		format = settings.file_type
		file_format = "." + format.lower().split("-")[0] # Get only the characters before a dash to support multiple variations of a single format
		combined = True if settings.file_grouping == "COMBINED" else False
		active_object = bpy.context.active_object
		
		# Create directory if it doesn't exist yet
		if not os.path.exists(location):
			os.makedirs(location)
		
		# Save then override the current mode to OBJECT
		if active_object is not None:
			object_mode = active_object.mode
			bpy.ops.object.mode_set(mode = 'OBJECT')
		
		# Check if at least one object is selected, if not, convert selected collection into object selection
		if bpy.context.object and bpy.context.object.select_get():
			file_name = active_object.name
		else:
			file_name = bpy.context.collection.name
			for obj in bpy.context.collection.all_objects:
				obj.select_set(True)
		
		if format != "CSV-1":
			# Push an undo state (seems easier than trying to re-select previously selected non-mesh objects)
			bpy.ops.ed.undo_push()
			
			# Deselect any non-mesh objects
			for obj in bpy.context.selected_objects:
				if obj.type not in delivery_object_types:
					obj.select_set(False)
		
		
		
		# MESH (REALTIME 3D)
		if file_format in ".fbx.glb.obj.usdz":
			# Push an undo state (easier than trying to re-select previously selected non-MESH objects?)
			bpy.ops.ed.undo_push()
			# Track number of undo steps to retrace after export is complete
			undo_steps = 1
			
			# Loop through each of the selected objects
			# But only set individual selections if file export is set to individual
			# Otherwise loop once and exit (see the if statement at the very end)
			for obj in bpy.context.selected_objects:
				if not combined:
					# deselect everything
					for selobj in bpy.context.selected_objects:
						selobj.select_set(False)
					# select individual object
					obj.select_set(True)
					file_name = obj.name
					# Note to future self; you probably missed the comment block just above. Please stop freaking out. When combined is true the loop is exited after the first export pass. You can stop frantically scrolling for multi-export errors, you'll just get to the end of this section and figure out the solution is already implemented. Again.
				
				if "FBX" in format:
					bpy.ops.export_scene.fbx(
						filepath = location + file_name + file_format,
						check_existing = False, # Always overwrite existing files
						use_selection = True,
						use_active_collection = False, # Collections are converted manually to object selections above
						
						axis_forward = '-Z' if format == "FBX-1" else 'X', # Unity or Unreal
						axis_up = 'Y' if format == "FBX-1" else 'Z', # Unity or Unreal
						
						global_scale = 1.0, # 1.0
						apply_unit_scale = True,
						apply_scale_options = 'FBX_SCALE_NONE', # FBX_SCALE_NONE = All Local
						use_space_transform = True,
						object_types = {'ARMATURE', 'CAMERA', 'EMPTY', 'LIGHT', 'MESH', 'OTHER'},
						bake_space_transform = True, # True (this is "!experimental!")
						
						use_mesh_modifiers = True, # Come back to this...manually trigger application of mesh modifiers and convert attributes to UV maps
						use_mesh_modifiers_render = True,
						mesh_smooth_type = 'FACE', # OFF = Normals Only
						colors_type = 'SRGB', # NONE, SRGB, LINEAR
						use_subsurf = False, # Seems unhelpful for realtime (until realtime supports live subdivision cross-platform)
						use_mesh_edges = False, # Exclude 2-point polygons
						use_triangles = True, # Seems logical if we're doing realtime
						use_custom_props = True, # Only needed if custom properties are used
						
						use_armature_deform_only = True, # True
						add_leaf_bones = False, # False
						primary_bone_axis = 'X', # X Axis
						secondary_bone_axis = 'Y', # Y Axis
						armature_nodetype = 'NULL',
						
						bake_anim = True,
						bake_anim_use_all_bones = True,
						bake_anim_use_nla_strips = True,
						bake_anim_use_all_actions = True,
						bake_anim_force_startend_keying = True, # Some recommend False, but Unity may not load animations correctly without starting keyframes
						bake_anim_step = 1.0,
						bake_anim_simplify_factor = 1.0,
						
						path_mode = 'AUTO',
						embed_textures = False,
						batch_mode = 'OFF',
						use_batch_own_dir = False,
						use_metadata = True)
					
				elif format == "GLB":
					bpy.ops.export_scene.gltf(
						filepath = location + file_name + file_format,
						check_existing = False, # Always overwrite existing files
						export_format = 'GLB',
#						export_copyright = '', # Consider adding copyright setting in preferences or scene?
						
						export_image_format = 'JPEG',
						export_texcoords = True,
						export_normals = True,
						export_gn_mesh = True,
						export_draco_mesh_compression_enable = True,
						export_draco_mesh_compression_level = 6,
						export_draco_position_quantization = 14,
						export_draco_normal_quantization = 10,
						export_draco_texcoord_quantization = 12,
						export_draco_color_quantization = 10,
						export_draco_generic_quantization = 12,
						
						use_selection = True,
						use_active_collection = False, # Collections are converted manually to object selections above
						
						export_extras = False, # Only needed if custom properties are used
						export_yup = True, # Standard Y-up orientation
						export_apply = True,
						
						export_animations = True,
						export_frame_range = True,
						export_frame_step = 1,
						export_force_sampling = True,
						
						export_def_bones = True, # Changed from default
						export_optimize_animation_size = True, # Changed from default, may cause issues with stepped animations
						
						export_lights = False,
						export_gpu_instances = True,
						will_save_settings = False)
				
				elif format == "OBJ":
					bpy.ops.wm.obj_export(
						filepath = location + file_name + file_format,
						check_existing = False, # Always overwrite existing files
						export_animation = False,
						#start_frame = bpy.context.scene.frame_start,
						#end_frame = bpy.context.scene.frame_end,
						forward_axis = 'NEGATIVE_Z',
						up_axis = 'Y',
						global_scale = 100.0,
						apply_modifiers = True,
						export_eval_mode = 'DAG_EVAL_RENDER', # Apply render modifiers, not viewport
						export_selected_objects = True, # Export only selected object(s)
						export_uv = True,
						export_normals = True,
						export_colors = False,
						export_materials = False, # Skip generation of materials
						path_mode = 'AUTO',
						export_triangulated_mesh = True, # Changed from default
						export_curves_as_nurbs = False,
						export_object_groups = False,
						export_material_groups = False,
						export_vertex_groups = False,
						export_smooth_groups = False,
						smooth_group_bitflags = False)
				
#				elif format == "USDZ":
#					bpy.ops.wm.usd_export(
#						filepath = location + file_name + file_format,
#						check_existing = False, # Changed from default
#						# Removed GUI options
#						selected_objects_only = True, # Changed from default
#						visible_objects_only = True,
#						export_animation = False, # May need to add an option for enabling animation exports depending on the project
#						export_hair = False,
#						export_uvmaps = True, # Need to test this: USD uses "st" as the default uv map name, and the exporter apparently doesn't convert Blender's default "UVmap" automatically?
#						export_normals = True,
#						export_materials = True,
#						use_instancing = False,
#						evaluation_mode = 'RENDER',
#						generate_preview_surface = True,
#						export_textures = True,
#						overwrite_textures = True, # Changed from default
#						relative_paths = True)
				
				# Interrupt the loop if we're exporting all objects to the same file
				if combined:
					break
			
			# Undo the previously completed object modifications
			for i in range(undo_steps):
				bpy.ops.ed.undo()
		
		
		
		# MESH (3D PRINTING)
		
		elif format == "STL":
			batch = 'OFF' if combined else 'OBJECT'
			output = location + file_name + file_format if combined else location
			bpy.ops.wm.stl_export(
				filepath = output,
				check_existing = False, # Always overwrites existing files
				
				ascii_format = False,
				use_batch = False,
				export_selected_objects = True,
				
				global_scale = 1.0,
				use_scene_unit = True, # Need to test this, see if it fixes scale errors in Cura
				
				forward_axis = 'Y',
				up_axis = 'Z',
				apply_modifiers = True)
		
		
		
		# VOLUME (3D TEXTURE)
		
		elif format == "VF":
			# Define the data to be saved
			fourcc = "VF_V"  # Replace with the appropriate FourCC of either 'VF_F' for value or 'VF_V' for vec3
			
			# Name of the custom attribute
			attribute_name = 'field_vector'
			
			# Get the active selected object
			obj = bpy.context.object
			
			# Ensure the selected object is a mesh with equal to or fewer than 65536 vertices and the necessary properties and attributes
			if obj and obj.type == 'MESH' and len(obj.data.vertices) <= 65536 and obj.data.get('vf_point_grid_x') is not None and obj.data.get('vf_point_grid_y') is not None and obj.data.get('vf_point_grid_z') is not None:
				# Get evaluated object
				obj = bpy.context.evaluated_depsgraph_get().objects.get(obj.name)
				
				# Check if named attribute exists
				if attribute_name in obj.data.attributes:
					# Create empty array
					array = []
					
					# For each attribute entry, collect the results
					for data in obj.data.attributes[attribute_name].data:
						# Check if the attribute includes a value
						if hasattr(data, 'value'):
							array.append(data.value)
						# Check if the attribute includes a vector
						elif hasattr(data, 'vector'):
							# Swizzle XZY order for Blender to Unity coordinate conversion
							array.append((data.vector.x, data.vector.z, data.vector.y))
						else:
							print(f"Values not found in '{attribute_name}' attribute.")
							return {'CANCELLED'}
					
					# Set array size using custom properties
					size_x = obj.data["vf_point_grid_x"]
					size_y = obj.data["vf_point_grid_z"] # Swizzle XZY order for Unity coordinate system
					size_z = obj.data["vf_point_grid_y"] # Swizzle XZY order for Unity coordinate system
					
					# Calculate the stride based on the data type
					is_float_data = fourcc[3] == 'F'
					stride = 1 if is_float_data else 3
					
					# Create a new binary file for writing
					with open(location + obj.name + file_format, 'wb') as file:
						# Write the FourCC
						file.write(struct.pack('4s', fourcc.encode('utf-8')))
						
						# Write the volume size
						file.write(struct.pack('HHH', size_x, size_y, size_z))
						
						# Write the data
						for value in array:
							if is_float_data:
								file.write(struct.pack('f', value))
							else:
								file.write(struct.pack('fff', *value))
				else:
					print(f"Selected object does not contain '{attribute_name}' values.")
					return {'CANCELLED'}
				
			else:
				print(f"Selected object is not a mesh")
				
				# Cancel processing
				return {'CANCELLED'}
		
		elif format == "PNG" or format == "EXR":
			# Name of the custom attribute
			attribute_name = 'field_vector'
			
			# Get the active selected object
			obj = bpy.context.object
			
			# Ensure the selected object is a mesh with equal to or fewer than 65536 vertices and the necessary properties and attributes
			# The actual limit for 3D textures in Unity is 2048 x 2048 x 2048 = 8,589,934,592
			# However...that would result in an image over 4 million pixels wide, and I just don't want to deal with the ramifications of that right now
			if obj and obj.type == 'MESH' and len(obj.data.vertices) <= 65536 and obj.data.get('vf_point_grid_x') is not None and obj.data.get('vf_point_grid_y') is not None and obj.data.get('vf_point_grid_z') is not None:
				# Get evaluated object
				obj = bpy.context.evaluated_depsgraph_get().objects.get(obj.name)
				
				# Check if named attribute exists
				if attribute_name in obj.data.attributes:
					# Get remapping values
					start = settings.data_range[0]
					stop = settings.data_range[1]
					
					# Create empty array
					array = []
					
					# For each attribute entry, collect the results
					for data in obj.data.attributes[attribute_name].data:
						# Check if the attribute includes a value
						if hasattr(data, 'value'):
							# Instead of nested arrays, just create a flat list of values
							val = self.remap(data.value, start, stop)
							array.append(val)
							array.append(val)
							array.append(val)
							array.append(1.0)
						# Check if the attribute includes a vector
						elif hasattr(data, 'vector'):
							# Instead of nested arrays, just create a flat list of values
							if format == 'PNG':
								array.append(self.remap(data.vector.x, start, stop))
								# Swizzle ZY order for Blender to Unity coordinate conversion
								array.append(self.remap(data.vector.z, start, stop))
								array.append(self.remap(data.vector.y, start, stop))
							else:
								array.append(data.vector.x)
								# Swizzle ZY order for Blender to Unity coordinate conversion
								array.append(data.vector.z)
								array.append(data.vector.y)
							array.append(1.0)
						else:
							print(f"Values not found in '{attribute_name}' attribute.")
							return {'CANCELLED'}
					
					# Get output sizes using custom properties
					grid_x = obj.data["vf_point_grid_x"]
					grid_y = obj.data["vf_point_grid_y"]
					grid_z = obj.data["vf_point_grid_z"]
					
					# Set image width (horizontal * depth) and height (vertical)
					# Swizzle ZY order for Unity coordinate system
					image_width = grid_x * grid_y
					image_height = grid_z
					
					# Create image
					image = bpy.data.images.new("3DtextureOutput", width=image_width, height=image_height, alpha=False, float_buffer=True, is_data=True)
					
					# Image content
					# Swizzle ZY order for Unity coordinate system
					array = np.array(array).reshape((grid_y, grid_z, grid_x, 4))
					# Flip vertical axis
					array = array[:,::-1,:]
					# Rotate
					array = np.rot90(array, axes=(0, 1))
					# Flatten into string of colour values
					image.pixels = array.flatten()
					
					# Save image
					image.filepath_raw = location + obj.name + file_format
					if format == 'PNG':
						image.file_format = 'PNG'
					else:
						image.file_format = 'OPEN_EXR'
					image.save()
				else:
					print(f"Selected object does not contain '{attribute_name}' values.")
					return {'CANCELLED'}
			else:
				print(f"Selected object is not a mesh")
				return {'CANCELLED'}
		
		
		
		# DATA (XYZ POSITIONS)
			
		elif format == "CSV-1":
			# Save timeline position
			frame_current = bpy.context.scene.frame_current
			
			# Set variables
			frame_start = bpy.context.scene.frame_start
			frame_end = bpy.context.scene.frame_end
			space = settings.csv_position
			
			for obj in bpy.context.selected_objects:
				# Collect data
				array = [["x","y","z"]]
				for i in range(frame_start, frame_end + 1):
					bpy.context.scene.frame_set(i)
					loc, rot, scale = obj.matrix_world.decompose() if space == "WORLD" else obj.matrix_local.decompose()
					array.append([loc.x, loc.y, loc.z])
				
				# Save out CSV file
				np.savetxt(
					location + obj.name + file_format,
					array,
					delimiter = ",",
					newline = '\n',
					fmt = '% s'
					)
			
			# Reset timeline position
			bpy.context.scene.frame_set(frame_current)
		
		elif format == "CSV-2":
			for obj in bpy.context.selected_objects:
				# Get evaluated object
				obj = bpy.context.evaluated_depsgraph_get().objects.get(obj.name)
				
				# Collect data with temporary mesh conversion
				array = [["x","y","z"]]
				for v in obj.to_mesh().vertices:
					array.append([v.co.x, v.co.y, v.co.z])
				
				# Remove temporary mesh conversion
				obj.to_mesh_clear()
				
				# Save out CSV file
				np.savetxt(
					location + obj.name + file_format,
					array,
					delimiter = ",",
					newline = '\n',
					fmt = '% s'
					)
		
		if format != "CSV-1":
			# Undo the previously completed non-mesh object deselection
			bpy.ops.ed.undo()
			
		# Reset to original mode
		if active_object is not None:
			bpy.ops.object.mode_set(mode = object_mode)
		
		# Done
		return {'FINISHED'}

###########################################################################
# UI rendering class

class DELIVERYKIT_PT_delivery(bpy.types.Panel):
	bl_space_type = "VIEW_3D"
	bl_region_type = "UI"
	bl_category = 'Launch'
	bl_order = 0
	bl_options = {'DEFAULT_CLOSED'}
	bl_label = "Delivery"
	bl_idname = "DELIVERYKIT_PT_delivery"
	
	@classmethod
	def poll(cls, context):
		return True
	
	def draw_header(self, context):
		try:
			layout = self.layout
		except Exception as exc:
			print(str(exc) + " | Error in Delivery Kit panel header")
	
	def draw(self, context):
		try:
			settings = context.scene.delivery_kit_settings
			
			# Set up variables
			file_format = "." + settings.file_type.lower().split("-")[0] # Get only the characters before a dash to support multiple variations of a single format
			button_enable = True
			button_icon = "FILE"
			button_title = ''
			info_box = ''
			show_group = True
			show_range = False
			show_csv = False
			object_count = 0
			
			# Check if at least one object is selected
			if bpy.context.object and bpy.context.object.select_get():
				# Volume Field: count only an active mesh with the necessary data elements
				# Does not check for named attributes, however, since that requires applying all modifiers
				if settings.file_type == "VF" or settings.file_type == "PNG" or settings.file_type == "EXR":
					obj = bpy.context.object
					# Validate object data (doesn't check if the geometry nodes modifier actually includes a named attribute)
					if obj.type == 'MESH' and len(obj.data.vertices) <= 65536 and obj.data.get('vf_point_grid_x') is not None and obj.data.get('vf_point_grid_y') is not None and obj.data.get('vf_point_grid_z') is not None and ('field_vector' in obj.data.attributes or 'NODES' in [modifier.type for modifier in obj.modifiers]):
						object_count = 1
#						info_box = 'Volume export requires,"field_vector" attribute in,Geometry Node modifier'
						if settings.file_type == "PNG" or settings.file_type == "EXR":
							info_box = 'Columns: ' + str(obj.data["vf_point_grid_y"])
					else:
						info_box = 'Volume export requires:,mesh with <=65536 points,"vf_point_grid..." properties,"field_vector" attribute'
				# CSV: count any items
				elif settings.file_type == "CSV-1":
					object_count = len(bpy.context.selected_objects)
				# Geometry: count only supported meshes and curves that are not hidden
				else:
					object_count = len([obj for obj in bpy.context.selected_objects if obj.type in delivery_object_types])
				
				# Button title
				if (object_count > 1 and settings.file_grouping == "COMBINED" and not (settings.file_type == "CSV-1" or settings.file_type == "CSV-2")):
					button_title = bpy.context.active_object.name + file_format
				elif object_count == 1:
					if bpy.context.active_object.type not in delivery_object_types and settings.file_grouping == "INDIVIDUAL":
						for obj in bpy.context.selected_objects:
							if obj.type in delivery_object_types:
								button_title = obj.name + file_format
					else:
						button_title = bpy.context.active_object.name + file_format
				else:
					button_title = str(object_count) + " files"
				
				# Button icon
				button_icon = "OUTLINER_OB_MESH"
			
			# Active collection fallback (except for Volume Field)
			elif not (settings.file_type == "VF" or settings.file_type == "PNG" or settings.file_type == "EXR"):
				# Volume Field: requires an active mesh object, collections are not supported
				# CSV-1: count any items within the collection
				if settings.file_type == "CSV-1":
					object_count = len(bpy.context.collection.all_objects)
				# Geometry: count only supported data types (mesh, curve, etcetera) for everything else
				else:
					object_count = len([obj for obj in bpy.context.collection.all_objects if obj.type in delivery_object_types])
				
				# Button title
				if settings.file_grouping == "COMBINED" and not (settings.file_type == "CSV-1" or settings.file_type == "CSV-2"):
					button_title = bpy.context.collection.name + file_format
				else:
					button_title = str(object_count) + " files"
				
				# Button icon
				button_icon = "OUTLINER_COLLECTION"
			
			# If no usable items (CSV-1) or meshes (everything else) are found, disable the button
			# Keeping the message generic allows this to be used universally
			if object_count == 0:
				button_enable = False
				button_icon = "X"
				if settings.file_type == "CSV-1":
					button_title = "Select item"
				else:
					button_title = "Select mesh"
			
			# Specific display cases
			if settings.file_type == "VF" or settings.file_type == "PNG" or settings.file_type == "EXR":
				show_group = False
				show_csv = False
			
			if settings.file_type == "PNG":
				show_range = True
			
			if settings.file_type == "CSV-1":
				show_group = False
				show_csv = True
			
			if settings.file_type == "CSV-2":
				show_group = False
				show_csv = False
			
			# UI Layout
			layout = self.layout
			layout.use_property_decorate = False # No animation
			
			layout.prop(settings, 'file_location', text = '')
			layout.prop(settings, 'file_type', text = '')
			
			if show_group:
				layout.prop(settings, 'file_grouping', expand = True)
			
			if show_range:
				layout.prop(settings, 'data_range')
			
			if show_csv:
				layout.prop(settings, 'csv_position', expand = True)
			
			if button_enable:
				layout.operator(DELIVERYKIT_OT_output.bl_idname, text = button_title, icon = button_icon)
			else:
				disabled = layout.row()
				disabled.active = False
				disabled.enabled = False
				disabled.operator(DELIVERYKIT_OT_output.bl_idname, text = button_title, icon = button_icon)
			
			if info_box:
				box = layout.box()
				col = box.column(align=True)
				for line in info_box.split(','):
					col.label(text=line)
			
		except Exception as exc:
			print(str(exc) + " | Error in Delivery Kit panel")
			