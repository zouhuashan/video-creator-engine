import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import scripts.web_server as web
from adapters.video_generation.base import VideoGenerationResult
from scripts.low_cost_video import status

class LowCostWebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'test';self.project.mkdir()
        (self.project/'control.mp4').write_bytes(b'video')
        (self.project/'character.png').write_bytes(b'image')
        self.addCleanup(patch.stopall)
        patch.object(web,'PROJECTS_ROOT',self.root).start()
        patch.object(web,'_low_cost_context',return_value=('control.mp4','character.png')).start()
        patch('scripts.low_cost_video.probe_video',return_value={'duration_seconds':5,'width':480,'height':854}).start()
        self.calls=[]
        def generate(adapter,request):
            self.calls.append((adapter.mode,request))
            request.output_path.write_bytes(b'mp4')
            request.output_path.with_suffix('.job.json').write_text(json.dumps({'quoted_usd':.2,'quoted_cny':1.35}))
            return VideoGenerationResult(request.output_path,'wavespeed_wan',5,len(request.image_paths),True,'task-123')
        patch('scripts.low_cost_video.WaveSpeedWanVideo.generate',generate).start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),web.VideoCreatorHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(lambda:web.RUNTIME_KEYS.pop('wavespeed_wan',None))
        web.RUNTIME_KEYS['wavespeed_wan']='test-only-private-key'

    def request(self,path,payload=None):
        req=Request(self.base+path, data=json.dumps(payload).encode() if payload is not None else None,
                    headers={'Content-Type':'application/json'})
        try:
            with urlopen(req) as response:return response.status,json.loads(response.read())
        except HTTPError as error:return error.code,json.loads(error.read())

    def wait_for_result(self):
        for _ in range(100):
            data=status(self.project)
            if not data['active']:return data
            time.sleep(.01)
        self.fail('worker did not finish')

    def payload(self):
        return {'confirm_billable':True,'upload_authorized':True,'control_reviewed':True,
                'mode':'video_edit','resolution':'480p','max_cost_cny':2,'prompt':'anime'}

    def test_project_workflow_http_save_and_catalog(self):
        files = {
            'novel-anime-project.json': {'title':'新的小说'},
            'story-bible/characters/index.json': {'characters':[{'id':'CHAR-NEW','name':'陈默'}]},
            'storyboard/shot-breakdown.json': {'scene_breakdowns':[{'scene_id':'SCENE-NEW','shots':[{'id':'SHOT-NEW','duration_seconds':2,'start_state':{'character_ids':['CHAR-NEW']}}]}]},
        }
        for relative, value in files.items():
            path=self.project/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
        endpoint='/api/novel-anime/projects/test/shot-workflow'
        code,data=self.request(endpoint)
        self.assertEqual(code,200);self.assertEqual(data['characters'][0]['name'],'陈默')
        self.assertFalse(data['control']['ready'])
        payload={'shot_id':'SHOT-NEW','character_id':'CHAR-NEW','character_definition':'现代短发男性',
                 'scene_name':'现代房间','scene_definition':'门窗、沙发','environment':'modern_room',
                 'action':'look_phone','definitions_confirmed':True}
        code,data=self.request(endpoint+'/save',payload)
        self.assertEqual(code,201);self.assertEqual(data['selected_shot_id'],'SHOT-NEW')
        self.assertIn('现代短发男性',data['suggested_prompt'])
        self.assertIn('character-prompt.txt',data['prompt_urls'])
        payload['character_id']='OTHER-PROJECT'
        self.assertEqual(self.request(endpoint+'/save',payload)[0],400)
        self.assertEqual(self.calls,[])

    def test_quote_reads_local_duration_without_cloud(self):
        code,data=self.request('/api/novel-anime/projects/test/low-cost-video/quote',{'resolution':'480p'})
        self.assertEqual(code,200);self.assertEqual(data['estimated_cny'],1.35)
        self.assertEqual(self.calls,[])

    def test_budget_and_consent_block(self):
        path='/api/novel-anime/projects/test/low-cost-video/start'
        self.assertEqual(self.request(path,{})[0],400)
        payload=self.payload();payload['max_cost_cny']=1
        self.assertEqual(self.request(path,payload)[0],400)
        self.assertEqual(self.calls,[])
        self.assertFalse((self.project/'graybox/low-cost/latest.json').exists())

    def test_generation_status_review_and_duplicate_guard(self):
        endpoint='/api/novel-anime/projects/test/low-cost-video'
        self.assertEqual(self.request(endpoint+'/start',self.payload())[0],202)
        data=self.wait_for_result();self.assertEqual(data['status'],'COMPLETED')
        self.assertEqual(self.calls[0][1].image_paths,())
        code,data=self.request(endpoint);self.assertEqual(code,200)
        self.assertTrue(data['media_url'].startswith('/media/test/'))
        self.assertNotIn('test-only-private-key',json.dumps(data))
        self.assertEqual(self.request(endpoint+'/start',self.payload())[0],400)
        self.assertEqual(len(self.calls),1)
        code,_=self.request(endpoint+'/review',{'review_status':'PASS','note':'角色、背景、动作均已检查'})
        self.assertEqual(code,200)
        self.assertEqual(status(self.project)['review_status'],'PASS')

    def test_missing_project_and_unfinished_review(self):
        self.assertEqual(self.request('/api/novel-anime/projects/missing/low-cost-video')[0],400)
        self.assertEqual(self.request('/api/novel-anime/projects/test/low-cost-video/review',{'review_status':'PASS','note':'checked'})[0],400)

    def test_web_key_entry_never_echoes_secret(self):
        code,data=self.request('/api/settings/keys',{'provider':'wavespeed_wan','key':'only-local-test-secret'})
        self.assertEqual(code,200);self.assertTrue(data['configured'])
        self.assertNotIn('only-local-test-secret',json.dumps(data))

if __name__=='__main__':unittest.main()
