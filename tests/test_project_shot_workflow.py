import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from scripts import project_shot_workflow as w
from scripts.low_cost_video import record_path

class ProjectShotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.p=Path(self.temp.name)/'novel-a';self.p.mkdir()
        for relative,data in {
            'novel-anime-project.json':{'title':'暴雨封楼'},
            'story-bible/characters/index.json':{'characters':[{'id':'CHAR-A','name':'陈默'}]},
            'storyboard/modern-shot-units.json':{'shots':{'SHOT-A':{'text_excerpt':'陈默的手机突然黑屏。'}}},
            'storyboard/shot-breakdown.json':{'scene_breakdowns':[{'scene_id':'SCENE-A','episode_id':'EP-A','shots':[{'id':'SHOT-A','duration_seconds':2,'start_state':{'character_ids':['CHAR-A']}}]}]},
        }.items():
            path=self.p/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
        self.payload={'shot_id':'SHOT-A','character_id':'CHAR-A','character_definition':'短发，现代深色外套',
          'scene_name':'公寓客厅','scene_definition':'现代房间，沙发、门窗', 'environment':'modern_room','action':'look_phone','definitions_confirmed':True}

    def test_no_old_pilot_fallback(self):
        data=w.status(self.p)
        self.assertEqual(data['selected_shot_id'],'SHOT-A')
        self.assertFalse(data['control']['ready'])
        with self.assertRaises(ValueError):w.context(self.p)

    def test_own_character_scene_and_prompts(self):
        data=w.save(self.p,self.payload)
        self.assertEqual(data['selected']['character_name'],'陈默')
        prompt=w.prompt(data['selected'])
        self.assertIn('现代深色外套',prompt);self.assertNotIn('高马尾',prompt)
        self.assertTrue((self.p/'production/shot-packs/SHOT-A/scene.json').is_file())

    def test_cross_project_and_unconfirmed_definitions_rejected(self):
        for change in ({'character_id':'OTHER-PROJECT'},{'shot_id':'OTHER-SHOT'},{'definitions_confirmed':False},{'environment':'unknown'},{'action':'sit_up'}):
            with self.assertRaises(ValueError):w.save(self.p,{**self.payload,**change})

    def test_control_and_reference_invalidation(self):
        w.save(self.p,self.payload)
        data=w.read(w.state_path(self.p),{})
        data['bindings']['SHOT-A'].update(character_reference='ref.png',scene_reference='scene.png',control={'status':'COMPLETED','output':'control.mp4'})
        (self.p/'control.mp4').write_bytes(b'video');w.write_json(w.state_path(self.p),data)
        self.assertTrue(w.save(self.p,self.payload)['control']['ready'])
        changed=w.save(self.p,{**self.payload,'character_definition':'另一件服装'})
        self.assertFalse(changed['control']['ready']);self.assertFalse(changed['selected'].get('character_reference'))
        self.assertEqual(changed['selected']['scene_reference'],'scene.png')

    def test_image_is_registered_for_selected_shot_only(self):
        w.save(self.p,self.payload)
        b=io.BytesIO();Image.new('RGB',(8,8)).save(b,format='PNG')
        payload={'kind':'character','shot_id':'SHOT-A','content_base64':base64.b64encode(b.getvalue()).decode()}
        data=w.upload(self.p,payload);relative=data['selected']['character_reference']
        self.assertTrue((self.p/relative).is_file());self.assertTrue(relative.startswith('production/references/SHOT-A/'))
        with self.assertRaises(ValueError):w.upload(self.p,{**payload,'shot_id':'SHOT-B'})

    def test_context_uses_current_immutable_control(self):
        w.save(self.p,self.payload);data=w.read(w.state_path(self.p),{})
        (self.p/'new-control.mp4').write_bytes(b'video')
        data['bindings']['SHOT-A']['control']={'status':'COMPLETED','output':'new-control.mp4'}
        w.write_json(w.state_path(self.p),data)
        self.assertEqual(w.context(self.p),('new-control.mp4',''))

    def test_script_timing_change_invalidates_control(self):
        w.save(self.p,self.payload);data=w.read(w.state_path(self.p),{})
        (self.p/'control.mp4').write_bytes(b'v')
        data['bindings']['SHOT-A']['control']={'status':'COMPLETED','output':'control.mp4'}
        w.write_json(w.state_path(self.p),data)
        breakdown=self.p/'storyboard/shot-breakdown.json';shots=w.read(breakdown,{})
        shots['scene_breakdowns'][0]['shots'][0]['duration_seconds']=3
        w.write_json(breakdown,shots)
        self.assertEqual(w.status(self.p)['control']['status'],'STALE')
        with self.assertRaises(ValueError):w.context(self.p)

    def test_jobs_are_isolated_per_shot(self):
        self.assertNotEqual(record_path(self.p,'SHOT-A'),record_path(self.p,'SHOT-B'))
        with self.assertRaises(ValueError):record_path(self.p,'../../outside')

    def test_import_rejects_timing_mismatch(self):
        w.save(self.p,self.payload)
        payload={'shot_id':'SHOT-A','content_base64':base64.b64encode(b'v'*2048).decode()}
        with patch.object(w,'probe_video',return_value={'duration_seconds':5}):
            with self.assertRaisesRegex(ValueError,'时长'):w.import_control(self.p,payload)
        self.assertFalse(w.status(self.p)['control']['ready'])

if __name__=='__main__':unittest.main()
