import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from scripts import web_server as web, novel_web_import as importer, episode_workbench as w
from scripts.script_direct_import import parse_script

SOURCE='''第1集：一起失业
【场景1｜公司办公室｜白天】
主管把通知书交给陈浩。

主管：
公司效益不好，今天就到这吧。

陈浩：
赔偿呢？

老婆林晓发来微信：
晚上吃什么？
我下班买菜。

【场景2｜便利店｜晚上】
林晓也坐在那里。

林晓手机界面：
求职软件已投递17份。
已读：0。

她给陈浩发消息：
还没下班？

陈浩回复：
嗯。
你先回家。

旁白：
他们第一次同时失业。

【不要告诉任何人。】
'''


class ScriptDirectTests(unittest.TestCase):
    def args(self,source=SOURCE,**extra):
        return dict(title='剧本测试',author='',episode_count=5,rights_mode='TECHNICAL_TEST',
                    rights_confirmed=False,source_name='剧本.txt',source_text=source,import_mode='SCRIPT',**extra)

    def test_blocks_messages_screen_text_and_reject_invalid_structure(self):
        p=parse_script('\ufeff'+SOURCE.replace('\n','\r\n'))
        self.assertEqual(p['names'],['主管','陈浩','林晓'])
        self.assertEqual(p['scenes'][1]['units'][2]['speaker'],'林晓')
        self.assertEqual(p['scenes'][1]['units'][3]['speaker'],'陈浩')
        self.assertEqual(p['scenes'][1]['units'][1]['kind'],'VISUAL')
        self.assertIn('已读：0。',p['scenes'][1]['units'][1]['text'])
        with self.assertRaisesRegex(ValueError,'场景块'):parse_script('不是场景块')
        with self.assertRaisesRegex(ValueError,'重复'):parse_script(SOURCE+'\n【场景1｜办公室｜白天】\n陈浩：你好。')

    def test_direct_contract_preserves_words_and_retry_keeps_editor(self):
        with tempfile.TemporaryDirectory() as t, patch.object(importer,'backfill_episode_scenes',side_effect=AssertionError('must skip novel rewriting')):
            root=Path(t);first=importer.create_project_from_web_upload(root,**self.args());p=root/first['directory_id']
            self.assertEqual(first['episode_count'],1);self.assertEqual(first['scene_backfill']['scene_count'],2)
            self.assertGreater(first['scene_backfill']['shot_count'],2)
            data=w.inventory(p,'S01E001');self.assertEqual(len(data['source_scenes']),2)
            spoken=[u['text'] for s in data['source_scenes'] for u in s['units'] if u['kind'] in ('DIALOGUE','NARRATION')]
            self.assertEqual(spoken,[r['text'] for r in data['script']['shots'] if r['audio_kind']=='speech'])
            self.assertIn('嗯。\n你先回家。',spoken)
            self.assertTrue(any(r['audio_kind']=='silent' and '【不要告诉任何人。】' in r['screen_lines'] for r in data['script']['shots']))
            self.assertTrue((p/first['log_path']).is_file())
            self.assertIn('SCRIPT_DIRECT_NO_REWRITE',(p/first['log_path']).read_text())
            script=data['script'];w.save_script(p,'S01E001',{'title':'人工修改标题','shots':script['shots'],'expected_revision':script['revision']})
            second=importer.create_project_from_web_upload(root,**self.args())
            self.assertTrue(second['reused_existing']);self.assertEqual(second['directory_id'],first['directory_id'])
            self.assertEqual(w.load_script(p,'S01E001')['title'],'人工修改标题')
            silent=next(r for r in script['shots'] if r['audio_kind']=='silent')
            with patch.object(w.KokoroSherpaTTS,'synthesize',side_effect=AssertionError('unspoken text must not enter TTS')):
                audio=w._synthesize(p,{**script,'shots':[silent]})
            self.assertEqual(audio['lines'][0]['spoken_duration'],0)

    def test_novel_without_stable_characters_still_imports(self):
        with tempfile.TemporaryDirectory() as t:
            args=self.args('第一章\n窗外暴雨不止，走廊空无一人。');args['import_mode']='NOVEL'
            a=importer.create_project_from_web_upload(Path(t),**args)
            self.assertEqual(a['character_count'],0);self.assertEqual(a['character_status'],'NEEDS_REVIEW')
            self.assertTrue((Path(t)/a['directory_id']/'novel-anime-project.json').is_file())

    def test_web_import_delete_and_running_job_protection(self):
        with tempfile.TemporaryDirectory() as t, patch.object(web,'PROJECTS_ROOT',Path(t)):
            web._NOVEL_PROJECT_CACHE.clear()
            server=ThreadingHTTPServer(('127.0.0.1',0),web.VideoCreatorHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def post(route,payload):
                with urlopen(Request(base+route,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')) as r:return json.load(r)
            try:
                a=post('/api/novel-anime/import',self.args());p=Path(t)/a['directory_id']
                args=self.args();args['title']='保留项目';b=post('/api/novel-anime/import',args)
                with self.assertRaises(HTTPError):post('/api/novel-anime/delete',{'project_id':a['directory_id']})
                w.write_json(w.directory(p,'S01E001')/'job.json',{'status':'RUNNING','owner_pid':os.getpid()})
                with self.assertRaises(HTTPError):post('/api/novel-anime/delete',{'project_id':a['directory_id'],'confirm_delete':True})
                self.assertTrue(p.is_dir())
                w.write_json(w.directory(p,'S01E001')/'job.json',{'status':'COMPLETED'})
                result=post('/api/novel-anime/delete',{'project_id':a['directory_id'],'confirm_delete':True})
                self.assertFalse(p.exists());self.assertEqual(result['default_project_id'],b['directory_id'])
                result=post('/api/novel-anime/delete',{'project_id':b['directory_id'],'confirm_delete':True})
                self.assertEqual(result['remaining_project_count'],0);self.assertEqual(result['default_project_id'],'')
            finally:server.shutdown();server.server_close();thread.join();web._NOVEL_PROJECT_CACHE.clear()

    @unittest.skipUnless((w.ROOT/'每天一条经营提示_第1集_系统导入版.txt').is_file(),'user sample unavailable')
    def test_user_sample_seven_scenes(self):
        source=(w.ROOT/'每天一条经营提示_第1集_系统导入版.txt').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as t:
            a=importer.create_project_from_web_upload(Path(t),**self.args(source));p=Path(t)/a['directory_id']
            self.assertEqual({c['name'] for c in a['characters']},{'陈浩','林晓','主管','系统'})
            data=w.inventory(p,'S01E001');self.assertEqual(len(data['source_scenes']),7)
            self.assertTrue(any(u['kind']=='VISUAL' and u['text']=='1987-0416' for s in data['source_scenes'] for u in s['units']))
            self.assertEqual(data['script']['title'],'夫妻俩同一天失业')
