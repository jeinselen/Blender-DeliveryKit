import bpy
import os
import importlib



###########################################################################
# Render Kit variables support

# Load Render Kit variable replacement function if installed
def _get_renderkit_module():
	# Find the addon module name that ends with "Launch_Render_Kit"
	for addon_key in bpy.context.preferences.addons.keys():
		if addon_key.endswith("Launch_Render_Kit"):
			try:
				# Import its render_variables submodule dynamically
				return importlib.import_module(f"{addon_key}.render_variables")
			except ImportError:
				# If that fails, stop searching (we found the addon but its structure is unexpected)
				break
	return None

def replaceVariables(scene, string):
	rv_mod = _get_renderkit_module()
	if not rv_mod or not hasattr(rv_mod, "replaceVariables"):
		return string
	try:
		return rv_mod.replaceVariables(scene, string)
	except Exception as e:
		print(f"[DeliveryKit] replaceVariables error: {e}")
		return string



###########################################################################
# Main class

# Define allowed object types
delivery_object_types = ['CURVE', 'MESH', 'META', 'SURFACE', 'FONT']
# Not all types are supported by all exporters, see the GitHub documentation for more details

class DELIVERYKIT_OT_output(bpy.types.Operator):
	bl_idname = "deliverykit.output"
	bl_label = "Deliver File"
	bl_description = "Quickly export selected objects or collection to a specified directory"
#	bl_options = {'REGISTER', 'UNDO'}
	
	def execute(self, context):
		scene = context.scene
		settings = scene.delivery_kit_settings
		
		# Set up local variables
		location = bpy.path.abspath(settings.file_location)
		format = settings.file_type
		file_format = "." + format.lower().split("-")[0] # Get only the characters before a dash to support multiple variations of a single format
		animation = True if settings.file_animation == "ANIM" else False
		static = False if animation else True
		combined = True if settings.file_grouping == "COMBINED" else False
		original_selection = list(bpy.context.selected_objects)
		original_selection_names = [obj.name for obj in original_selection]
		original_active_object = bpy.context.active_object
		original_active_name = original_active_object.name if original_active_object else ""
		active_object = original_active_object
		if original_selection and active_object not in original_selection:
			active_object = original_selection[0]
			bpy.context.view_layer.objects.active = active_object
		active_object_name = active_object.name if active_object else ""
		object_mode = active_object.mode if active_object is not None else None
		
		def restore_export_state():
			for obj in list(bpy.context.selected_objects):
				obj.select_set(False)
			for obj_name in original_selection_names:
				obj = bpy.data.objects.get(obj_name)
				if obj is not None:
					obj.select_set(True)
			if active_object_name and object_mode:
				obj = bpy.data.objects.get(active_object_name)
				if obj is not None:
					bpy.context.view_layer.objects.active = obj
					if obj.mode != object_mode:
						bpy.ops.object.mode_set(mode = object_mode)
			if original_active_name:
				obj = bpy.data.objects.get(original_active_name)
				if obj is not None:
					bpy.context.view_layer.objects.active = obj
		
		def run_export(operator, message, **kwargs):
			result = operator(**kwargs)
			if 'FINISHED' not in result:
				raise RuntimeError(message)
			return result
		
		# Create directory if it doesn't exist yet
		if not os.path.exists(location):
			os.makedirs(location)
		
		# Save then override the current mode to OBJECT
		if active_object is not None:
			bpy.ops.object.mode_set(mode = 'OBJECT')
		
		# Check if at least one object is selected, if not, convert selected collection into object selection
		selected_objects = list(bpy.context.selected_objects)
		if selected_objects:
			if active_object in selected_objects:
				file_name = active_object.name
			else:
				file_name = selected_objects[0].name
		else:
			file_name = bpy.context.collection.name
			for obj in bpy.context.collection.all_objects:
				obj.select_set(True)
		
		# Filter file name for variables using RenderKit function
		if replaceVariables:
			file_name = replaceVariables(scene, file_name)
		
		if format != "CSV-2":
			# Deselect any non-mesh objects
			for obj in bpy.context.selected_objects:
				if obj.type not in delivery_object_types:
					obj.select_set(False)
		
############################## START FILE PROCESSING LOOP ##############################
		
		try:
			# Loop through each of the selected objects
			# But only set individual selections if file export is set to individual
			# Otherwise loop once and exit (see the if statement at the very end)
			for obj in list(bpy.context.selected_objects):
				if not combined:
					# deselect everything
					for selobj in list(bpy.context.selected_objects):
						selobj.select_set(False)
					# select individual object
					obj.select_set(True)
					bpy.context.view_layer.objects.active = obj
					bpy.context.view_layer.update()
					file_name = obj.name
				
					# Filter file name for variables using RenderKit function
					if replaceVariables:
						file_name = replaceVariables(scene, file_name)
				
					# Note to future self; you probably missed the comment block just above. Please stop freaking out. When combined is true the loop is exited after the first export pass. You can stop frantically scrolling for multi-export errors, you'll just get to the end of this section and figure out the solution is already implemented. Again.
				
				
				
############################## MESH AND MATERIAL EXPORTS ##############################
				
				if "FBX" in format:
					run_export(bpy.ops.export_scene.fbx, "FBX export failed.",
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
						
						use_mesh_modifiers = True,
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
				
				# Compressed GLB for ThreeJS
				elif format == "GLB":
					run_export(bpy.ops.export_scene.gltf, "GLB export failed.",
						filepath = location + file_name + file_format,
						check_existing = False,
						export_import_convert_lighting_mode = 'SPEC',
						export_use_gltfpack = False, # Blender 5.0 fails if this is enabled
						export_format = 'GLB',
#						export_copyright = '',
						
						export_image_format = 'JPEG',
#						export_image_format = 'WEBP',
#						export_image_add_webp = False,
#						export_image_webp_fallback = False,
#						export_texture_dir = '',
						export_jpeg_quality = 75,
						export_image_quality = 75,
#						export_keep_originals = False,
						export_texcoords = True,
						export_normals = True,
						export_gn_mesh = True, # Experimental
						
						export_draco_mesh_compression_enable = True,
						export_draco_mesh_compression_level = 6,
						export_draco_position_quantization = 12,
						export_draco_normal_quantization = 10,
						export_draco_texcoord_quantization = 10,
						export_draco_color_quantization = 8,
						export_draco_generic_quantization = 8,
						
						export_tangents = False,
						export_materials = 'EXPORT',
						export_unused_images = False,
						export_unused_textures = False,
						export_vertex_color = 'MATERIAL',
						export_vertex_color_name = 'Color',
						export_all_vertex_colors = True,
						export_active_vertex_color_when_no_material = True, # This will increase file size needlessly if not managed
						export_attributes = True, # Exported attributes must start with an underscore
						use_mesh_edges = False, # Special cases may need this
						use_mesh_vertices = False, # Special cases may need this
						export_cameras = True, # Include cameras (if selected)
						use_selection = True,
						use_visible = True, # Limit to visible
						use_renderable = True, # Limit to renderable
						
						use_active_collection = False, # Selection is used instead of collections
						use_active_collection_with_nested = True,
						use_active_scene = False,
						collection = '',
						at_collection_center = False,
						
						export_extras = True, # Include additional item data
						export_yup = True,
						export_apply = static, # Should be turned on for NON ANIMATED outputs
						export_shared_accessors = False,
						
						export_current_frame = static, # Export the current frame only
						export_animations = animation,
						export_frame_range = True, # Limit to animation range
						export_frame_step = 1,
						export_force_sampling = True,
						export_sampling_interpolation_fallback = 'LINEAR',
						export_pointer_animation = False,
						export_animation_mode = 'ACTIONS',
						export_nla_strips_merged_animation_name = 'Animation',
						export_def_bones = False,
						export_hierarchy_flatten_bones = False,
						export_hierarchy_flatten_objs = False,
						export_armature_object_remove = False,
						export_leaf_bone = False,
						export_optimize_animation_size = True,
						export_optimize_animation_keep_anim_armature = True,
						export_optimize_animation_keep_anim_object = False,
						export_optimize_disable_viewport = False,
						export_negative_frame = 'SLIDE',
						export_anim_slide_to_zero = False,
						export_bake_animation = True, # Required for drivers or constraints
						export_merge_animation = 'ACTION',
						export_anim_single_armature = True,
						export_reset_pose_bones = True,
						export_rest_position_armature = True,
						export_anim_scene_split_object = True,
						export_skins = True,
						export_influence_nb = 4,
						export_all_influences = False,
						
						export_morph = True,
						export_morph_normal = True,
						export_morph_tangent = False,
						export_morph_animation = True,
						export_morph_reset_sk_data = True,
						
						export_lights = True, # Include lights
						
						export_try_sparse_sk = True,
						export_try_omit_sparse_sk = True,
						export_gpu_instances = False,
						export_action_filter = False,
						export_convert_animation_pointer = False,
						export_nla_strips = True,
						export_original_specular = False,
						will_save_settings = True,
						export_hierarchy_full_collections = False,
						export_extra_animations = False)
				
				# GLTF export for Godot Engine
				elif format == "GLTF":
					run_export(bpy.ops.export_scene.gltf, "GLTF export failed.",
						filepath = location + file_name + file_format,
						
						# Following settings generated from sample export that may or may not work
						# Very much early draft, not even WIP
						check_existing = False,
						export_import_convert_lighting_mode = 'SPEC',
						gltf_export_id = '',
						export_use_gltfpack = False,
						export_gltfpack_tc = True,
						export_gltfpack_tq = 8,
						export_gltfpack_si = 1.0,
						export_gltfpack_sa = False,
						export_gltfpack_slb = False,
						export_gltfpack_vp = 14,
						export_gltfpack_vt = 12,
						export_gltfpack_vn = 8,
						export_gltfpack_vc = 8,
						export_gltfpack_vpi = 'Integer',
						export_gltfpack_noq = True,
						export_gltfpack_kn = False,
						export_format = 'GLTF_SEPARATE',
						ui_tab = 'GENERAL',
						export_copyright = '',
						export_image_format = 'AUTO',
						export_image_add_webp = False,
						export_image_webp_fallback = False,
						export_texture_dir = '',
						export_jpeg_quality = 75,
						export_image_quality = 100,
						export_keep_originals = False,
						export_texcoords = True,
						export_normals = True,
						export_gn_mesh = True,
						export_draco_mesh_compression_enable = False,
						export_draco_mesh_compression_level = 6,
						export_draco_position_quantization = 14,
						export_draco_normal_quantization = 10,
						export_draco_texcoord_quantization = 12,
						export_draco_color_quantization = 10,
						export_draco_generic_quantization = 12,
						export_tangents = False,
						export_materials = 'EXPORT',
						export_unused_images = False,
						export_unused_textures = False,
						export_vertex_color = 'MATERIAL',
						export_vertex_color_name = 'Color',
						export_all_vertex_colors = True,
						export_active_vertex_color_when_no_material = True,
						export_attributes = True,
						use_mesh_edges = True,
						use_mesh_vertices = True,
						export_cameras = True,
						use_selection = True,
						use_visible = False,
						use_renderable = False,
						use_active_collection_with_nested = True,
						use_active_collection = False,
						use_active_scene = False,
						collection = '',
						at_collection_center = False,
						export_extras = True,
						export_yup = True,
						export_apply = True,
						export_shared_accessors = False,
						export_animations = True,
						export_frame_range = False,
						export_frame_step = 1,
						export_force_sampling = True,
						export_sampling_interpolation_fallback = 'LINEAR',
						export_pointer_animation = False,
						export_animation_mode = 'NLA_TRACKS',
						export_nla_strips_merged_animation_name = 'Animation',
						export_def_bones = False,
						export_hierarchy_flatten_bones = False,
						export_hierarchy_flatten_objs = False,
						export_armature_object_remove = False,
						export_leaf_bone = False,
						export_optimize_animation_size = True,
						export_optimize_animation_keep_anim_armature = True,
						export_optimize_animation_keep_anim_object = False,
						export_optimize_disable_viewport = False,
						export_negative_frame = 'SLIDE',
						export_anim_slide_to_zero = False,
						export_bake_animation = False,
						export_merge_animation = 'ACTION',
						export_anim_single_armature = True,
						export_reset_pose_bones = True,
						export_current_frame = False,
						export_rest_position_armature = True,
						export_anim_scene_split_object = True,
						export_skins = True,
						export_influence_nb = 4,
						export_all_influences = False,
						export_morph = True,
						export_morph_normal = True,
						export_morph_tangent = False,
						export_morph_animation = True,
						export_morph_reset_sk_data = True,
						export_lights = True,
						export_try_sparse_sk = True,
						export_try_omit_sparse_sk = False,
						export_gpu_instances = True,
						export_action_filter = False,
						export_convert_animation_pointer = False,
						export_nla_strips = True,
						export_original_specular = False,
						will_save_settings = False,
						export_hierarchy_full_collections = False,
						export_extra_animations = False,
						export_loglevel = -1)
				
				# OBJ export for Element 3D (likely deprecated soon, I don't think any of us use it anymore)
				elif format == "OBJ":
					run_export(bpy.ops.wm.obj_export, "OBJ export failed.",
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
				
				# USDA for Nvidia Omniverse
				# https://docs.blender.org/api/current/bpy.ops.wm.html#bpy.ops.wm.usd_export
				elif format == "USDA":
					run_export(bpy.ops.wm.usd_export, "USDA export failed.",
						filepath = location + file_name + file_format,
						check_existing = False, # Always overwrite existing files
						
						selected_objects_only = True, # Only export selected items
						
						export_hair = False, # This appears to be for hair _particle systems_ which should be phasing out?
						export_uvmaps = True,
						rename_uvmaps = True,
						export_mesh_colors = True,
						export_normals = True,
						export_materials = True,
						export_subdivision = 'BEST_MATCH',
						
						export_animation = animation,
						export_armatures = True,
						only_deform_bones = False,
						export_shapekeys = True,
						
						use_instancing = True,
						evaluation_mode = 'RENDER',
						generate_preview_surface = True,
						generate_materialx_network = True,
						
						convert_orientation = True,
						export_global_forward_selection = 'NEGATIVE_Z',
						export_global_up_selection = 'Y',
						export_textures_mode = 'NEW',
						overwrite_textures = True, # Always replace textures to ensure latest versions are included
						relative_paths = True,
						xform_op_mode = 'TRS',
						root_prim_path = '/root',
						
						export_custom_properties = True,
						custom_properties_namespace = 'userProperties',
						author_blender_name = True,
						convert_world_material = True,
						allow_unicode = True,
						
						export_meshes = True,
						export_lights = True,
						export_cameras = True,
						export_curves = True,
						export_points = True,
						export_volumes = True,
						
						triangulate_meshes = False,
						quad_method = 'SHORTEST_DIAGONAL',
						ngon_method = 'BEAUTY',
						merge_parent_xform = False,
						convert_scene_units = 'CENTIMETERS', # A random video on YouTube claimed it had to be centimeters
						meters_per_unit = 1.0) # A random thread in an Nvidia forum said units had to be changed from 1.0 to 100.0, but centimeters would be 0.01? IDK
						# GPT 5.1 claims it should NOT be converted to centimeters, and that Omniverse is also Z-up and nothing should be reoriented
				
				# USDZ for Apple Platforms
				elif format == "USDZ":
					run_export(bpy.ops.wm.usd_export, "USDZ export failed.",
						filepath = location + file_name + file_format,
						check_existing = False, # Changed from default
						# Removed GUI options
						selected_objects_only = True, # Changed from default
						export_animation = False, # May need to add an option for enabling animation exports depending on the project
						export_hair = False,
						export_uvmaps = True, # Need to test this: USD uses "st" as the default uv map name, and the exporter apparently doesn't convert Blender's default "UVmap" automatically?
						export_normals = True,
						export_materials = True,
						use_instancing = False,
						evaluation_mode = 'RENDER',
						generate_preview_surface = True,
#						export_textures = True,
#						overwrite_textures = True, # Changed from default
						relative_paths = True)
				
				
				
############################## MESH ONLY EXPORTS ##############################
				
				# STL for 3D Printing
				elif format == "STL":
#					batch = False if combined else True
#					output = location + file_name + file_format if combined else location
					run_export(bpy.ops.wm.stl_export, "STL export failed.",
#						filepath = output,
						filepath = location + file_name + file_format,
						check_existing = False, # Always overwrites existing files
						
						ascii_format = False,
#						use_batch = batch,
						use_batch = False,
						export_selected_objects = True,
						
						global_scale = 1000.0, # Exports the correct scale (converting from 0.001m to 1.0mm) to Cura, Orca, and Bambu Studio slicers
						use_scene_unit = False,
						
						forward_axis = 'Y',
						up_axis = 'Z',
						apply_modifiers = True)
				
				
				
############################## MESH DATA EXPORTS ##############################
				
				# CSV for Data Transport
				
				elif format == "CSV-1":
					run_export(bpy.ops.export_scene.csv_data, "No exportable objects found.",
						filepath = location + file_name + file_format,
						mode = 'POINTS',
						use_selection = True,
						batch_mode = 'OFF' if combined else 'OBJECT',
						space = settings.csv_position,
						channel_x = 'x',
						channel_y = 'y',
						channel_z = 'z')
				
				elif format == "CSV-2":
					run_export(bpy.ops.export_scene.csv_data, "CSV export failed.",
						filepath = location + file_name + file_format,
						mode = 'POSITIONS',
						use_selection = True,
						batch_mode = 'OFF' if combined else 'OBJECT',
						space = settings.csv_position,
						channel_x = 'x',
						channel_y = 'y',
						channel_z = 'z')
				
				# JSON for SplineMaker
				
				elif format == "JSON":
					run_export(bpy.ops.export_scene.spline_maker_json, "SplineMaker JSON export failed.",
						filepath = location + file_name + file_format,
						use_selection = True,
						batch_mode = 'OFF' if combined else 'OBJECT')
				
				# SVG for Rive
				
				elif format == "SVG":
					run_export(bpy.ops.export_curve.svg_bezier_nurbs, "SVG export failed.",
						filepath = location + file_name + file_format,
						tolerance = 0.01,
						coordinate_scale = 100.0,
						view_box_mode = 'SCENE_ORIGIN')
			
			
			
############################## END FILE PROCESSING LOOP ##############################
			
				# Interrupt the loop if we're exporting all objects to the same file
				if combined:
					break
			
		except RuntimeError:
			return {'CANCELLED'}
		finally:
			restore_export_state()
		
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
			show_anim = False
			show_group = True
			show_csv = False
			object_count = 0
			
			# Check if at least one object is selected
			if bpy.context.object and bpy.context.object.select_get():
				# CSV Positions can use any object; CSV Points use evaluated mesh-compatible objects
				if settings.file_type == "CSV-2":
					object_count = len(bpy.context.selected_objects)
				elif settings.file_type == "CSV-1":
					object_count = len([obj for obj in bpy.context.selected_objects if obj.type in delivery_object_types])
				
				# Geometry: count only supported meshes and curves that are not hidden
				else:
					object_count = len([obj for obj in bpy.context.selected_objects if obj.type in delivery_object_types])
				
				
				
				# Button title
				if object_count > 1 and settings.file_grouping == "COMBINED":
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
			
			# Active collection fallback
			else:
				# CSV Positions can use any object; CSV Points use evaluated mesh-compatible objects
				if settings.file_type == "CSV-2":
					object_count = len(bpy.context.collection.all_objects)
				elif settings.file_type == "CSV-1":
					object_count = len([obj for obj in bpy.context.collection.all_objects if obj.type in delivery_object_types])
				# Geometry: count only supported data types (mesh, curve, etcetera) for everything else
				else:
					object_count = len([obj for obj in bpy.context.collection.all_objects if obj.type in delivery_object_types])
				
				# Button title
				if settings.file_grouping == "COMBINED":
					button_title = bpy.context.collection.name + file_format
				else:
					button_title = str(object_count) + " files"
				
				# Button icon
				button_icon = "OUTLINER_COLLECTION"
			
			# If no usable items are found, disable the button
			# Keeping the message generic allows this to be used universally
			if object_count == 0:
				button_enable = False
				button_icon = "X"
				if settings.file_type == "CSV-2":
					button_title = "Select item"
				else:
					button_title = "Select mesh"
			
			# Specific display cases
			if settings.file_type in ("USDA", "USDZ"):
				show_anim = True
			
			if settings.file_type == "CSV-2":
				show_group = True
				show_csv = True
			
			# UI Layout
			layout = self.layout
			layout.use_property_decorate = False # No animation
			
			layout.prop(settings, 'file_location', text = '')
			layout.prop(settings, 'file_type', text = '')
			
			if show_anim:
				layout.prop(settings, 'file_animation', expand = True)
			
			if show_group:
				layout.prop(settings, 'file_grouping', expand = True)
			
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

###########################################################################
# Addon registration functions
# •Define classes being registered
# •Define keymap array
# •Registration function
# •Unregistration function
			
classes = (DELIVERYKIT_OT_output, DELIVERYKIT_PT_delivery,)

keymaps = []



def register():
	# Register classes
	for cls in classes:
		bpy.utils.register_class(cls)
	
	# Add keymaps for quick export
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
	
	# Deregister classes
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)



if __package__ == "__main__":
	register()
	
	
