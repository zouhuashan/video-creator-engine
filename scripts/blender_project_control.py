"""Blender-side project-owned blocking renderer, never a final visual asset."""
import json
import math
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from blender_graybox_scene import _material,_box,_build_actor,_keyframe,_animate_actor,_build_camera,_linear,_build_environment

args=sys.argv[sys.argv.index('--')+1:]
spec=json.loads(Path(args[0]).read_text());directory=Path(args[1])
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
white=_material('ControlActor',(0.7,0.72,0.76,1));dark=_material('ControlDark',(0.08,0.09,0.12,1));gray=_material('ControlRoom',(0.33,0.36,0.41,1))
if spec['environment']=='ancient_courtyard':
    _build_environment(white,gray,dark)
else:
    _box('Floor',(0,0,-.13),(4.5,5,.13),gray)
    _box('BackWall',(0,4,1.6),(4.5,.12,1.6),white)
    _box('SideWall',(-4.5,0,1.6),(.12,4,1.6),white)
    _box('Window',(-2,3.85,1.85),(1,.05,.7),dark)
    _box('Door',(2,3.8,1.25),(.55,.08,1.25),dark)
    if spec['environment']=='modern_room':
        _box('Sofa',(-2,1.2,.42),(.8,1.1,.42),gray)
        _box('SofaBack',(-2,2.2,.95),(.8,.15,.5),gray)
    else:
        _box('CorridorWall',(4.5,0,1.6),(.12,4,1.6),white)
actor=_build_actor(white,dark)
root,body,head,left_arm,right_arm,left_leg,right_leg=actor
root.name=spec['character_id']+'-ControlActor'
if spec['environment']!='ancient_courtyard':
    robe=bpy.data.objects.get('Robe')
    if robe:bpy.data.objects.remove(robe,do_unlink=True)
fps=int(spec['fps']);frames=max(1,round(spec['duration_seconds']*fps))
if spec['action']=='look_phone':
    for frame,angle in [(1,0),(max(2,round(frames*.4)),-.85),(frames,-.95)]:
        _keyframe(right_arm,frame,rotation=(angle,-.08,0))
    _keyframe(head,1,rotation=(0,0,0));_keyframe(head,frames,rotation=(.2,0,0))
    _box('Phone',(0,0,-.81),(.07,.025,.13),dark,right_arm)
    _linear(right_arm);_linear(head)
else:
    spec['actor']={'start':[0,2,0],'stop':[0,0,0],'walk_start_time':0,
        'stop_time':spec['duration_seconds']*.6,'look_up_time':spec['duration_seconds']*.8,'hold_time':spec['duration_seconds']}
    _animate_actor(spec,*actor)
spec.setdefault('actor',{'start':[0,0,0],'stop':[0,0,0],'stop_time':spec['duration_seconds']*.6})
spec['camera_path']={'start':[3.7,-8,3.1],'end':[3.3,-7.6,2.95],'target':[0,0,1.3],'follow_actor':False}
_build_camera(spec)
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=spec['width'];scene.render.resolution_y=spec['height'];scene.render.resolution_percentage=100
scene.render.fps=fps;scene.frame_start=1;scene.frame_end=frames
scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True
scene.display.shading.background_type='WORLD';scene.world.color=(.045,.05,.065)
scene.render.image_settings.file_format='PNG'
bpy.ops.wm.save_as_mainfile(filepath=str(directory/'control.blend'))
frame_dir=directory/'frames';frame_dir.mkdir(exist_ok=True)
scene.render.filepath=str(frame_dir/'frame-')
bpy.ops.render.render(animation=True)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-framerate',str(fps),'-i',str(frame_dir/'frame-%04d.png'),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(directory/'control.mp4')],check=True,timeout=120)
print('PROJECT_CONTROL_COMPLETE',spec['project_id'],spec['shot_id'])
