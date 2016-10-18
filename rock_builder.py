bl_info = {
    "name": "Rock Builder",
    "author": "Jake Dube",
    "version": (1, 0),
    "blender": (2, 78, 0),
    "location": "3D View > Tools > Rocks",
    "description": "Generates rocks using a technique from Zacharias Reinhardt's tutorial.",
    "wiki_url": "",
    "category": "Add Mesh",
}

from random import random

import bpy
from bpy.props import IntProperty, FloatProperty, PointerProperty
from bpy.types import Scene, Panel, Operator, PropertyGroup
from bpy.utils import register_class, unregister_class
import bmesh


# UI
class RockBuilderPanel(Panel):
    bl_label = "Rock Builder"
    bl_idname = "3D_VIEW_PT_layout_RockBuilder"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_context = "objectmode"
    bl_category = 'Rocks'

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        rock = scene.rock_gen_props

        # Generate Maze button
        row = layout.row()
        row.scale_y = 1.5
        row.operator("rock_gen.generate_rock", icon="SCULPTMODE_HLT")
        row = layout.row()
        row.scale_y = 1.5
        row.operator("rock_gen.update_rock", icon="FILE_REFRESH")
        
        box = layout.box()
        box.label("Mesh Settings")
        box.prop(rock, "random_variation")
        box.prop(rock, "elongation")
        
        box = layout.box()
        box.label("Subsurf and Bevel Settings")
        box.prop(rock, "viewport_subsurf")
        box.prop(rock, "render_subsurf")
        box.prop(rock, "bevel_width")
        
        box = layout.box()
        box.label("Displacement Settings")
        box.prop(rock, "displace_amount")
        box.prop(rock, "small_displace_amount")
        box.prop(rock, "texture_size")
        box.prop(rock, "small_texture_size")
        

def setup_big_texture(text: bpy.types.Texture):
    rock = bpy.context.scene.rock_gen_props
    
    text.type = 'CLOUDS'
    text.noise_basis = 'VORONOI_F1'
    text.noise_scale = rock.texture_size
    text.noise_type = 'HARD_NOISE'


# ensure big texture
def displace_big() -> bpy.types.Texture:
    data = bpy.data
    
    # look for pre-existing texture
    for t in data.textures:
        if t.name == "ROCK_GENERATOR_BIG":
            # comment this out to not overwrite the settings:
            setup_big_texture(t)
            return t
    # build new texture
    text = data.textures.new(name="ROCK_GENERATOR_BIG", type="CLOUDS")
    setup_big_texture(text)
    return text


def setup_small_texture(text: bpy.types.Texture):
    rock = bpy.context.scene.rock_gen_props
    
    text.type = 'CLOUDS'
    text.noise_basis = 'VORONOI_F1'
    text.noise_scale = rock.small_texture_size
    text.noise_type = 'HARD_NOISE'


# ensure small texture
def displace_small() -> bpy.types.Texture:
    data = bpy.data
    
    # look for pre-existing texture
    for t in data.textures:
        if t.name == "ROCK_GENERATOR_SMALL":
            # comment this out to not overwrite the settings:
            setup_small_texture(t)
            return t
    # build new texture
    text = data.textures.new(name="ROCK_GENERATOR_SMALL", type="CLOUDS")
    setup_small_texture(text)
    return text


# active object
def active():
    return bpy.context.scene.objects.active


def build_rock(context):
    # convenience variables
    scene = context.scene
    rock = scene.rock_gen_props
    ops = bpy.ops

    #########################################################################
    ##                         BASE MESH MODELING                          ##
    #########################################################################

    # add a new ico-sphere
    ops.mesh.primitive_ico_sphere_add(subdivisions=2, size=1)
    active()["ROCK_GENERATOR"] = True
    active().name = "Rock"

    # shade smooth
    ops.object.shade_smooth()

    # do elongation here...
    ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.resize(
        value=(rock.elongation, 1, 1), 
        constraint_axis=(True, False, False), 
        constraint_orientation='GLOBAL', 
        mirror=False, 
        proportional='DISABLED')
    # switch back to object mode
    ops.object.mode_set(mode='OBJECT')
    
    # setup mesh and bmesh
    mesh = context.object.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    
    # randomly move vertices
    for v in bm.verts:
        v.co.x += random() * rock.random_variation
        v.co.y += random() * rock.random_variation
        v.co.z += random() * rock.random_variation

    # save to mesh
    bm.to_mesh(mesh)

    # free the bmesh to prevent further access
    bm.free()

    #########################################################################
    ##                           MODIFIERS                                 ##
    #########################################################################

    # configure bevel modifier
    mod = active().modifiers.new(name="Bevel", type='BEVEL')
    mod.width = rock.bevel_width
    mod.limit_method = 'ANGLE'
    mod.show_expanded = False

    # configure subsurf modifier
    mod = active().modifiers.new(name="Subdivision Surface", type='SUBSURF')
    mod.levels = rock.viewport_subsurf
    mod.render_levels = rock.render_subsurf
    mod.show_expanded = False

    # configure big displacement modifiers
    directions = ('X', 'Y', 'Z')
    values = (1, -1)
    for d in directions:
        for v in values:
            mod = active().modifiers.new(name="Displace - {}{}".format(d, v), type='DISPLACE')
            mod.texture = displace_big()
            mod.direction = d
            mod.strength = v * rock.displace_amount
            mod.show_expanded = False

    # configure small displacement modifier
    mod = active().modifiers.new(name="Displace - Fine", type='DISPLACE')
    mod.texture = displace_small()
    mod.strength = rock.small_displace_amount
    mod.show_expanded = False


class RockBuilderOperator(Operator):
    bl_label = "Generate Rock"
    bl_idname = "rock_gen.generate_rock"
    bl_description = "Generates a rock using a method described by Zacharias Reinhardt's tutorial:\nhttp://www.blendernation.com/2016/10/16/create-realistic-looking-rocks-blender/"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        build_rock(context)
        
        return {'FINISHED'}


class RockBuilderUpdate(Operator):
    bl_label = "Update Rock"
    bl_idname = "rock_gen.update_rock"
    bl_description = "Updates selected rock"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_rock = active()
        try:
            is_rock = selected_rock.get('ROCK_GENERATOR')
        except KeyError:
            self.report({'ERROR'}, "No active rock object!")
            return {'CANCELLED'}
        if not is_rock:
            self.report({'ERROR'}, "No active rock object!")
            return {'CANCELLED'}
        
        for s in context.selected_objects:
            s.select = False
        selected_rock.select = True
        bpy.ops.object.delete(use_global=False)
        
        build_rock(context)
        
        return {'FINISHED'}


class RockGeneratorProperties(PropertyGroup):
    viewport_subsurf = IntProperty(name="Viewport Subdivisions", default=4)
    render_subsurf = IntProperty(name="Render Subdivisions", default=5)
    random_variation = FloatProperty(name="Random Variation", default=0.5)
    bevel_width = FloatProperty(name="Bevel Width", default=0.025)
    displace_amount = FloatProperty(name="Displace Amount", default=0.5)
    small_displace_amount = FloatProperty(name="Small Displace Amount", default=0.025)
    texture_size = FloatProperty(name="Texture Size", default=1.5)
    small_texture_size = FloatProperty(name="Small Texture Size", default=1.5)
    elongation = FloatProperty(name="Elongation", default=1.25)


classes = (RockBuilderPanel, RockBuilderOperator, RockBuilderUpdate, RockGeneratorProperties)


def register():
    for c in classes:
        register_class(c)
    
    Scene.rock_gen_props = PointerProperty(type=RockGeneratorProperties)


def unregister():
    for c in classes:
        unregister_class(c)
    
    del Scene.rock_gen_props
    

if __name__ == "__main__":
    register()
