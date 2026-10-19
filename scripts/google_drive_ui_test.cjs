// NODE_PATH=/path/to/node_modules node --experimental-vm-modules scripts/google_drive_ui_test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
(async () => {
 const dom = new JSDOM('<!doctype html><body></body>', {url:'https://comfy.example/'});
 const calls=[]; const extensions=[];
 let configured=false; let failConfig=false;
 const savedRedirect='https://saved.example/google_drive_upload/oauth/callback';
 const context=vm.createContext({window:dom.window,document:dom.window.document,URL,FileReader:dom.window.FileReader,console,
   fetch: async (url, options={}) => {
    const body=options.body?JSON.parse(options.body):null; calls.push({url,body});
    if(url.endsWith('/config')) {
      if(failConfig)return {ok:false,status:400,json:async()=>({error:'Invalid callback URL'})};
      configured=true;
    }
    const data = url.endsWith('/status')?{configured,connected:configured,redirect_uri:configured?savedRedirect:undefined}:url.endsWith('/folders')?{id:'created-folder'}:
      url.endsWith('/oauth/start')?{authorization_url:'https://accounts.google.com/o/oauth2/auth?state=test'}:{ok:true};
    return {ok:true,json:async()=>data};
   }});
 const app={registerExtension:e=>extensions.push(e)};
 const modules=new Map();
 function load(file){
  if(modules.has(file))return modules.get(file);
  let m;
  if(file.endsWith('/scripts/app.js'))m=new vm.SyntheticModule(['app'],function(){this.setExport('app',app)},{context});
  else if(file.endsWith('/scripts/api.js'))m=new vm.SyntheticModule(['api'],function(){this.setExport('api',{apiURL:p=>'/api'+p})},{context});
  else m=new vm.SourceTextModule(fs.readFileSync(file,'utf8'),{context,identifier:file});
  modules.set(file,m);return m;
 }
 const root=path.resolve(__dirname,'..'); const entry=load(root+'/js/google_drive/index.js');
 await entry.link((s,m)=>load(path.resolve(path.dirname(m.identifier),s))); await entry.evaluate();
 assert.equal(extensions.length,1);
 const setup=modules.get(root+'/js/google_drive/setup.mjs').namespace;
 for(const vue of [false,true]){
  dom.window.LiteGraph={vueNodesMode:vue};
  class Node{constructor(){this.widgets=[{name:'folder_id',value:''}];this.properties={};}addWidget(type,name,value,callback,options){const w={type,name,value,callback,options};this.widgets.push(w);return w;}setDirtyCanvas(){}}
  await extensions[0].beforeRegisterNodeDef(Node,{name:'GoogleDriveUpload'});
  const node=new Node();node.onNodeCreated();assert.ok(node.widgets.some(w=>w.name==='Google Drive Setup'));
  let draftPanel=await setup.openDriveSetup(node);
  const draft='{"web":{"client_id":"test","client_secret":"never-serialize-me"}}';
  draftPanel.querySelector('textarea').value=draft;
  draftPanel.querySelector('[name=redirect_uri]').value='https://custom.example/google_drive_upload/oauth/callback';
  [...draftPanel.querySelectorAll('button')].find(b=>b.textContent==='Close').click();
  draftPanel=await setup.openDriveSetup(node);
  draftPanel.dispatchEvent(new dom.window.Event('cancel',{cancelable:true}));
  assert.equal(draftPanel.isConnected,false);
  draftPanel=await setup.openDriveSetup(node);
  const panel=await setup.openDriveSetup(node);
  assert.equal(draftPanel.isConnected,false,'opening another setup replaces the old dialog');
  assert.equal(panel.querySelector('textarea').value,draft,'closing and reopening preserves unsaved credentials');
  assert.equal(panel.querySelector('[name=redirect_uri]').value,'https://custom.example/google_drive_upload/oauth/callback');
  const textarea=panel.querySelector('textarea');textarea.value=JSON.stringify({web:{client_id:'test',client_secret:'never-serialize-me'}});
  const find=t=>[...panel.querySelectorAll('button')].find(b=>b.textContent===t);
  failConfig=true;
  find('Save Configuration').click();await new Promise(r=>setImmediate(r));
  assert.match(panel.querySelector('[role=status]').textContent,/Invalid callback/);
  assert.ok(textarea.value.includes('never-serialize-me'),'a failed save retains input');
  failConfig=false;
  find('Save Configuration').click();await new Promise(r=>setImmediate(r));
  assert.equal(textarea.value,'');assert.ok(!JSON.stringify(node).includes('never-serialize-me'));
  find('Connect Google Drive').click();await new Promise(r=>setImmediate(r));
  assert.equal(panel.querySelector('a').hostname,'accounts.google.com');
  panel.querySelector('[name=folder_name]').value='Generated';
  find('Create Folder').click();await new Promise(r=>setImmediate(r));
  assert.equal(node.widgets[0].value,'created-folder');
  find('Close').click();assert.equal(panel.isConnected,false);
  const reopened=await setup.openDriveSetup(node);
  assert.equal(reopened.querySelector('[name=redirect_uri]').value,savedRedirect);
  assert.equal(reopened.querySelector('textarea').value,'','saved secrets are not returned to the browser');
  assert.match(reopened.querySelector('[data-credential-state]').textContent,/credentials saved/i);
  assert.match(reopened.querySelector('textarea').placeholder,/saved/i);
  assert.ok(!reopened.textContent.includes('never-serialize-me'));
  [...reopened.querySelectorAll('button')].find(b=>b.textContent==='Close').click();
 }
 assert.equal(calls.filter(c=>c.url.endsWith('/folders')).length,2);
 console.log('PASS: Drive extension, both renderer modes, setup, credentials excluded from node, connect link and folder ID');
})().catch(e=>{console.error(e);process.exitCode=1;});
