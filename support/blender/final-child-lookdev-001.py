import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view


def parse_args():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--blend-output",required=True)
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def smooth(obj):
    if getattr(obj,"data",None) and hasattr(obj.data,"polygons"):
        for poly in obj.data.polygons:
            poly.use_smooth=True
    return obj


def material(name,color,roughness=0.7,metallic=0.0,specular=0.25):
    mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError(f"Principled BSDF missing: {name}")
    bsdf.inputs["Base Color"].default_value=(*color,1.0)
    bsdf.inputs["Roughness"].default_value=roughness
    bsdf.inputs["Metallic"].default_value=metallic
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value=specular
    return mat


def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()


def uv_sphere(name,loc,scale,mat,segments=64,rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,location=loc)
    obj=bpy.context.object
    obj.name=name
    obj.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(mat)
    return smooth(obj)


def cone(name,loc,r1,r2,depth,mat,rotation=(0,0,0),vertices=64):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices,radius1=r1,radius2=r2,depth=depth,location=loc,rotation=rotation)
    obj=bpy.context.object
    obj.name=name
    obj.data.materials.append(mat)
    return smooth(obj)


def cube(name,loc,scale,mat,rotation=(0,0,0),bevel=0.02):
    bpy.ops.mesh.primitive_cube_add(location=loc,rotation=rotation)
    obj=bpy.context.object
    obj.name=name
    obj.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=obj.modifiers.new("SoftBevel","BEVEL")
        mod.width=bevel
        mod.segments=4
    obj.data.materials.append(mat)
    return obj


def curve_strand(name,points,radii,mat,bevel=0.02):
    curve=bpy.data.curves.new(name+"Curve","CURVE")
    curve.dimensions="3D"
    curve.resolution_u=12
    curve.bevel_depth=bevel
    curve.bevel_resolution=5
    curve.fill_mode="FULL"
    spline=curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points)-1)
    for bp,co,radius in zip(spline.bezier_points,points,radii):
        bp.co=co
        bp.radius=radius
        bp.handle_left_type="AUTO"
        bp.handle_right_type="AUTO"
    obj=bpy.data.objects.new(name,curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def loft(name,centers,widths,depths,mat,segments=24,subdiv=2):
    centers=[Vector(c) for c in centers]
    verts=[]
    rings=[]
    for i,center in enumerate(centers):
        if i==0:
            tangent=(centers[1]-centers[0]).normalized()
        elif i==len(centers)-1:
            tangent=(centers[-1]-centers[-2]).normalized()
        else:
            tangent=(centers[i+1]-centers[i-1]).normalized()
        perp=Vector((-tangent.z,0.0,tangent.x))
        if perp.length<1e-6:
            perp=Vector((1,0,0))
        perp.normalize()
        ring=[]
        for s in range(segments):
            a=math.tau*s/segments
            offset=perp*(math.cos(a)*widths[i])+Vector((0,math.sin(a)*depths[i],0))
            ring.append(len(verts))
            verts.append(tuple(center+offset))
        rings.append(ring)
    faces=[]
    for r in range(len(rings)-1):
        for s in range(segments):
            sn=(s+1)%segments
            faces.append((rings[r][s],rings[r][sn],rings[r+1][sn],rings[r+1][s]))
    faces.append(tuple(reversed(rings[0])))
    faces.append(tuple(rings[-1]))
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    smooth(obj)
    if subdiv:
        mod=obj.modifiers.new("OrganicSubdivision","SUBSURF")
        mod.levels=subdiv
        mod.render_levels=subdiv
    return obj


def ensure_mpfb_enabled():
    prefs=bpy.context.preferences
    for module_name in prefs.addons.keys():
        if str(module_name).split(".")[-1]=="mpfb":
            return str(module_name)
    repos=getattr(getattr(prefs,"extensions",None),"repos",[])
    for repo in repos:
        if not getattr(repo,"enabled",True):
            continue
        package=Path(str(repo.directory)).expanduser()/"mpfb"
        if package.is_dir() and (package/"blender_manifest.toml").is_file():
            module_name=f"bl_ext.{repo.module}.mpfb"
            result=bpy.ops.preferences.addon_enable(module=module_name)
            if "FINISHED" in result:
                return module_name
    raise RuntimeError("MPFB unavailable; run ./install-mpfb.command")


def configure_child(scene):
    values={
        "add_phenotype":True,
        "phenotype_gender":"female",
        "phenotype_age":"child",
        "phenotype_muscle":"minmuscle",
        "phenotype_weight":"averageweight",
        "phenotype_height":"minheight",
        "phenotype_proportions":"average",
        "phenotype_race":"asian",
        "phenotype_influence":1.0,
        "add_breast":False,
        "scale_factor":"METER",
        "mask_helpers":True,
        "detailed_helpers":True,
        "extra_vertex_groups":True,
    }
    for short,value in values.items():
        full="MPFB_NH_"+short
        if not hasattr(scene,full):
            raise RuntimeError(f"Missing MPFB scene property: {full}")
        setattr(scene,full,value)


def bounds(obj):
    depsgraph=bpy.context.evaluated_depsgraph_get()
    e=obj.evaluated_get(depsgraph)
    points=[e.matrix_world@Vector(c) for c in e.bound_box]
    lo=Vector((min(p.x for p in points),min(p.y for p in points),min(p.z for p in points)))
    hi=Vector((max(p.x for p in points),max(p.y for p in points),max(p.z for p in points)))
    return lo,hi,points


def normalize_height(obj,target=1.28):
    bpy.context.view_layer.update()
    lo,hi,_=bounds(obj)
    h=hi.z-lo.z
    obj.scale*=target/max(h,1e-6)
    bpy.context.view_layer.objects.active=obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bpy.context.view_layer.update()
    lo,_,_=bounds(obj)
    obj.location.z-=lo.z


def create_child():
    ensure_mpfb_enabled()
    configure_child(bpy.context.scene)
    before={o.name for o in bpy.data.objects}
    result=bpy.ops.mpfb.create_human()
    if "FINISHED" not in result:
        raise RuntimeError(f"MPFB create_human failed: {result}")
    if bpy.context.mode!="OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    created=[o for o in bpy.data.objects if o.name not in before and o.type=="MESH"]
    if not created:
        raise RuntimeError("MPFB created no mesh")
    base=max(created,key=lambda o:len(o.data.vertices))
    base.name="FinalChildBase"
    for o in created:
        if o!=base:
            o.hide_render=True
            o.hide_set(True)
    normalize_height(base,1.28)
    return base


def stylize_head(base):
    mesh=base.data
    zs=[v.co.z for v in mesh.vertices]
    zmin,zmax=min(zs),max(zs)
    span=zmax-zmin
    for v in mesh.vertices:
        t=(v.co.z-zmin)/max(span,1e-6)
        if t>=0.835:
            cz=zmin+span*0.91
            dz=v.co.z-cz
            v.co.x*=1.13
            v.co.y*=1.12
            v.co.z=cz+dz*1.05
        elif 0.64<=t<0.835:
            v.co.x*=0.96
    mesh.update()
    normalize_height(base,1.28)


def head_metrics(base):
    lo,hi,_=bounds(base)
    h=hi.z-lo.z
    head_c=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z+h*0.885))
    head_w=(hi.x-lo.x)*0.42
    return lo,hi,h,head_c,head_w


def add_face(base,head_c,head_w):
    skin=material("SkinAnime",(0.74,0.49,0.42),0.86,0.0,0.18)
    sclera=material("EyeWhite",(0.96,0.97,0.95),0.50)
    iris=material("EyeIris",(0.10,0.065,0.045),0.30,0.0,0.35)
    pupil=material("EyePupil",(0.005,0.006,0.008),0.20)
    catch=material("EyeCatch",(1.0,1.0,1.0),0.10)
    lash=material("Lash",(0.018,0.012,0.016),0.48)
    lip=material("Lip",(0.35,0.08,0.10),0.60)

    # Give body a soft animation skin.
    base.data.materials.clear()
    base.data.materials.append(skin)

    face_y=head_c.y-head_w*0.73
    eye_z=head_c.z+head_w*0.07
    ex=head_w*0.36
    for side,x in (("L",head_c.x-ex),("R",head_c.x+ex)):
        uv_sphere("EyeWhite_"+side,(x,face_y,eye_z),(head_w*0.19,head_w*0.045,head_w*0.23),sclera,64,32)
        uv_sphere("Iris_"+side,(x,face_y-head_w*0.042,eye_z-head_w*0.005),(head_w*0.125,head_w*0.022,head_w*0.145),iris,48,24)
        uv_sphere("Pupil_"+side,(x,face_y-head_w*0.062,eye_z),(head_w*0.052,head_w*0.010,head_w*0.070),pupil,40,20)
        uv_sphere("Catch_"+side,(x-head_w*0.04,face_y-head_w*0.074,eye_z+head_w*0.075),(head_w*0.025,head_w*0.006,head_w*0.033),catch,24,12)
        curve_strand("UpperLid_"+side,[
            (x-head_w*0.18,face_y-head_w*0.075,eye_z+head_w*0.12),
            (x,face_y-head_w*0.090,eye_z+head_w*0.21),
            (x+head_w*0.18,face_y-head_w*0.075,eye_z+head_w*0.12),
        ],[0.7,1.0,0.7],lash,head_w*0.018)

    curve_strand("Mouth",[
        (head_c.x-head_w*0.10,face_y-head_w*0.035,head_c.z-head_w*0.28),
        (head_c.x,face_y-head_w*0.045,head_c.z-head_w*0.31),
        (head_c.x+head_w*0.10,face_y-head_w*0.035,head_c.z-head_w*0.28),
    ],[0.7,1.0,0.7],lip,head_w*0.012)


def add_hair(head_c,head_w):
    hair=material("Hair",(0.018,0.014,0.019),0.43,0.0,0.40)
    cyan=material("HairRibbon",(0.38,0.72,0.77),0.68)
    gold=material("HairGold",(0.58,0.31,0.07),0.32,0.30)

    uv_sphere("HairCap",(head_c.x,head_c.y+head_w*0.10,head_c.z+head_w*0.16),(head_w*0.90,head_w*0.78,head_w*0.72),hair)
    bun_z=head_c.z+head_w*0.74
    for sign,side in ((-1,"L"),(1,"R")):
        bx=head_c.x+sign*head_w*0.62
        uv_sphere("Bun_"+side,(bx,head_c.y+head_w*0.08,bun_z),(head_w*0.30,head_w*0.27,head_w*0.26),hair,56,28)
        uv_sphere("Gold_"+side,(bx,head_c.y-head_w*0.19,bun_z+head_w*0.02),(head_w*0.055,head_w*0.035,head_w*0.055),gold,28,14)
        cube("Ribbon_"+side,(bx,head_c.y-head_w*0.16,bun_z-head_w*0.18),(head_w*0.16,head_w*0.025,head_w*0.045),cyan,rotation=(0,0,math.radians(sign*18)),bevel=head_w*0.02)

    fy=head_c.y-head_w*0.69
    strands=[
        (-0.55,-0.38,-0.22),
        (-0.30,-0.20,-0.11),
        (0.00,0.00,0.00),
        (0.30,0.20,0.11),
        (0.55,0.38,0.22),
    ]
    for i,(topx,midx,endx) in enumerate(strands):
        curve_strand("Bang_%02d"%i,[
            (head_c.x+head_w*topx,fy,head_c.z+head_w*0.64),
            (head_c.x+head_w*midx,fy-head_w*0.025,head_c.z+head_w*0.42),
            (head_c.x+head_w*endx,fy,head_c.z+head_w*0.23),
        ],[1.0,0.82,0.34],hair,head_w*0.085)

    for sign,side in ((-1,"L"),(1,"R")):
        curve_strand("SideLock_"+side,[
            (head_c.x+sign*head_w*0.72,head_c.y-head_w*0.34,head_c.z+head_w*0.45),
            (head_c.x+sign*head_w*0.82,head_c.y-head_w*0.39,head_c.z),
            (head_c.x+sign*head_w*0.72,head_c.y-head_w*0.34,head_c.z-head_w*0.38),
        ],[1.0,0.78,0.32],hair,head_w*0.065)


def add_costume(lo,hi,h):
    pale=material("HanfuPale",(0.53,0.77,0.80),0.92)
    white=material("HanfuWhite",(0.89,0.90,0.86),0.94)
    teal=material("HanfuTeal",(0.22,0.49,0.52),0.87)
    sash=material("HanfuSash",(0.34,0.64,0.66),0.84)

    cx=(lo.x+hi.x)/2
    cy=(lo.y+hi.y)/2
    # Torso / skirt sit in front of body so they read as cloth rather than skin.
    loft("RobeTorso",[
        (cx,cy-0.015,lo.z+h*0.67),
        (cx,cy-0.020,lo.z+h*0.53),
        (cx,cy-0.015,lo.z+h*0.41),
    ],[h*0.14,h*0.17,h*0.18],[h*0.08,h*0.10,h*0.11],pale,24,2)
    loft("RobeSkirt",[
        (cx,cy+0.015,lo.z+h*0.43),
        (cx,cy+0.020,lo.z+h*0.25),
        (cx,cy+0.025,lo.z+h*0.04),
    ],[h*0.18,h*0.25,h*0.32],[h*0.10,h*0.14,h*0.18],pale,28,2)

    chest_z=lo.z+h*0.63
    front_y=lo.y-h*0.012
    cube("CollarL",(cx-h*0.045,front_y,chest_z),(h*0.030,h*0.012,h*0.16),white,rotation=(0,math.radians(-8),math.radians(-20)),bevel=h*0.010)
    cube("CollarR",(cx+h*0.045,front_y-h*0.006,chest_z),(h*0.030,h*0.012,h*0.16),white,rotation=(0,math.radians(8),math.radians(20)),bevel=h*0.010)
    cube("WaistSash",(cx,cy-h*0.010,lo.z+h*0.43),(h*0.18,h*0.055,h*0.040),sash,bevel=h*0.012)
    cube("FrontPanel",(cx,front_y-h*0.010,lo.z+h*0.28),(h*0.085,h*0.012,h*0.17),teal,bevel=h*0.010)
    cube("FrontPanelWhite",(cx,front_y-h*0.018,lo.z+h*0.30),(h*0.050,h*0.010,h*0.13),white,bevel=h*0.008)

    shoulder_z=lo.z+h*0.61
    for sign,side in ((-1,"L"),(1,"R")):
        centers=[
            (cx+sign*h*0.14,cy,shoulder_z),
            (cx+sign*h*0.23,cy-h*0.005,lo.z+h*0.53),
            (cx+sign*h*0.27,cy-h*0.010,lo.z+h*0.43),
        ]
        loft("Sleeve_"+side,centers,[h*0.10,h*0.13,h*0.16],[h*0.075,h*0.09,h*0.11],pale,20,2)
        loft("Cuff_"+side,[
            (cx+sign*h*0.25,cy-h*0.015,lo.z+h*0.46),
            (cx+sign*h*0.28,cy-h*0.020,lo.z+h*0.40),
        ],[h*0.14,h*0.17],[h*0.09,h*0.11],white,20,2)


def build_background():
    ground=material("Ground",(0.075,0.045,0.030),0.97)
    dark=material("CampDark",(0.035,0.032,0.036),0.96)
    warm=material("Lantern",(0.52,0.15,0.035),0.62)
    bpy.ops.mesh.primitive_plane_add(size=12,location=(0,0,0))
    bpy.context.object.data.materials.append(ground)
    for x,z,depth in ((-1.8,1.0,2.7),(-1.2,0.75,3.1),(1.3,0.85,2.9),(1.9,1.05,3.3)):
        cone("CampSilhouette",(x,depth,z*0.5),0.10,0.07,z,dark)
    for x in (-1.7,1.7):
        cone("Pole",(x,2.2,0.8),0.025,0.025,1.6,dark)
        uv_sphere("Lantern",(x,2.2,1.45),(0.11,0.11,0.17),warm,32,16)


def collect_visual_objects(exclude):
    return [o for o in bpy.context.scene.objects if o.name not in exclude and o.type in {"MESH","CURVE"} and not o.hide_render]


def auto_frame(scene,cam,target,objects,margin=0.06):
    depsgraph=bpy.context.evaluated_depsgraph_get()
    pts=[]
    for obj in objects:
        e=obj.evaluated_get(depsgraph)
        if not getattr(e,"bound_box",None):
            continue
        pts.extend([e.matrix_world@Vector(c) for c in e.bound_box])
    if not pts:
        raise RuntimeError("No objects for final framing")
    lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
    hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
    # Crop deliberately to three-quarter portrait, not full-body technical inspection.
    target.location=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z+(hi.z-lo.z)*0.68))
    cam.location=Vector((target.location.x,lo.y-2.5,target.location.z+0.03))
    for _ in range(100):
        bpy.context.view_layer.update()
        test=[world_to_camera_view(scene,cam,p) for p in pts]
        xs=[p.x for p in test]; ys=[p.y for p in test]; zs=[p.z for p in test]
        # only require upper 78% of character group; portrait intentionally crops feet/lower hem
        if min(xs)>=margin and max(xs)<=1-margin and max(ys)<=1-margin and min(zs)>0:
            return {"x_min":float(min(xs)),"x_max":float(max(xs)),"y_max":float(max(ys)),"camera":tuple(float(v) for v in cam.location)}
        cam.location.y-=0.10
    raise RuntimeError("Final LookDev auto framing failed")


def main():
    args=parse_args()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene=bpy.context.scene
    scene.render.engine="BLENDER_EEVEE"
    scene.render.resolution_x=720
    scene.render.resolution_y=1280
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGBA"
    scene.render.image_settings.color_depth="8"
    scene.render.film_transparent=False
    scene.world.color=(0.014,0.018,0.026)

    build_background()
    background_names={o.name for o in scene.objects}

    base=create_child()
    stylize_head(base)
    lo,hi,h,head_c,head_w=head_metrics(base)
    add_face(base,head_c,head_w)
    add_hair(head_c,head_w)
    add_costume(lo,hi,h)

    # Warm sunset rim.
    bpy.ops.object.light_add(type="AREA",location=(3.0,1.2,3.1))
    rim=bpy.context.object
    rim.name="WarmSunsetRim"
    rim.data.energy=520
    rim.data.color=(1.0,0.28,0.07)
    rim.data.size=3.2
    look_at(rim,(0,0,1.0))

    # Protected cool-neutral face fill.
    bpy.ops.object.light_add(type="AREA",location=(-1.8,-3.3,2.1))
    fill=bpy.context.object
    fill.name="CoolFaceFill"
    fill.data.energy=430
    fill.data.color=(0.58,0.72,1.0)
    fill.data.size=2.4
    look_at(fill,(head_c.x,head_c.y,head_c.z))

    bpy.ops.object.light_add(type="AREA",location=(0,-3.0,2.0))
    eye=bpy.context.object
    eye.name="EyeLight"
    eye.data.energy=90
    eye.data.color=(1.0,0.82,0.70)
    eye.data.size=0.9
    look_at(eye,(head_c.x,head_c.y,head_c.z))

    target=bpy.data.objects.new("FinalLookdevTarget",None)
    bpy.context.collection.objects.link(target)

    bpy.ops.object.camera_add(location=(0,-4,1.1))
    cam=bpy.context.object
    cam.name="Camera"
    cam.data.lens=82
    cam.data.sensor_width=36.0
    cam.data.dof.use_dof=True
    cam.data.dof.focus_object=base
    cam.data.dof.aperture_fstop=2.8
    track=cam.constraints.new(type="TRACK_TO")
    track.target=target
    track.track_axis="TRACK_NEGATIVE_Z"
    track.up_axis="UP_Y"
    scene.camera=cam

    char_objects=collect_visual_objects(background_names)
    framing=auto_frame(scene,cam,target,char_objects,0.06)

    print(f"VIDEO_CREATOR_FINAL_CHILD_LOOKDEV_FRAMING_PASS framing={framing}",flush=True)

    output=Path(args.output).expanduser().resolve()
    blend=Path(args.blend_output).expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    blend.parent.mkdir(parents=True,exist_ok=True)
    scene.render.filepath=str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size<50000:
        raise RuntimeError("Final child LookDev render missing or unexpectedly small")

    print(f"VIDEO_CREATOR_FINAL_CHILD_LOOKDEV_PASS output={output}",flush=True)


if __name__=="__main__":
    main()
