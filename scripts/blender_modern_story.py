"""Modern couple blocking for local preview, using the existing articulated meshes.

The cast is bound to project IDs. This is a replaceable temporary asset set,
not a reconstruction of final character references or a production visual.
"""
import math

def build(g):
    spec=g['spec'];D=g['D'];key=g['key'];actor=g['actor'];empty=g['empty'];camera=g['camera'];walk=g['walk'];sit=g['sit']
    box=g['_box'];sphere=g['_sphere'];cylinder=g['_cylinder'];mat=g['material']
    wood=g['wood'];skin=g['skin'];hair=g['hair'];eyes=g['eyes'];linen=g['linen'];metal=g['metal']
    wall=mat('WarmWall',(.66,.69,.70));floor=mat('FloorTile',(.48,.53,.55));window=mat('DayWindow',(.49,.70,.83))
    blue=mat('ChenBlue',(.13,.32,.52));rose=mat('LinRose',(.64,.30,.27));grey=mat('ManagerGrey',(.32,.34,.37));white=mat('Document',(.92,.92,.87))
    act=spec['action'];visual=spec.get('visual','');text=spec.get('text','');casts=set(spec.get('cast_ids',[]));names={c['name']:c['id'] for c in spec.get('characters',[])}
    speaker=next((c['name'] for c in spec.get('characters',[]) if c['id']==spec.get('character_id')),None)
    actors={}
    def person(name,loc,yaw=0,seated=False):
        if names.get(name) not in casts:return None
        mesh={'陈浩':'ChenHao','林晓':'LinXiao','主管':'Supervisor'}[name]
        a=actor(mesh,location=loc,yaw=yaw);actors[name]=a
        costume={'陈浩':blue,'林晓':rose,'主管':grey}[name]
        for o in g['bpy'].data.objects:
            if o.name.startswith(mesh) and (o.name.endswith('Torso') or 'Arm' in o.name):
                if o.type=='MESH':o.data.materials.clear();o.data.materials.append(costume)
        if name=='林晓':
            sphere(mesh+'HairBack',(0,.11,.04),(.213,.14,.23),hair,a['head'])
            sphere(mesh+'HairBun',(0,.23,.13),(.08,.08,.095),hair,a['head'])
        if seated:
            sit(a)
            box(mesh+'ChairSeat',(loc[0],loc[1],.50),(.31,.29,.04),wood)
            for dx in (-.24,.24):
                for dy in (-.21,.21):box(mesh+'ChairLeg',(loc[0]+dx,loc[1]+dy,.24),(.025,.025,.24),wood)
        # Continuous small respiration remains separate from gesture/keyframes.
        for i in range(int(D*2)+2):key(a['body'],min(D,i*.5),location=(0,0,.91+.007*math.sin(i*1.6)))
        return a
    def gesture(a,amount=-.8,side='R',delay=.2):
        if not a:return
        arm,elbow,_=a['arms'][side]
        for t,r,e in [(0,0,-.12),(min(D*.35,delay+.6),amount,-.65),(D*.72,amount*.8,-.60),(D,0,-.12)]:
            key(arm,t,rotation=(r,0,.08 if side=='R' else -.08));key(elbow,t,rotation=(e,0,0))
    def react(a,worry=False):
        if not a:return
        for t,r in [(0,(.06,0,-.06)),(D*.5,(.20 if worry else -.06,0,.09)),(D,(.18 if worry else .02,0,0))]:key(a['head'],t,rotation=r)
    def phone(a):
        if not a:return
        arm,elbow,hand=a['arms']['R'];key(arm,0,rotation=(-.65,0,0));key(arm,D,rotation=(-.8,0,0));key(elbow,0,rotation=(-.95,0,0));key(elbow,D,rotation=(-1.0,0,0))
        box('Phone',(0,-.005,-.02),(.045,.015,.087),eyes,hand);box('PhoneDisplay',(0,-.023,-.02),(.037,.005,.074),window,hand)
        react(a,True)
    def table(x=0,y=0,z=.78,size=(.85,.43)):
        box('Table',(x,y,z),(size[0],size[1],.04),wood)
        for dx in (-size[0]+.08,size[0]-.08):
            for dy in (-size[1]+.08,size[1]-.08):box('TableLeg',(x+dx,y+dy,z/2),(.035,.035,z/2),wood)
    box('Floor',(0,.6,-.1),(3.5,3.2,.1),floor)
    box('BackWall',(0,2.9,1.5),(3.5,.08,1.5),wall)
    box('Window',(-1.65,2.79,1.85),(.82,.025,.62),window)
    for x in (-2.45,-1.65,-.85):box('WindowBar',(x,2.74,1.85),(.02,.025,.65),white)
    box('WindowCross',(-1.65,2.74,1.85),(.84,.025,.02),white)
    if act=='modern_office':
        table(0,.32,.78,(.87,.40))
        chen=person('陈浩',(-.55,-.60,-.34),math.pi/2,True)
        boss=person('主管',(.63,.96,-.34),-math.pi/2,True)
        box('Laptop',(.4,.45,.92),(.21,.035,.13),metal)
        paper=box('DismissalNotice',(.4,.1,.835),(.14,.20,.009),white)
        # Only the opening beat pushes the notice; later cuts preserve its position.
        if '推到' in visual:
            key(paper,0,location=(.4,.1,.835));key(paper,D*.45,location=(-.35,-.03,.835));key(paper,D,location=(-.35,-.03,.835));gesture(boss,-1.1)
        else:paper.location=(-.35,-.03,.835)
        talk=actors.get(speaker);gesture(talk,-.6)
        if '避开' in visual:react(boss,True)
        if '手机' in visual or '加班' in text or '吃什么' in text or spec.get('focus_id')=='PROP_PHONE':phone(chen)
        else:react(chen,True)
        if speaker=='陈浩' and not any(k in text for k in ('加班','随便')):
            camera((-1.50,1.80,1.70),(-1.35,1.60,1.64),(-.55,-.60,1.22),53)
        else:camera((-2.65,-4.25,2.20),(-2.35,-3.85,2.02),(0,.27,1.02),46)
    elif act=='modern_stairs':
        for i in range(6):box('StairStep',(0,.65+i*.40,.10+i*.17),(1.4,.20,.10+i*.17),linen)
        lin=person('林晓',(-.35,.40,-.34),-.12)
        if lin:sit(lin)
        paper=box('DismissalNotice',(-.20,.13,.68),(.14,.18,.01),white)
        phone(lin);react(lin,True)
        camera((1.5,-3.2,1.65),(1.2,-2.8,1.52),(-.30,.42,1.05),50)
    elif act=='modern_store':
        table(-1.2,.08,.77,(.52,.35));table(1.15,1.55,.77,(.52,.35))
        chen=person('陈浩',(-1.25,-.58,-.34),-.14,True);lin=person('林晓',(1.15,.86,-.34),.18,True)
        for z in (.48,.97,1.46):
            box('ShopShelf',(0,1,z),(.30,.60,.035),metal)
            for i in range(3):
                cylinder('ShopBottle',(-.1, .6+i*.35,z+.16),.047,.25,blue)
                box('ShopGoods',(.1,.65+i*.35,z+.13),(.07,.09,.10),rose)
        cylinder('MineralWater',(-1.2,.06,.98),.046,.30,window)
        phone(lin if speaker=='林晓' or '林晓' in visual else chen)
        react(chen,True);react(lin,True)
        if '扣在' in visual:gesture(chen,-.85)
        if speaker=='林晓':camera((2.6,-2.8,1.8),(2.4,-2.45,1.7),(.9,.6,1.12),43)
        else:camera((-2.4,-4.8,2.25),(-2.15,-4.4,2.1),(-.35,.55,1.05),43)
    elif act=='modern_door':
        box('HomeDoor',(-1.2,2.70,1.12),(.53,.09,1.12),wood)
        box('Elevator',(1.2,2.70,1.12),(.55,.08,1.12),metal)
        chen=person('陈浩',(-.70,.3,0),math.pi/2);lin=person('林晓',(.75,1.20,0),-math.pi/2)
        if '开门' in visual or '电梯' in visual:
            if lin:walk(lin,(.75,1.2,0),(.45,.36,0),.05,D*.62)
        gesture(actors.get(speaker),-.55);react(chen);react(lin)
        camera((.2,-4.8,1.80),(.16,-4.35,1.7),(0,.65,1.12),46)
    elif act in ('modern_dinner','modern_system'):
        table(0,.60,.78,(.66,.48))
        chen=person('陈浩',(-.86,.38,-.34),math.pi/2,True);lin=person('林晓',(.86,.38,-.34),-math.pi/2,True)
        for x in (-.18,.20):
            sphere('Plate',(x,.60,.84),(.16,.12,.014),white);sphere('DinnerFood',(x,.60,.86),(.11,.08,.025),rose)
        for x in (-.5,.5):sphere('Bowl',(x,.40,.85),(.075,.075,.055),white)
        gesture(actors.get(speaker),-.72)
        if '夹了一块' in visual and lin:
            gesture(lin,-1.15)
            arm,elbow,hand=lin['arms']['R'];box('Chopstick',(0,-.04,-.10),(.004,.004,.13),wood,hand)
        if act=='modern_system':
            phone(chen);react(lin)
            if chen and '锁掉' in visual:
                arm,elbow,_=chen['arms']['R'];key(arm,D*.45,rotation=(-.75,0,0));key(arm,D,rotation=(0,0,0));key(elbow,D,rotation=(-.1,0,0))
        elif '桌子下面' in visual or spec.get('focus_id')=='PROP_NOTICES':
            box('PocketNotice',(-.75,.39,.48),(.09,.016,.10),white);box('BagNotice',(.9,.40,.4),(.13,.05,.14),rose)
        camera((.4,-4.0,1.95),(.35,-3.7,1.80),(0,.52,1.0),49)
    elif act=='modern_kitchen':
        box('KitchenCounter',(0,1.30,.45),(1.25,.38,.45),wood)
        pot=empty('OldPot',location=(0,1.20,.99))
        sphere('OldPotBody',(0,0,0),(.28,.24,.10),metal,pot)
        for x in (-.32,.32):box('PotHandle',(x,0,.03),(.06,.04,.025),metal,pot)
        chen=person('陈浩',(-.83,.2,0),.3)
        phone(chen);react(chen,True)
        # Identifying numerals are genuine scene geometry, not spoken dialogue.
        bpy=g['bpy'];curve=bpy.data.curves.new('PotNumber','FONT');curve.body='1987-0416';curve.size=.055
        o=bpy.data.objects.new('PotNumber',curve);bpy.context.collection.objects.link(o);o.location=(-.18,1.04,1.07);curve.materials.append(white)
        camera((1.45,-2.65,2.45),(1.12,-2.05,2.15),(-.15,.98,1.08),54)
    else:raise ValueError('Unknown modern scene '+act)
    # Optional project-owned director framing; legacy shots retain their cameras.
    framing=spec.get('framing');focus=spec.get('focus_id','')
    if framing in ('closeup','medium','insert'):
        bpy=g['bpy'];bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
        role=next((name for name,cid in names.items() if cid==focus),None)
        a=actors.get(role)
        if framing in ('closeup','medium') and a:
            root=a['root'].matrix_world.translation;yaw=a['root'].rotation_euler.z
            distance=1.05 if framing=='closeup' else 2.1
            height=root.z+1.56 if framing=='closeup' else root.z+1.2
            target=(root.x,root.y,height)
            start=(root.x+math.sin(yaw)*distance,root.y-math.cos(yaw)*distance,height+.10)
            end=(root.x+math.sin(yaw)*(distance-.08),root.y-math.cos(yaw)*(distance-.08),height+.08)
            camera(start,end,target,55 if framing=='closeup' else 48)
        elif framing=='insert':
            prefix={'PROP_DOCUMENT':'DismissalNotice','PROP_PHONE':'PhoneDisplay','PROP_POT':'OldPotBody','PROP_NOTICES':'PocketNotice'}.get(focus)
            prop=next((o for o in bpy.data.objects if prefix and o.name.startswith(prefix)),None)
            if not prop:raise ValueError('Director insert target missing: '+focus)
            target=prop.matrix_world.translation
            if focus=='PROP_PHONE':
                forward=prop.matrix_world.to_3x3() @ g['Vector']((0,-1,0));forward.normalize()
                start=target+forward*.65+g['Vector']((.07,0,.15));end=target+forward*.58+g['Vector']((.05,0,.12))
            elif focus=='PROP_NOTICES':
                start=target+g['Vector']((0,-.8,.06));end=target+g['Vector']((0,-.7,.06))
            else:
                start=target+g['Vector']((.25,-.45,.75));end=target+g['Vector']((.20,-.4,.65))
            camera(tuple(start),tuple(end),tuple(target),50)
        elif not a and framing!='wide':raise ValueError('Director actor focus is not physically present')
    # Smooth organic surfaces, retaining flat walls/furniture and low GPU cost.
    for o in g['bpy'].data.objects:
        if o.type=='MESH' and (any(o.name.startswith(n) for n in ('ChenHao','LinXiao','Supervisor')) or o.name.startswith(('OldPotBody','DinnerFood'))):
            if 'Chair' not in o.name and 'Eyebrow' not in o.name:
                for polygon in o.data.polygons:polygon.use_smooth=True
    return actors
