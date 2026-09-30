"""Event-specific local blocking: two actors, props, reactions and camera cuts.

Run inside Blender. This remains a story preview, never an approved visual.
"""
import json
import math
import subprocess
import sys
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blender_graybox_scene import _material, _box, _sphere, _cylinder, _keyframe

args=sys.argv[sys.argv.index('--')+1:]
spec=json.loads(Path(args[0]).read_text());folder=Path(args[1]);folder.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
FPS=int(spec['fps']);D=spec['duration_seconds'];F=round(D*FPS)

def empty(name,parent=None,location=(0,0,0)):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);o.parent=parent;o.location=location;return o

def key(obj,t,location=None,rotation=None):
    _keyframe(obj,max(1,min(F,round(t*FPS)+1)),location=location,rotation=rotation)

def material(name,color):return _material(name,(*color,1))

skin=material('Skin',(.79,.58,.42));hair=material('Hair',(.055,.04,.035));eyes=material('Eyes',(.025,.03,.05))
shirt=material('DadBlue',(.18,.35,.50));pants=material('DarkTrousers',(.09,.14,.23));pink=material('ChildPink',(.68,.34,.41))
wall=material('BlueWall',(.26,.32,.41));wood=material('Wood',(.27,.22,.21));linen=material('Linen',(.59,.65,.72));glass=material('RainWindow',(.075,.13,.25));metal=material('DoorMetal',(.14,.21,.24));red=material('Red',(.68,.025,.045));light=material('Lamp',(.84,.76,.53))

def limb(name,parent,loc,upper,lower,mat):
    pivot=empty(name,parent,loc)
    _cylinder(name+'Upper',(0,0,-upper/2),.065,upper,mat,pivot)
    joint=empty(name+'Joint',pivot,(0,0,-upper))
    _sphere(name+'JointMesh',(0,0,0),(.073,.073,.073),mat,joint)
    _cylinder(name+'Lower',(0,0,-lower/2),.055,lower,mat,joint)
    tip=empty(name+'Tip',joint,(0,0,-lower))
    return pivot,joint,tip

def actor(name,child=False,location=(0,0,0),yaw=0):
    root=empty(name,location=location);root.rotation_euler.z=yaw
    if child:root.scale=(.62,.62,.62)
    body=empty(name+'Hip',root,(0,0,.91))
    _sphere(name+'Torso',(0,0,.28),(.245,.16,.34),pink if child else shirt,body)
    _sphere(name+'Belt',(0,0,.03),(.24,.16,.12),pants,body)
    _cylinder(name+'Neck',(0,0,.60),.075,.13,skin,body)
    head=empty(name+'Head',body,(0,0,.72))
    _sphere(name+'Face',(0,0,0),(.20,.18,.245),skin,head)
    _sphere(name+'Hair',(0,.025,.18),(.212,.185,.095),hair,head)
    for x in (-.083,.083):
        eye=_sphere(name+'Eye',(x,-.169,.045),(.022,.018,.032),eyes,head)
        _box(name+'Eyebrow',(x,-.173,.099),(.041,.014,.009),hair,head)
    _sphere(name+'Nose',(0,-.185,-.005),(.032,.03,.032),skin,head)
    mouth=_sphere(name+'Mouth',(0,-.176,-.086),(.036,.012,.012),eyes,head)
    if child:
        for x in (-.215,.215):_sphere(name+'Pigtail',(x,.045,.075),(.069,.074,.095),hair,head)
    arms={}
    for side,x in [('L',-.28),('R',.28)]:
        upper,elbow,hand=limb(name+'Arm'+side,body,(x,0,.50),.26,.25,pink if child else shirt)
        _sphere(name+'Hand'+side,(0,0,0),(.062,.06,.075),skin,hand)
        arms[side]=(upper,elbow,hand)
    legs={}
    for side,x in [('L',-.13),('R',.13)]:
        thigh,knee,foot=limb(name+'Leg'+side,root,(x,0,.89),.41,.39,pants)
        _sphere(name+'Shoe'+side,(0,-.06,-.04),(.075,.14,.07),pants,foot)
        legs[side]=(thigh,knee,foot)
    return dict(root=root,body=body,head=head,arms=arms,legs=legs,mouth=mouth)

def sit(a):
    for thigh,knee,_ in a['legs'].values():thigh.rotation_euler.x=-1.35;knee.rotation_euler.x=1.35

def room():
    _box('Floor',(0,.4,-.10),(3,3.3,.10),wood)
    # A real door opening, rather than a slab actors would walk through.
    _box('BackLeft',(-1.6,2.6,1.35),(1.6,.10,1.35),wall)
    _box('BackRight',(2.2,2.6,1.35),(.65,.10,1.35),wall)
    _box('DoorLintel',(.78,2.6,2.48),(.8,.10,.22),wall)
    _box('LeftWall',(-3,.7,1.35),(.1,2,1.35),wall)
    _box('Window',(-1.6,2.48,1.72),(.72,.05,.62),glass)
    for x in (-2.3,-.9,-1.6):_box('WindowFrame',(x,2.4,1.72),(.025,.045,.63),linen)
    _box('WindowCross',(-1.6,2.4,1.7),(.73,.045,.025),linen)
    for i in range(16):
        rain=_box('Rain',(-2.25+(i%8)*.18,2.39,1.2+(i//8)*.65),(.008,.008,.05),linen)
        for t in (0,D):key(rain,t,location=(rain.location.x,2.39,1.13+((i*.19+t*.35)%1.05)))
    _box('AdultBed',(-1.35,1.0,.19),(.59,1.05,.19),wood)
    _box('AdultMattress',(-1.35,1.0,.45),(.60,1.05,.08),linen)
    _box('AdultPillow',(-1.35,1.75,.59),(.44,.24,.07),linen)
    _box('ChildBed',(1.65,1.0,.13),(.40,.79,.13),wood)
    _box('ChildMattress',(1.65,1.0,.34),(.40,.79,.07),pink)
    _box('ChildPillow',(1.65,1.53,.44),(.28,.19,.05),linen)
    _box('Table',(-.18,1.36,.67),(.32,.36,.045),wood)
    for x in (-.42,.06):_box('TableLeg',(x,1.36,.32),(.025,.24,.32),wood)
    hinge=empty('DoorHinge',location=(.05,2.53,0));_box('Door',(.67,0,1.1),(.67,.045,1.1),metal,hinge)
    _sphere('Handle',(1.12,-.09,1.1),(.03,.05,.03),light,hinge)
    return hinge

def camera(start,end,target,lens=45):
    bpy.ops.object.camera_add(location=start);cam=bpy.context.object;cam.name='StoryCamera';cam.data.lens=lens
    for t,loc in ((0,start),(D,end)):
        q=(Vector(target)-Vector(loc)).to_track_quat('-Z','Y');key(cam,t,location=loc,rotation=q.to_euler())
    bpy.context.scene.camera=cam;return cam

def walk(a,start,end,begin=0,stop=None):
    stop=stop or D*.75
    key(a['root'],0,location=start);key(a['root'],begin,location=start);key(a['root'],stop,location=end);key(a['root'],D,location=end)
    period=.27 if a['root'].scale.x<1 else .36
    t=begin;i=0
    while t<stop:
        angle=.32 if i%2==0 else -.32
        for side,sign in [('L',1),('R',-1)]:
            thigh,knee,_=a['legs'][side];key(thigh,t,rotation=(angle*sign,0,0));key(knee,t,rotation=(max(0,-angle*sign*.75),0,0))
            upper,elbow,_=a['arms'][side];key(upper,t,rotation=(-angle*sign*.5,0,0));key(elbow,t,rotation=(-.15,0,0))
        key(a['body'],t,location=(0,0,.91+(i%2)*.014));t+=period;i+=1
    for parts in (a['legs'],a['arms']):
        for upper,joint,_ in parts.values():key(upper,stop,rotation=(0,0,0));key(joint,stop,rotation=(0,0,0))

act=spec['action']
fixed_modern=False
if act.startswith('modern_'):
    from blender_fixed_modern_story import build
    build(globals());fixed_modern=True
elif act=='door_leak':
    _box('CorridorFloor',(0,1,-.12),(2.5,4,.12),wall)
    _box('FireDoor',(0,2.5,1.14),(.78,.10,1.10),metal)
    for x in (-.83,.83):_box('FireDoorFrame',(x,2.5,1.18),(.055,.17,1.18),linen)
    _box('FireDoorFrameTop',(0,2.5,2.40),(.89,.17,.06),linen)
    _box('DoorGap',(0,2.37,.035),(.77,.045,.015),eyes)
    # A thin growing volume physically emerges under the door, then spreads.
    drop=_sphere('RedLiquid',(.12,2.33,.018),(.05,.04,.009),red)
    for t,scale,loc in [(0,(.04,.02,.008),(.12,2.34,.018)),(D*.4,(.15,.19,.012),(.12,2.22,.018)),(D,(.24,.48,.012),(.12,1.98,.018))]:
        drop.scale=scale;drop.keyframe_insert(data_path='scale',frame=round(t*FPS)+1);key(drop,t,location=loc)
    camera((.48,.32,.57),(.32,.58,.32),(.1,2.1,.14),47)
else:
    hinge=room()
    if act=='wake_up':
        dad=actor('Dad',location=(-1.35,.25,-.38));sit(dad)
        for t,angle in [(0,-1.17),(.9,-.35),(1.5,0),(D,0)]:key(dad['body'],t,rotation=(angle,0,0))
        upper,elbow,hand=dad['arms']['R']
        key(upper,0,rotation=(-.15,0,0));key(upper,1.6,rotation=(-1.1,0,0));key(elbow,0,rotation=(-.15,0,0));key(elbow,1.6,rotation=(-.62,0,0))
        _box('Phone',(0,-.01,-.015),(.047,.016,.095),eyes,hand)
        _box('PhoneScreen',(0,-.028,-.015),(.039,.008,.080),glass,hand)
        key(dad['head'],1.2,rotation=(0,0,0));key(dad['head'],D,rotation=(.20,0,0))
        camera((-3.1,-4.3,2.0),(-2.65,-3.6,1.85),(-1.25,.35,1.0),47)
    elif act=='child_question':
        dad=actor('Dad',location=(-1.35,.25,-.38),yaw=-.15);sit(dad)
        child=actor('Child',True,(.25,.45,0),-math.pi/2)
        upper,elbow,hand=child['arms']['R']
        for t,u,e in [(0,-.7,-.9),(.4,-1.7,-1.4),(1.0,-1.72,-1.5),(1.4,-1.60,-1.5),(D,-.05,-.1)]:key(upper,t,rotation=(u,.12,0));key(elbow,t,rotation=(e,0,0))
        key(child['head'],0,rotation=(.18,0,0));key(child['head'],D,rotation=(-.05,0,-.15))
        camera((1.7,-3,1.24),(1.35,-2.6,1.16),(-.05,.45,.93),45)
    elif act=='father_reassure':
        dad=actor('Dad',location=(-.23,.25,-.18),yaw=math.pi/2)
        for thigh,knee,_ in dad['legs'].values():thigh.rotation_euler.x=-1.0;knee.rotation_euler.x=1.25
        child=actor('Child',True,(.35,.25,0),-math.pi/2)
        key(dad['body'],0,rotation=(0,0,0));key(dad['body'],.9,rotation=(-.15,0,0))
        upper,elbow,_=dad['arms']['R'];key(upper,0,rotation=(0,0,0));key(upper,.9,rotation=(-.85,0,0));key(elbow,0,rotation=(0,0,0));key(elbow,.9,rotation=(-.25,0,0))
        key(child['head'],0,rotation=(0,0,0));key(child['head'],D,rotation=(.03,0,.16))
        camera((.6,-3.0,1.5),(.5,-2.7,1.4),(0,.25,1.0),49)
    elif act=='father_realize':
        dad=actor('Dad',location=(-.3,.35,0))
        key(dad['head'],0,rotation=(.20,0,-.2));key(dad['head'],D*.55,rotation=(-.03,0,.16));key(dad['head'],D,rotation=(-.04,0,.18))
        for obj in bpy.data.objects:
            if obj.name.startswith('DadEye') and not obj.name.startswith('DadEyebrow'):
                obj.keyframe_insert(data_path='scale',frame=1);obj.scale.z*=1.45;obj.keyframe_insert(data_path='scale',frame=round(F*.4))
        key(dad['mouth'],0,rotation=(0,0,0));dad['mouth'].keyframe_insert(data_path='scale',frame=1);dad['mouth'].scale.z*=2;dad['mouth'].keyframe_insert(data_path='scale',frame=F)
        camera((-.25,-2.35,1.7),(-.25,-1.75,1.67),(-.3,.35,1.52),58)
    elif act=='whistle_drop':
        whistle=empty('Whistle',location=(-.18,1.36,1.65))
        _sphere('WhistleBody',(0,0,0),(.125,.09,.055),red,whistle)
        _box('WhistleMouth',(.125,0,0),(.115,.055,.03),red,whistle)
        _sphere('WhistleHole',(-.02,-.085,.012),(.04,.009,.022),eyes,whistle)
        for t,z,a in [(0,1.55,0),(.42,1.55,0),(.95,.77,-.4),(1.18,.90,.2),(1.5,.78,0),(D,.78,0)]:key(whistle,t,location=(-.18,1.36,z),rotation=(0,a,0))
        camera((.65,-1.0,1.6),(.50,-.7,1.45),(-.10,1.36,.95),55)
    elif act=='room_blackout':
        dad=actor('Dad',location=(-.35,.4,0));child=actor('Child',True,(.40,.48,0))
        for a in (dad,child):
            upper,elbow,_=a['arms']['R'];key(upper,0,rotation=(0,0,0));key(upper,.45,rotation=(-.8,0,0));key(elbow,.45,rotation=(-.8,0,0));key(a['head'],0,rotation=(0,0,0));key(a['head'],.4,rotation=(-.12,0,-.1))
        cam=camera((.3,-4.7,1.7),(.3,-4.3,1.7),(.0,.45,1.0),43)
        base=Vector((.3,-4.7,1.7))
        for i in range(1,15):key(cam,i/FPS,location=base+Vector((.035*math.sin(i*2.1),0,.02*math.cos(i*2.8))))
        for mat in (skin,shirt,pants,pink,wall,wood,linen,metal):
            original=tuple(mat.diffuse_color);mat.keyframe_insert(data_path='diffuse_color',frame=1);mat.keyframe_insert(data_path='diffuse_color',frame=round(.55*FPS));mat.diffuse_color=(*[c*.22 for c in original[:3]],1);mat.keyframe_insert(data_path='diffuse_color',frame=round(.75*FPS))
    elif act=='leave_room':
        dad=actor('Dad',location=(.4,.20,0),yaw=math.pi);child=actor('Child',True,(-.30,.05,0),math.pi)
        walk(dad,(.4,.20,0),(.83,2.65,0),.05,D*.88);walk(child,(-.30,.05,0),(.60,2.25,0),.2,D*.92)
        key(hinge,0,rotation=(0,0,0));key(hinge,.85,rotation=(0,0,-1.1));key(hinge,D,rotation=(0,0,-1.1))
        camera((-.35,-4.3,1.55),(-.10,-3.8,1.55),(.60,1.6,1.0),43)
    else:raise ValueError('Unsupported story event '+act)

speaker=spec.get('voice_actor')
if speaker:
    mouth=next((o for o in bpy.data.objects if o.name==speaker+'Mouth'),None)
    if mouth:
        for t,energy in spec.get('mouth_envelope',[]):
            mouth.scale.z=.012+min(1,energy)*.040
            mouth.keyframe_insert(data_path='scale',frame=max(1,min(F,round(t*FPS)+1)))

scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE' if fixed_modern else 'BLENDER_WORKBENCH';scene.render.resolution_x=spec['width'];scene.render.resolution_y=spec['height'];scene.render.resolution_percentage=100
scene.render.fps=FPS;scene.frame_start=1;scene.frame_end=F
scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
scene.display.shading.background_type='WORLD';scene.world.color=(.055,.07,.10);scene.render.image_settings.file_format='PNG'
if fixed_modern:scene.view_settings.look='AgX - Medium High Contrast'
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'control.blend'))
frames=folder/'frames';frames.mkdir(exist_ok=True);scene.render.filepath=str(frames/'frame-');bpy.ops.render.render(animation=True)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-framerate',str(FPS),'-i',str(frames/'frame-%04d.png'),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'control.mp4')],check=True,timeout=120)
(folder/'event-report.json').write_text(json.dumps({'event':act,'phone_objects':len([o for o in bpy.data.objects if 'Phone' in o.name]),'actors':len([o for o in bpy.data.objects if o.name.endswith('_Rig') or o.name in ('Dad','Child')]),'camera':scene.camera.name,'frames':F,'renderer':'fixed_humanoid' if fixed_modern else 'primitive_story','preview_only':True},indent=2))
