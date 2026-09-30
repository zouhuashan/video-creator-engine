import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from adapters.video_generation.base import VideoGenerationRequest, VideoGenerationError
from adapters.video_generation.wavespeed_wan import WaveSpeedWanVideo, estimate
from scripts.low_cost_video import start, status, local_file

class WaveSpeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'control.mp4'; self.video.write_bytes(b'video')
        self.image = self.root / 'character.png'; self.image.write_bytes(b'image')
        self.output = self.root / 'result.mp4'
        self.calls = []
        self.price = .2
        self.fail_submit = False
        self.fail_download = False

    def opener(self, request):
        self.calls.append(request)
        url = request.full_url
        if url.endswith('/media/upload/binary'):
            data = {'download_url': 'https://media.example/input'}
        elif url.endswith('/model/price'):
            data = {'price':self.price, 'discounted_price':self.price, 'currency':'USD'}
        elif url.endswith('/animate') or url.endswith('/video-edit'):
            if self.fail_submit: raise TimeoutError('secret')
            data = {'id':'task-1'}
        elif url.endswith('/task-1/result'):
            data = {'status':'completed','outputs':['https://media.example/result.mp4']}
        else:
            if self.fail_download: raise TimeoutError('secret')
            self.assertFalse(request.has_header('Authorization'))
            return io.BytesIO(b'output-video')
        return io.BytesIO(json.dumps({'code':200,'data':data}).encode())

    def provider(self, **kwargs):
        return WaveSpeedWanVideo(api_key='private-key', opener=self.opener,
            probe=lambda p:{'duration_seconds':5,'width':480,'height':854}, sleeper=lambda s:None, **kwargs)

    def request(self, images=True):
        return VideoGenerationRequest(image_paths=(self.image,) if images else (),
            reference_video_paths=(self.video,),output_path=self.output,prompt_text='anime')

    def test_rounding_and_minimum(self):
        self.assertEqual(estimate(5)['estimated_cny'],1.35)
        self.assertEqual(estimate(5.01)['billable_seconds'],6)
        self.assertEqual(estimate(.3)['billable_seconds'],3)
        self.assertEqual(estimate(5,'720p')['estimated_cny'],2.69)
        for duration in (float('nan'),float('inf'),0,121):
            with self.assertRaises(VideoGenerationError): estimate(duration)

    def test_budget_blocks_before_upload(self):
        with self.assertRaises(VideoGenerationError): self.provider(max_cost_cny=1).generate(self.request())
        self.assertEqual(self.calls,[])

    def test_live_price_blocks_before_paid_submit(self):
        self.price=1
        with self.assertRaisesRegex(VideoGenerationError,'实时报价'): self.provider().generate(self.request())
        self.assertFalse(any(r.full_url.endswith('/animate') for r in self.calls))

    def test_replace_payload_and_private_ledger(self):
        result=self.provider().generate(self.request())
        self.assertEqual(result.task_id,'task-1')
        payload=json.loads(next(r.data for r in self.calls if r.full_url.endswith('/animate')))
        self.assertEqual(payload['mode'],'replace')
        self.assertEqual(payload['resolution'],'480p')
        self.assertNotIn('private-key',self.output.with_suffix('.job.json').read_text())
        self.assertEqual(self.output.read_bytes(),b'output-video')

    def test_video_edit_never_sends_reference_image(self):
        self.provider(mode='video_edit').generate(self.request(False))
        payload=json.loads(next(r.data for r in self.calls if r.full_url.endswith('/video-edit')))
        self.assertNotIn('image',payload)
        self.assertNotIn('mode',payload)
        self.assertEqual(sum(r.full_url.endswith('/media/upload/binary') for r in self.calls),1)

    def test_download_failure_resume_does_not_resubmit(self):
        self.fail_download=True
        with self.assertRaises(VideoGenerationError):self.provider().generate(self.request())
        self.calls=[];self.fail_download=False
        self.provider().generate(self.request())
        self.assertTrue(all('/predictions/' in r.full_url or r.full_url.endswith('result.mp4') for r in self.calls))

    def test_unknown_submission_never_auto_retries(self):
        self.fail_submit=True
        with self.assertRaises(VideoGenerationError):self.provider().generate(self.request())
        self.calls=[]
        with self.assertRaisesRegex(VideoGenerationError,'未知'):self.provider().generate(self.request())
        self.assertEqual(self.calls,[])

    def test_changed_input_cannot_resume(self):
        self.provider().generate(self.request())
        self.image.write_bytes(b'changed');self.calls=[]
        with self.assertRaisesRegex(VideoGenerationError,'变化'):self.provider().generate(self.request())
        self.assertEqual(self.calls,[])

    def test_invalid_mode_and_image_contract(self):
        with self.assertRaises(VideoGenerationError):self.provider(mode='invalid').generate(self.request())
        with self.assertRaises(VideoGenerationError):self.provider(mode='video_edit').generate(self.request())
        self.assertEqual(self.calls,[])

    def test_workflow_consent_and_path_guard(self):
        with self.assertRaises(ValueError):start(self.root,{},'control.mp4','character.png','key')
        with self.assertRaises(ValueError):local_file(self.root,'../outside.mp4')
        self.assertEqual(status(self.root)['status'],'NOT_STARTED')

    def test_interrupted_status_is_resumable(self):
        path=self.root/'graybox/low-cost/latest.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'status':'RUNNING','output':'missing.mp4'}))
        self.assertEqual(status(self.root)['status'],'INTERRUPTED')

if __name__=='__main__':unittest.main()
