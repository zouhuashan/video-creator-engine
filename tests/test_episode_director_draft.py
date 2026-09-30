import tempfile
import unittest
from pathlib import Path
from scripts import episode_workbench as w
from scripts.episode_director_draft import load_draft,adopt_draft

class DirectorDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.project=Path(self.temp.name)/'p';self.project.mkdir()
        w.write_json(self.project/'novel-anime-project.json',{'episodes':[{'id':'S01E001'}]})
        w.write_json(self.project/'story-bible/characters/index.json',{'characters':[{'id':'CHAR-A','name':'陈浩'}]})
        self.row={'id':'SHOT-S01E001-WB1','speaker_id':'CHAR-A','text':'原对白','visual':'公司办公室','render_kind':'control','action':'modern_office','environment':'modern_room','screen_lines':[],'cast_ids':['CHAR-A'],'duration_seconds':4}
        w.save_script(self.project,'S01E001',{'title':'原稿','shots':[self.row],'expected_revision':0})
        self.current=w.load_script(self.project,'S01E001');self.folder=w.directory(self.project,'S01E001')
        self.draft={'project_id':self.project.name,'episode_id':'S01E001','base_signature':self.current['signature'],'title':'修改稿','shots':[{**self.row,'text':'修改对白','framing':'closeup','focus_id':'CHAR-A'}]}
        w.write_json(self.folder/'director-draft.json',self.draft)

    def test_loading_is_read_only_adopting_keeps_old_revision_and_invalidates_media(self):
        draft=load_draft(self.project,'S01E001',self.current)
        self.assertEqual(w.load_script(self.project,'S01E001')['signature'],self.current['signature'])
        (self.folder/'old.mp4').write_bytes(b'old')
        w.write_json(self.folder/'job.json',{'status':'COMPLETED','script_signature':self.current['signature'],'output':(self.folder/'old.mp4').relative_to(self.project).as_posix()})
        result=adopt_draft(self.project,'S01E001',{'expected_revision':1,'draft_signature':draft['draft_signature']})
        self.assertEqual(result['script']['revision'],2);self.assertEqual(result['script']['shots'][0]['framing'],'closeup')
        self.assertEqual(result['job']['status'],'STALE');self.assertTrue((self.folder/'old.mp4').exists())
        self.assertEqual(len(list((self.folder/'revisions').glob('*.json'))),2)
        self.assertTrue((self.folder/'director-adoptions.json').is_file())

    def test_changed_draft_changed_script_and_active_render_cannot_be_overwritten(self):
        draft=load_draft(self.project,'S01E001',self.current)
        with self.assertRaisesRegex(ValueError,'修改稿已变化'):adopt_draft(self.project,'S01E001',{'expected_revision':1,'draft_signature':'wrong'})
        import os
        w.write_json(self.folder/'job.json',{'status':'RUNNING','owner_pid':os.getpid()})
        with self.assertRaisesRegex(ValueError,'正在生成'):adopt_draft(self.project,'S01E001',{'expected_revision':1,'draft_signature':draft['draft_signature']})
        w.write_json(self.folder/'job.json',{'status':'COMPLETED'})
        w.save_script(self.project,'S01E001',{'title':'人工编辑','shots':[self.row],'expected_revision':1})
        with self.assertRaisesRegex(ValueError,'当前台本已变化'):adopt_draft(self.project,'S01E001',{'expected_revision':2,'draft_signature':draft['draft_signature']})

    def test_invalid_optional_draft_does_not_break_current_workbench(self):
        w.write_json(self.folder/'director-draft.json',{**self.draft,'project_id':'other'})
        data=w.inventory(self.project,'S01E001');self.assertIsNone(data['director_draft']);self.assertTrue(data['director_draft_error'])
        self.assertEqual(data['script']['title'],'原稿')
        with self.assertRaises(ValueError):adopt_draft(self.project,'S01E001',{'expected_revision':1})

    def test_unowned_framing_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'焦点'):w.validate_script(self.project,'S01E001',{'title':'镜头','shots':[{**self.row,'framing':'closeup','focus_id':'OTHER-PROJECT'}]})
