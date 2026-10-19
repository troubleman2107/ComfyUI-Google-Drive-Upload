// NODE_PATH=/path/to/node_modules node --experimental-vm-modules scripts/google_drive_ui_test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
(async () => {
 const dom = new JSDOM('<!doctype html><body></body>', {url:'https://comfy.example/'});
 const calls=[]; const extensions=[];
 const context=vm.createContext({window:dom.window,document:dom.window.document,URL,FileReader:dom.window.FileReader,console,
   fetch: async (url, options={}) => {
    const body=options.body?JSON.parse(options.body):null; calls.push({url,body});
    const data = url.endsWith('/status')?{configured:true,connected:true}:url.endsWith('/folders')?{id:'created-folder'}:
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
  const panel=await setup.openDriveSetup(node);
  const textarea=panel.querySelector('textarea');textarea.value=JSON.stringify({web:{client_id:'test',client_secret:'never-serialize-me'}});
  const find=t=>[...panel.querySelectorAll('button')].find(b=>b.textContent===t);
  find('Save Configuration').click();await new Promise(r=>setImmediate(r));
  assert.equal(textarea.value,'');assert.ok(!JSON.stringify(node).includes('never-serialize-me'));
  find('Connect Google Drive').click();await new Promise(r=>setImmediate(r));
  assert.equal(panel.querySelector('a').hostname,'accounts.google.com');
  panel.querySelector('[name=folder_name]').value='Generated';
  find('Create Folder').click();await new Promise(r=>setImmediate(r));
  assert.equal(node.widgets[0].value,'created-folder');
  find('Close').click();assert.equal(panel.isConnected,false);
 }
 assert.equal(calls.filter(c=>c.url.endsWith('/folders')).length,2);
 console.log('PASS: Drive extension, both renderer modes, setup, credentials excluded from node, connect link and folder ID');
})().catch(e=>{console.error(e);process.exitCode=1;});
