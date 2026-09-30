import base64
import io
import json
import shutil
import subprocess
import threading
import zipfile
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from scripts import humanoid_performance as performance
from scripts import pilot_visual_finish as pilot
from scripts import web_server as web
from scripts.modern_asset_library import review_asset


def image_bytes(color):
    out = io.BytesIO()
    Image.new('RGB', (256, 256), color).save(out, 'PNG')
    return out.getvalue()


def video(path, color='black', duration=6, width=240, height=426):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    f'color=c={color}:s={width}x{height}:r=24:d={duration}',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(path)], check=True, timeout=20)
    return path.read_bytes()


@pytest.fixture
def project(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required for single-shot integration tests')
    root = tmp_path / 'novel-pilot'
    out = root / performance.RELATIVE_DIR
    out.mkdir(parents=True)
    (root / 'novel-anime-project.json').write_text(json.dumps({'episodes': [{'id': 'S01E001'}]}))
    index = root / 'story-bible/characters/index.json'
    index.parent.mkdir(parents=True)
    index.write_text(json.dumps({'characters': [{'id': 'CHR-001', 'name': '陈浩'}]}))
    video(out / 'performance.mp4')
    (out / 'poster.png').write_bytes(image_bytes('gray'))
    (out / 'performance-report.json').write_text(json.dumps({'performance': {'contact_pass': True}, 'human_review': 'PENDING'}))
    assets = root / performance.ASSET_MANIFEST
    assets.parent.mkdir(parents=True)
    assets.write_text('{}')
    for role, color in zip(pilot.ROLES, ('red', 'blue', 'green', 'yellow')):
        pilot.register_image(root, role=role, character_id='CHR-001', content=image_bytes(color), source='test')
    return root


def payload(project, **fields):
    return {'expected_revision': pilot.status(project)['revision'], **fields}


def ready_package(project):
    for role in pilot.ROLES:
        asset = pilot.status(project)['assets'][role]
        pilot.review_image(project, payload(project, role=role, decision='APPROVED', sha256=asset['sha256']))
    current = pilot.status(project)
    pilot.accept_control(project, payload(project, sha256=current['control']['sha256'], accept_as_control=True))
    return pilot.prepare_package(project, payload(project))


def imported(project):
    current = ready_package(project)
    content = video(project / 'candidate.mp4', color='blue')
    return pilot.import_result(project, payload(project, package_signature=current['signature'], content_base64=base64.b64encode(content).decode()))


def test_references_do_not_approve_control_or_unlock_expansion(project):
    state = pilot.status(project)
    assert not state['can_prepare'] and not state['can_expand']
    assert all(a['review_status'] == 'PENDING' for a in state['assets'].values())
    assert performance.status(project)['human_review'] == 'PENDING'
    with pytest.raises(ValueError, match='审核'):
        pilot.prepare_package(project, payload(project))
    assert not (project / pilot.DIRECTORY / 'packages').exists()


def test_explicit_control_consent_and_every_asset_are_required(project):
    current = pilot.status(project)
    with pytest.raises(ValueError, match='明确接受'):
        pilot.accept_control(project, payload(project, sha256=current['control']['sha256']))
    with pytest.raises(ValueError, match='明确接受'):
        pilot.accept_control(project, payload(project, sha256='old', accept_as_control=True))
    assert not pilot.status(project)['control']['accepted']


def test_package_is_local_idempotent_and_has_current_files(project):
    state = ready_package(project)
    assert state['package']['fresh'] and not state['can_expand']
    path = project / state['package']['path']
    with zipfile.ZipFile(path) as archive:
        assert {'control.mp4', 'character.png', 'scene.png', 'keyframe.png', 'end_keyframe.png',
                'control-first.png', 'control-last.png', 'scene.json', 'prompt-zh.txt', 'README.txt'} <= set(archive.namelist())
        contract = json.loads(archive.read('scene.json'))
        assert contract['project_id'] == project.name and contract['package_signature'] == state['signature']
        assert not contract['cost']['remote_generation_started']
    assert pilot.prepare_package(project, payload(project))['revision'] == state['revision']
    assert performance.status(project)['human_review'] == 'PENDING'


def test_replacement_keeps_history_and_invalidates_package(project):
    prior = ready_package(project)
    path = project / prior['package']['path']
    pilot.register_image(project, role='scene', content=image_bytes('purple'))
    assert path.is_file() and not pilot.status(project)['package']['fresh']
    assert pilot.status(project)['assets']['scene']['review_status'] == 'PENDING'
    assert not pilot.status(project)['can_expand']


def test_revoking_library_approval_invalidates_package(project):
    state = ready_package(project)
    review_asset(project, state['assets']['character']['path'], 'REJECTED')
    assert not pilot.status(project)['package']['fresh']


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_reupload_repairs_reference_without_reusing_approval(project, damage):
    state = ready_package(project)
    asset = state['assets']['character']
    path = project / asset['path']
    original = path.read_bytes()
    if damage == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'corrupt')
    assert not pilot.status(project)['package']['fresh']
    restored = pilot.register_image(project, role='character', character_id=asset['entity_id'], content=original)
    assert path.read_bytes() == original and restored['assets']['character']['fresh']
    assert restored['assets']['character']['review_status'] == 'PENDING'
    assert not restored['package']['fresh'] and not restored['can_expand']


def test_control_rerender_invalidates_its_consent(project):
    state = ready_package(project)
    video(project / performance.RELATIVE_DIR / 'performance.mp4', color='red')
    after = pilot.status(project)
    assert not after['control']['accepted'] and not after['package']['fresh']
    assert (project / state['package']['path']).exists()


def test_bad_media_or_wrong_character_are_rejected(project):
    with pytest.raises(ValueError, match='当前项目'):
        pilot.register_image(project, role='character', character_id='OTHER', content=image_bytes('white'))
    with pytest.raises(ValueError):
        pilot.register_image(project, role='scene', content=b'not an image')
    with pytest.raises(ValueError, match='刷新'):
        pilot.review_image(project, {'expected_revision': -1, 'role': 'character', 'decision': 'APPROVED'})


def test_tampered_reference_cannot_be_approved(project):
    state = pilot.status(project)
    asset = state['assets']['scene']
    (project / asset['path']).write_bytes(image_bytes('purple'))
    with pytest.raises(ValueError, match='变化'):
        pilot.review_image(project, payload(project, role='scene', sha256=asset['sha256'], decision='APPROVED'))


def test_import_checks_duration_aspect_and_control_copy(project):
    current = ready_package(project)
    for content, error in (
        ((project / performance.RELATIVE_DIR / 'performance.mp4').read_bytes(), '原控制'),
        (video(project / 'too-short.mp4', color='red', duration=2), '时长'),
        (video(project / 'landscape.mp4', color='blue', width=426, height=240), '竖屏'),
    ):
        with pytest.raises(ValueError, match=error):
            pilot.import_result(project, payload(project, package_signature=current['signature'], content_base64=base64.b64encode(content).decode()))
    assert not pilot.status(project)['result'].get('path')


def test_real_result_requires_all_checks_and_stays_pending_after_qc(project):
    state = imported(project)
    assert state['result']['technical_qc'] == 'PASS' and not state['can_expand']
    with pytest.raises(ValueError, match='六项'):
        pilot.review_result(project, payload(project, sha256=state['result']['sha256'], decision='PASS', checks={}))
    passed = pilot.review_result(project, payload(project, sha256=state['result']['sha256'], decision='PASS', checks={k: True for k in pilot.RESULT_CHECKS}))
    assert passed['can_expand'] and not passed['publishing_allowed']
    assert performance.status(project)['human_review'] == 'PENDING'
    (project / state['result']['path']).write_bytes(b'changed video')
    assert not pilot.status(project)['can_expand']


def test_reject_can_be_resumed_and_reimport_does_not_erase_review(project):
    state = imported(project)
    denied = pilot.review_result(project, payload(project, sha256=state['result']['sha256'], decision='REJECTED', notes='手指变形'))
    raw = (project / denied['result']['path']).read_bytes()
    again = pilot.import_result(project, payload(project, package_signature=denied['signature'], content_base64=base64.b64encode(raw).decode()))
    assert again['result']['review']['notes'] == '手指变形' and again['revision'] == denied['revision']
    assert not again['can_expand']


def test_http_get_and_upload_are_project_scoped(project, monkeypatch):
    monkeypatch.setattr(web, 'PROJECTS_ROOT', project.parent)
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.VideoCreatorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/api/novel-anime/projects/'
    try:
        with urlopen(base + project.name + '/pilot-visual-finish') as response:
            state = json.load(response)
        assert state['assets']['character']['media_url'].startswith('/media/' + project.name + '/')
        with pytest.raises(HTTPError) as invalid:
            urlopen(base + 'missing/pilot-visual-finish')
        assert invalid.value.code == 400
        request = Request(base + project.name + '/pilot-visual-finish/review-asset',
                          data=json.dumps({'expected_revision': -1, 'role': 'scene', 'decision': 'APPROVED'}).encode(),
                          headers={'Content-Type': 'application/json'})
        with pytest.raises(HTTPError) as stale:
            urlopen(request)
        assert stale.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
