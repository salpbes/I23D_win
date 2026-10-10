# Build a "TRELLIS-like" messy test model: thin open shells + fins + floating bits, export as glb
import bpy, bmesh, sys, math
bpy.ops.wm.read_factory_settings(use_empty=True)
me = bpy.data.meshes.new("geometry_0"); bm = bmesh.new()
# open cylinder band (paper thin, no caps), high-res
bmesh.ops.create_cone(bm, cap_ends=False, segments=256, radius1=0.5, radius2=0.5, depth=0.3)
# thin vertical spikes as open planes (fins)
for i in range(12):
    a = i/12*2*math.pi
    vs=[bm.verts.new((0.5*math.cos(a)+dx*math.sin(a)*0.04, 0.5*math.sin(a)-dx*math.cos(a)*0.04, z)) for dx,z in ((-1,0.15),(1,0.15),(0,0.45))]
    bm.faces.new(vs)
# duplicated inner faces to create non-manifold edges
geom = bmesh.ops.duplicate(bm, geom=bm.faces[:50])["geom"]
# tiny floating bits
for i in range(5):
    r = bmesh.ops.create_icosphere(bm, subdivisions=0, radius=0.003)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0.7+i*0.01,0,0))
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("geometry_0", me); bpy.context.scene.collection.objects.link(ob)
ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.export_scene.gltf(filepath=sys.argv[-1], export_format="GLB", use_selection=True)
print("faces", len(me.polygons))
