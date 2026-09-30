"""Local suspense inserts for script previews; no external models or image API."""
import math
import subprocess
from PIL import Image, ImageDraw
from scripts.render_screen_mg import _font, _wrap

WIDTH, HEIGHT, FPS = 480, 854, 24


def frame(row, seconds, duration):
    image=Image.new('RGB',(WIDTH,HEIGHT),'#080e19');d=ImageDraw.Draw(image)
    for y in range(HEIGHT):
        t=y/HEIGHT
        d.line((0,y,WIDTH,y),fill=(8+int(t*8),14+int(t*10),25+int(t*10)))
    # Continuous rain, without random flicker from frame to frame.
    for i in range(58):
        x=(i*97+seconds*35)%WIDTH;y=(i*181+seconds*470)%(HEIGHT+90)-90
        d.line((x,y,x-12,y+45),fill='#253448',width=1)
    title=row.get('screen_title','剧情提示')
    label=f"{row.get('_series_title','剧情预演')[:20]} / 第 {int(row.get('_episode_id','S01E001')[-3:])} 集"
    d.text((32,108),label,font=_font(15),fill='#8293a8')
    pulse=.5+.5*math.sin(seconds*2)
    d.rounded_rectangle((26,173,454,666),radius=24,fill='#101a29',outline='#47536a',width=2)
    d.line((48,199,99,199),fill='#fa545a',width=4)
    y=225
    for text in _wrap(d,title,_font(31),380):
        d.text((48,y),text,font=_font(31),fill='#faf0ed');y+=43
    d.line((48,y+17,430,y+17),fill='#2b3e54',width=1);y+=49
    if '哨子' in title:
        x=230+int(math.sin(seconds*1.5)*4);wy=390+int(math.cos(seconds*1.5)*5)
        d.ellipse((x-56,wy-31,x+45,wy+36),fill='#d63e4a',outline='#ff7382',width=3)
        d.rounded_rectangle((x+17,wy-18,x+104,wy+8),radius=5,fill='#d63e4a')
        d.ellipse((x-22,wy-12,x+4,wy+14),fill='#180e16')
        d.arc((x-90,wy-68,x+100,wy+120),10,160,fill='#aeb8c7',width=2);y=530
    lines=row.get('screen_lines') or [row['text']]
    for i,text in enumerate(lines):
        # Reveal early enough for reading, then hold the whole card.
        if seconds < .15+i*.18:continue
        highlight=('陈念' in text or text.startswith('C ') or '提前' in text)
        for line in _wrap(d,text,_font(24),365):
            if y>625:break
            d.text((48,y),line,font=_font(24),fill='#ff777e' if highlight else '#dce5ef');y+=36
        y+=12
    d.rectangle((26,686,26+int(428*min(1,seconds/duration)),689),fill=(int(170+60*pulse),60,68))
    return image


def render_screen(row,duration,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name('pending.mp4')
    process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
        '-s',f'{WIDTH}x{HEIGHT}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(temp)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for index in range(round(duration*FPS)):
            process.stdin.write(frame(row,index/FPS,duration).tobytes())
        process.stdin.close()
        error=process.stderr.read().decode();process.stderr.close();code=process.wait(timeout=120)
        if code:raise ValueError('屏幕镜头渲染失败：'+error[-800:])
        temp.replace(path)
    except Exception:
        process.kill();process.wait();process.stderr.close();
        if not process.stdin.closed:process.stdin.close()
        temp.unlink(missing_ok=True);raise
