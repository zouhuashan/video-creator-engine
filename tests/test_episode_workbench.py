import io
import json
import shutil
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from types import SimpleNamespace
from scripts import episode_workbench as w, project_shot_workflow as shots
import scripts.web_server as web


class EpisodeWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'novel-a';self.project.mkdir()
        for relative,value in {
            'novel-anime-project.json':{'episodes':[{'id':'S01E001'},{'id':'S01E002'}]},
            'story-bible/characters/index.json':{'characters':[{'id':'CHAR-DAD','name':'陈默'},{'id':'CHAR-CHILD','name':'念念'},{'id':'FALSE-CHAR','name':'十四楼'}]},
            'production/character-corrections.json':{'archived_ids':['FALSE-CHAR'],'characters':{'CHAR-CHILD':{'name':'陈念'}}},
            'storyboard/shot-breakdown.json':{'scene_breakdowns':[{'scene_id':'OLD-SCENE','episode_id':'S01E001','shots':[{'id':'OLD-SHOT'}]},{'scene_id':'OTHER-SCENE','episode_id':'S01E002','shots':[{'id':'OTHER-SHOT'}]}]},
        }.items():w.write_json(self.project/relative,value)
        self.row={'id':'SHOT-S01E001-WB001','speaker_id':'NARRATOR','text':'死亡名单上，出现了女儿的名字。','visual':'死亡名单特写','duration_seconds':1,'render_kind':'screen','screen_title':'死亡名单','screen_lines':['陈念 · 7岁'],'environment':'modern_room','action':'look_phone'}
        self.payload={'title':'死亡名单上的女儿','shots':[self.row],'expected_revision':0}

    def save(self,**change):return w.save_script(self.project,'S01E001',{**self.payload,**change})

    def test_optimistic_revision_noop_and_history(self):
        first=self.save();self.assertEqual(first['script']['revision'],1)
        with self.assertRaisesRegex(ValueError,'刷新'):self.save()
        same=self.save(expected_revision=1);self.assertEqual(same['script']['revision'],1)
        second=self.save(expected_revision=1,title='新标题');self.assertEqual(second['script']['revision'],2)
        self.assertEqual(len(list((w.directory(self.project,'S01E001')/'revisions').glob('*.json'))),2)

    def test_invalid_speaker_id_timing_and_episode_are_blocked(self):
        for change in ({'speaker_id':'FALSE-CHAR'},{'speaker_id':'OTHER-PROJECT'},{'id':'SHOT-S01E002-WB001'},{'duration_seconds':float('nan')},{'duration_seconds':True},{'text':''},{'render_kind':'cloud'},{'cast_ids':['OTHER-PROJECT']},{'cast_ids':['NARRATOR']}):
            with self.assertRaises(ValueError):self.save(shots=[{**self.row,**change}])
        with self.assertRaises(ValueError):w.load_script(self.project,'../S01E001')
        with self.assertRaises(ValueError):w.load_script(self.project,'S01E099')

    def test_overlay_replaces_only_edited_episode_and_keeps_legacy(self):
        w.write_json(shots.state_path(self.project),{'selected_shot_id':'OLD-SHOT','bindings':{}})
        self.save();catalog=shots.inventory(self.project)
        self.assertEqual(shots.selected_id(self.project),'SHOT-S01E001-WB001')
        self.assertEqual([s['id'] for s in catalog['shots']],['SHOT-S01E001-WB001','OTHER-SHOT'])
        self.assertEqual([c['name'] for c in catalog['characters']],['陈默','陈念'])
        self.assertIn('OLD-SHOT',(self.project/'storyboard/shot-breakdown.json').read_text())

    def test_edit_invalidates_audio_master_and_review_but_retains_media(self):
        first=self.save();folder=w.directory(self.project,'S01E001');(folder/'old.mp4').write_bytes(b'old')
        (self.project/'voice.wav').write_bytes(b'voice')
        sig=first['script']['signature']
        w.write_json(folder/'audio.json',{'script_signature':sig,'lines':[{'path':'voice.wav','shot_id':self.row['id'],'clip_duration':2}]})
        w.write_json(folder/'job.json',{'status':'COMPLETED','output':'production/episodes/S01E001/old.mp4','script_signature':sig})
        w.write_json(folder/'preview-review.json',{'status':'PASS','script_signature':sig})
        self.assertTrue(w.inventory(self.project,'S01E001')['job']['ready'])
        changed=self.save(expected_revision=1,shots=[{**self.row,'text':'修改过的旁白。'}])
        self.assertEqual(changed['job']['status'],'STALE');self.assertFalse(changed['audio_ready'])
        self.assertEqual(changed['preview_review']['status'],'PENDING');self.assertTrue((folder/'old.mp4').is_file())

    def test_final_requires_human_check_and_current_visual(self):
        self.save()
        with self.assertRaisesRegex(ValueError,'声音'):w.start(self.project,'S01E001',{'mode':'final','expected_revision':1})
        with self.assertRaisesRegex(ValueError,'观看'):w.review_preview(self.project,'S01E001',{'job_id':'fake','story_checked':True,'voice_checked':True,'subtitles_checked':True})
        self.assertFalse(w.inventory(self.project,'S01E001')['can_assemble_final'])

    def test_resume_rejects_changed_inputs_and_cross_process_active_owner(self):
        self.save();folder=w.directory(self.project,'S01E001')
        w.write_json(folder/'job.json',{'mode':'final','provider':'kokoro_local','script_signature':'OLD'})
        with self.assertRaisesRegex(ValueError,'变化'):w.start(self.project,'S01E001',{'resume':True,'expected_revision':1})
        import os
        w.write_json(folder/'job.json',{'status':'RUNNING','owner_pid':os.getpid()})
        with self.assertRaisesRegex(ValueError,'正在生成'):self.save(expected_revision=1)
        with self.assertRaisesRegex(ValueError,'生成中'):w.start(self.project,'S01E001',{'expected_revision':1})

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required for real render')
    def test_real_local_screen_voice_subtitle_assembly_and_audio_reuse(self):
        self.save()
        out=io.BytesIO()
        with wave.open(out,'wb') as voice:
            voice.setnchannels(1);voice.setsampwidth(2);voice.setframerate(8000);voice.writeframes(b'\0\0'*4000)
        with patch.object(w.KokoroSherpaTTS,'synthesize',return_value=SimpleNamespace(audio=out.getvalue())) as synth:
            data=w.start(self.project,'S01E001',{'expected_revision':1})
            for _ in range(300):
                time.sleep(.025);data=w.inventory(self.project,'S01E001')
                if not data['job']['active']:break
            self.assertEqual(data['job']['status'],'COMPLETED',data['job'].get('error'))
            job=data['job'];self.assertTrue(job['ready']);self.assertEqual(job['human_review'],'PENDING')
            qc=w.read(self.project/job['qc']);self.assertAlmostEqual(qc['duration'],data['audio']['duration'],delta=.1)
            self.assertIn('剧情预演',(self.project/job['subtitles']).read_text())
            self.assertFalse(w.inventory(self.project,'S01E001')['can_assemble_final'])
            w._synthesize(self.project,data['script']);self.assertEqual(synth.call_count,1)
            with self.assertRaisesRegex(ValueError,'分别确认'):w.review_preview(self.project,'S01E001',{'job_id':job['id']})
            reviewed=w.review_preview(self.project,'S01E001',{'job_id':job['id'],'story_checked':True,'voice_checked':True,'subtitles_checked':True})
            self.assertTrue(reviewed['can_assemble_final']) # Screen-only graphics can be local final assets.
            self.assertEqual(reviewed['preview_review']['status'],'PASS')

    def test_event_action_and_cast_flow_to_control_and_timing_changes(self):
        self.save(shots=[{**self.row,'render_kind':'control','action':'father_reassure','cast_ids':['CHAR-DAD','CHAR-CHILD']}])
        row=shots.inventory(self.project)['shots'][0]
        self.assertEqual(row['action'],'father_reassure');self.assertEqual(row['character_ids'],['CHAR-DAD','CHAR-CHILD'])
        payload={'shot_id':row['id'],'character_id':'CHAR-DAD','character_definition':'父亲蓝衣',
            'scene_name':'房间','scene_definition':'父女站在床边','action':'father_reassure','environment':'modern_room','definitions_confirmed':True}
        with self.assertRaisesRegex(ValueError,'台本不一致'):shots.save(self.project,{**payload,'action':'look_phone'})
        shots.save(self.project,payload)
        binding=shots.read(shots.state_path(self.project),{})
        (self.project/'control.mp4').write_bytes(b'control')
        binding['bindings'][row['id']]['control']={'status':'COMPLETED','output':'control.mp4'}
        w.write_json(shots.state_path(self.project),binding)
        self.assertTrue(shots.status(self.project)['control']['ready'])
        self.save(expected_revision=1,shots=[{**self.row,'render_kind':'control','action':'father_realize','cast_ids':['CHAR-DAD','CHAR-CHILD']}])
        self.assertEqual(shots.status(self.project)['control']['status'],'STALE')

    def test_reviewed_cloud_video_with_stale_control_is_blocked(self):
        self.save(shots=[{**self.row,'render_kind':'control'}])
        candidate=w.workflow_shots(self.project,'S01E001')[0]
        (self.project/'control.mp4').write_bytes(b'control');(self.project/'final.mp4').write_bytes(b'final')
        binding={**candidate,'control':{'status':'COMPLETED','output':'control.mp4'}}
        w.write_json(shots.state_path(self.project),{'bindings':{self.row['id']:binding}})
        result={'ready':True,'review_status':'PASS','control':'control.mp4','output':'final.mp4'}
        with patch('scripts.low_cost_video.status',return_value=result),patch.object(w,'probe_video',return_value={'duration_seconds':1}):
            self.assertEqual(w._final_source(self.project,self.row,1),self.project.resolve()/'final.mp4')
            binding['excerpt']='旧版本剧情'
            w.write_json(shots.state_path(self.project),{'bindings':{self.row['id']:binding}})
            with self.assertRaisesRegex(ValueError,'失效'):w._final_source(self.project,self.row,1)

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_short_dialogue_preserves_script_and_uses_local_fallback_cache(self):
        child={**self.row,'speaker_id':'CHAR-CHILD','text':'爸爸，你怎么了？'}
        dad={**self.row,'id':'SHOT-S01E001-WB002','speaker_id':'CHAR-DAD','text':'没事。'}
        self.save(shots=[child,dad])
        out=io.BytesIO()
        with wave.open(out,'wb') as voice:
            voice.setnchannels(1);voice.setsampwidth(2);voice.setframerate(8000);voice.writeframes(b'\x10\x01'*4000)
        result=SimpleNamespace(audio=out.getvalue())
        with patch.object(w.KokoroSherpaTTS,'synthesize',return_value=result) as kokoro, patch.object(w.MacOSSayTTS,'synthesize',return_value=result) as local:
            script=w.load_script(self.project,'S01E001');audio=w._synthesize(self.project,script)
            kokoro.assert_called_once_with('爸爸你怎么了？',voice='zf_001',speed=1)
            local.assert_called_once_with('没事。',voice='Reed (中文（中国大陆）)',speed=1)
            self.assertEqual(audio['lines'][0]['text'],'爸爸，你怎么了？')
            self.assertEqual(audio['lines'][1]['actual_provider'],'macos_say')
            self.assertNotEqual(audio['lines'][0]['audio_signature'],w.digest({'text':child['text'],'voice':'zf_001','provider':'kokoro_local','speed':1,'adapter':'v1'}))
            w._synthesize(self.project,script)
            self.assertEqual(kokoro.call_count,1);self.assertEqual(local.call_count,1)

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_short_opening_clause_does_not_lose_the_first_word(self):
        row={**self.row,'speaker_id':'CHAR-CHILD','text':'好。\n我今天也加班。'}
        self.save(shots=[row]);out=io.BytesIO()
        with wave.open(out,'wb') as voice:
            voice.setnchannels(1);voice.setsampwidth(2);voice.setframerate(8000);voice.writeframes(b'\x10\x01'*4000)
        with patch.object(w.KokoroSherpaTTS,'synthesize',side_effect=AssertionError('short opening must use safe local voice')),patch.object(w.MacOSSayTTS,'synthesize',return_value=SimpleNamespace(audio=out.getvalue())) as local:
            audio=w._synthesize(self.project,w.load_script(self.project,'S01E001'))
            self.assertEqual(audio['lines'][0]['text'],row['text'])
            self.assertEqual(audio['lines'][0]['actual_provider'],'macos_say')
            self.assertIn('好',local.call_args.args[0])
            self.assertIn('我今天也加班',local.call_args.args[0])

    def test_voice_energy_opening_uses_the_same_point_two_second_entry(self):
        import array
        source=self.project/'voice.wav'
        samples=array.array('h',[0]*4800+[1000]*4800+[0]*4800)
        with wave.open(str(source),'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(48000);audio.writeframes(samples.tobytes())
        envelope=w.mouth_envelope(source)
        self.assertEqual(envelope[0],[0,0]);self.assertEqual(envelope[-1],[.5,0])
        self.assertIn([.3,1.0],envelope);self.assertTrue(all(0<=v<=1 for t,v in envelope))

    def test_ass_control_sequences_escaped(self):
        self.assertNotIn(r'{\pos',w._subtitle_text(r'恶意{\pos(0,0)}字幕'))
        self.assertIn('｛',w._subtitle_text('{text}'))

    def test_workbench_http_save_and_scope(self):
        with patch.object(web,'PROJECTS_ROOT',self.root):
            server=ThreadingHTTPServer(('127.0.0.1',0),web.VideoCreatorHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url=f'http://127.0.0.1:{server.server_port}/api/novel-anime/projects/novel-a/episode-workbench/S01E001'
                with urlopen(url) as res:self.assertEqual(json.load(res)['script']['revision'],0)
                request=Request(url+'/save',data=json.dumps(self.payload).encode(),headers={'Content-Type':'application/json'})
                with urlopen(request) as res:self.assertEqual(json.load(res)['script']['revision'],1)
                with self.assertRaises(HTTPError) as caught:urlopen(request)
                self.assertEqual(caught.exception.code,400)
                with self.assertRaises(HTTPError) as caught:urlopen(url.replace('S01E001','S01E099'))
                self.assertEqual(caught.exception.code,400)
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
