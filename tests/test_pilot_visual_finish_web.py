"""Exercise the real page renderers without opening a browser."""
import subprocess
from pathlib import Path


def test_reference_panel_renders_only_in_final_review_and_binds_revision():
    source = Path(__file__).resolve().parents[1] / 'web/production-flow.js'
    program = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map();
const node=id=>{
  if(!nodes.has(id)) nodes.set(id,{innerHTML:'',dataset:{},listeners:{},disabled:false,
    querySelectorAll:()=>[],addEventListener(event,handler){this.listeners[event]=handler;}});
  return nodes.get(id);
};
let activeProject='project-test',reloads=0,calls=[];
const context=vm.createContext({console,Map,setTimeout,clearTimeout,
  document:{getElementById:node},state:{currentWorkspace:'render'},
  resolveActiveNovelProject:()=>activeProject,escapeHtml:value=>String(value||''),
  episodeLabel:value=>value,
  api:async(url,options)=>calls.push({url,payload:JSON.parse(options.body)})});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8').replace(/\ninitProductionLayout\(\);\s*$/,''),context);
vm.runInContext(`renderVisualDirection=()=>'';loadProductionWorkbench=async()=>{reloadCount();};`,
  Object.assign(context,{reloadCount:()=>reloads++}));
const pilot={project_id:'project-test',revision:7,characters:[],assets:{},
  control:{sha256:'current-control',media_url:'/media/control.mp4'},package:{fresh:false},
  result:{},blockers:['待审核'],can_prepare:false};
const data={project_id:'project-test',episode_id:'S01E001',episodes:['S01E001'],
  characters:[],control_actions:[],script:{title:'试演',revision:1,shots:[]},
  job:{active:false,ready:false,status:'NOT_RUN'},pilot_visual_finish:pilot};
context.testData=data;
vm.runInContext(`productionStory={project:'project-test',data:testData};renderProductionStory();`,context);
assert(!node('productionScriptContent').innerHTML.includes('pilotVisualFinish'));
vm.runInContext('renderProductionWorkbench(testData)',context);
assert(node('studioContent').innerHTML.includes('pilotVisualFinish'));
assert(node('studioContent').innerHTML.includes('/media/control.mp4'));
assert(node('studioContent').innerHTML.includes('data-pilot-image="end_keyframe"'));
node('pilotAcceptControl').checked=true;
(async()=>{
  await node('pilotSaveControl').listeners.click();
  assert.strictEqual(calls.length,1);
  assert.strictEqual(calls[0].payload.expected_revision,7);
  assert.strictEqual(calls[0].payload.sha256,'current-control');
  assert.strictEqual(reloads,1);
  activeProject='another-project';
  await node('pilotSaveControl').listeners.click();
  assert.strictEqual(calls.length,1,'late callback must not affect a different project');
  activeProject='project-test';context.state.currentWorkspace='audio';
  vm.runInContext('renderProductionWorkbench(testData)',context);
  assert(!node('studioContent').innerHTML.includes('pilotVisualFinish'));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', program, str(source)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
