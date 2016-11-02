# ### BEGIN GPL LICENSE BLOCK ###
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ### END GPL LICENSE BLOCK ###

from random import random, uniform
import math

import bpy
from bpy.props import IntProperty, FloatProperty, PointerProperty, BoolProperty
from bpy.types import Scene, Panel, Operator, PropertyGroup
from bpy.utils import register_class, unregister_class
import bmesh

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

        row = layout.row()
        row.scale_y = 1.5
        row.operator("rock_gen.generate_rock", icon="SCULPTMODE_HLT")
        row = layout.row()
        row.scale_y = 1.5
        row.operator("rock_gen.update_rock", icon="FILE_REFRESH")
        
        box = layout.box()
        box.label("Mesh Settings")
        box.prop(rock, "num_rocks")
        box.prop(rock, "spacing")
        box.prop(rock, "random_variation")

        row = box.row(align=True)
        row.prop(rock, "min_elongation")
        row.prop(rock, "max_elongation")

        box = layout.box()
        box.label("Subsurf and Bevel Settings")
        box.prop(rock, "viewport_subsurf")
        box.prop(rock, "render_subsurf")
        box.prop(rock, "bevel_width")
        
        box = layout.box()
        box.label("Displacement Settings")

        row = box.row(align=True)
        row.prop(rock, "min_displace_amount")
        row.prop(rock, "max_displace_amount")

        box.prop(rock, "small_displace_amount")

        row = box.row(align=True)
        row.prop(rock, "min_texture_size")
        row.prop(rock, "max_texture_size")

        box.prop(rock, "small_texture_size")
        box.prop(rock, "new_texture")
        

def setup_big_texture(text: bpy.types.Texture):
    rock = bpy.context.scene.rock_gen_props
    
    text.type = 'CLOUDS'
    text.noise_basis = 'VORONOI_F1'
    text.noise_scale = uniform(rock.min_texture_size, rock.max_texture_size)
    text.noise_type = 'HARD_NOISE'


# ensure big texture
def displace_big() -> bpy.types.Texture:
    data = bpy.data

    if not bpy.context.scene.rock_gen_props.new_texture:
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


def build_rock(context, loc=""):
    if not loc:
        loc = bpy.context.scene.cursor_location

    # convenience variables
    scene = context.scene
    rock = scene.rock_gen_props
    ops = bpy.ops

    #########################################################################
    ##                         BASE MESH MODELING                          ##
    #########################################################################

    # add a new ico-sphere
    ops.mesh.primitive_ico_sphere_add(subdivisions=2, location=loc, size=1)
    active()["ROCK_GENERATOR"] = True
    active().name = "Rock"

    # shade smooth
    ops.object.shade_smooth()

    # do elongation here...
    ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.resize(
        value=(uniform(rock.min_elongation, rock.max_elongation), 1, 1),
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
            mod.strength = v * uniform(rock.min_displace_amount, rock.max_displace_amount)
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
        scene = context.scene
        num_rocks = scene.rock_gen_props.num_rocks
        start_location = scene.cursor_location
        space = scene.rock_gen_props.spacing
        i = 0
        j = 0
        while i < num_rocks:
            for k in range(int(math.sqrt(num_rocks))):
                if i >= num_rocks:
                    break
                build_rock(context, (start_location.x + (k * space), start_location.y + (j * space), start_location.z))
                i += 1
            j += 1
        
        return {'FINISHED'}


class RockBuilderUpdate(Operator):
    bl_label = "Update Rock"
    bl_idname = "rock_gen.update_rock"
    bl_description = "Updates active rock"
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

        # get the original transform
        orig_loc = selected_rock.location

        for s in context.selected_objects:
            s.select = False
        selected_rock.select = True
        bpy.ops.object.delete(use_global=False)
        
        build_rock(context, loc=orig_loc)
        
        return {'FINISHED'}


class RockGeneratorProperties(PropertyGroup):
    viewport_subsurf = IntProperty(name="Viewport Subdivisions", default=4, min=0, soft_max=6, max=10)
    render_subsurf = IntProperty(name="Render Subdivisions", default=5, min=0, soft_max=6, max=10)
    random_variation = FloatProperty(name="Random Variation", default=0.5, min=0)
    bevel_width = FloatProperty(name="Bevel Width", default=0.025, min=0)
    small_displace_amount = FloatProperty(name="Small Displace Amount", default=0.025, min=0)
    small_texture_size = FloatProperty(name="Small Texture Size", default=1.5, min=0)

    # new batch props
    num_rocks = IntProperty(name="Number", default=10, min=0, max=1000)

    min_elongation = FloatProperty(name="Min Elongation", default=1, min=0)
    max_elongation = FloatProperty(name="Max Elongation", default=1.5, min=0)

    min_texture_size = FloatProperty(name="Min Texture Size", default=1.25, min=0)
    max_texture_size = FloatProperty(name="Max Texture Size", default=1.75, min=0)

    min_displace_amount = FloatProperty(name="Min Displace Amount", default=0.25, min=0)
    max_displace_amount = FloatProperty(name="Max Displace Amount", default=0.75, min=0)

    new_texture = BoolProperty(name="New Texture", default=True)

    spacing = FloatProperty(name="Spacing", default=3, min=0, max=100)


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
