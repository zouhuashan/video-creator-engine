import tempfile
import unittest
from pathlib import Path
from scripts.script_action_plan import plan_row, apply_plan
from scripts import episode_workbench as w
CHARACTERS=[{'id':str(i),'name':n} for i,n in enumerate(('陈浩','林晓','主管','系统'))]

class ActionPlanTests(unittest.TestCase):
    def row(self,location,speaker='0'):
        return dict(id='SHOT-S01E001-WB1',speaker_id=speaker,text='原对白。',visual=location+'｜白天',
            render_kind='screen',action='look_phone',environment='modern_room',screen_title=location,
            screen_lines=[],cast_ids=['0','1','2','3'],duration_seconds=4)

    def test_remote_voices_are_not_physical_cast_and_dialogue_is_unchanged(self):
        for scene,voice,cast in [('公司办公室','1',['0','2']),('另一家公司楼梯间','1',['1']),
                                  ('家中餐桌','0',['0','1']),('系统出现','3',['0','1']),('厨房','3',['0'])]:
            original=self.row(scene,voice);result=plan_row(original,CHARACTERS)
            self.assertEqual(result['render_kind'],'control')
            self.assertEqual(result['cast_ids'],cast)
            self.assertEqual(result['text'],original['text'])
            self.assertEqual(result['speaker_id'],voice)
            self.assertEqual(original['render_kind'],'screen')

    def test_unfamiliar_characters_or_locations_do_not_get_substituted(self):
        for row,chars in [(self.row('神秘森林'),CHARACTERS),(self.row('公司办公室'),[{'id':'0','name':'陌生人物'}])]:
            self.assertEqual(plan_row(row,chars),row)

    def test_apply_preserves_script_and_guards_revision_and_running_job(self):
        from unittest.mock import patch
        import os
        with tempfile.TemporaryDirectory() as t:
            project=Path(t)/'p';project.mkdir()
            w.write_json(project/'novel-anime-project.json',{'episodes':[{'id':'S01E001'}]})
            w.write_json(project/'story-bible/characters/index.json',{'characters':CHARACTERS})
            row=self.row('公司办公室')
            w.save_script(project,'S01E001',{'title':'测试','shots':[row],'expected_revision':0})
            with self.assertRaisesRegex(ValueError,'刷新'):apply_plan(project,'S01E001',{'expected_revision':0})
            w.write_json(w.directory(project,'S01E001')/'job.json',{'status':'RUNNING','owner_pid':os.getpid()})
            with self.assertRaisesRegex(ValueError,'正在生成'):apply_plan(project,'S01E001',{'expected_revision':1})
            w.write_json(w.directory(project,'S01E001')/'job.json',{'status':'COMPLETED'})
            apply_plan(project,'S01E001',{'expected_revision':1})
            result=w.load_script(project,'S01E001')
            self.assertEqual(result['shots'][0]['text'],row['text'])
            self.assertEqual(result['shots'][0]['render_kind'],'control')
            self.assertEqual(result['revision'],2)
            with self.assertRaisesRegex(ValueError,'已接入'):apply_plan(project,'S01E001',{'expected_revision':2})

    def test_ui_messages_overlay_without_speaking_them(self):
        row=self.row('便利店');row['screen_lines']=['1843.27元。'];row['render_kind']='control'
        audio={'duration':4,'lines':[{'shot_id':row['id'],'clip_start':0,'clip_duration':4,'start':.2,'end':2,'text':row['text']}]}
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'subtitles.ass';w._subtitles(audio,path,True,{'shots':[row]})
            self.assertIn('1843.27元。',path.read_text())
            self.assertNotIn('1843.27',path.with_suffix('.srt').read_text())

if __name__=='__main__':unittest.main()
