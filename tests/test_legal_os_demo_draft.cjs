// New local-draft behavior only. Simulated DOM/storage; native browser checked separately.
// Usage: node tests/test_legal_os_demo_draft.cjs
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '..', 'lukart_work', 'legal_os_demo.js'), 'utf8');
const key = 'lukart.legal-os.demo.synthetic-draft.v1';
class Element {
  constructor(){this.value='';this.checked=false;this.disabled=false;this.textContent='';this.children=[];this.listeners={};this.classList={toggle(){}};}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  emit(name){for(const fn of this.listeners[name]??[])fn();}
  replaceChildren(...children){this.children=children;this.value=children[0]?.value??'';}
  append(child){this.children.push(child);}
}
function setup(store=new Map(), fail={}) {
  const elements=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const formIds=['compose-description','compose-type',...['sender','recipient'].flatMap(role=>['name','lines','postal','country'].map(field=>'compose-'+role+'-'+field))];
  const writes=[], removals=[];
  vm.runInNewContext(script,{
    document:{getElementById:get,querySelectorAll:()=>formIds.map(get),createElement:()=>new Element()},
    Option:function(text,value){this.textContent=text;this.value=value;},
    localStorage:{getItem(k){if(fail.get)throw Error('blocked');return store.get(k)??null;},setItem(k,v){if(fail.set)throw Error('quota');store.set(k,v);writes.push(k);},removeItem(k){if(fail.remove)throw Error('blocked');store.delete(k);removals.push(k);}},
    fetch(){throw Error('Local draft must not perform network requests');},
    console
  });
  return {store,writes,removals,get,edit(id,value){get(id).value=value;get(id).emit('input');},consent(){get('demo-synthetic-only').checked=true;get('demo-synthetic-only').emit('change');},save(){get('demo-save-local').emit('click');},reset(){get('demo-reset').emit('click');},message(){return get('demo-draft-status').textContent;}};
}
const tests=[];
function test(name,run){run();tests.push(name);console.log('PASS '+name);}

test('explicit synthetic confirmation; no automatic save',()=>{
  const t=setup();assert.equal(t.writes.length,0);assert.equal(t.get('demo-save-local').disabled,true);
  t.save();assert.equal(t.store.has(key),false);assert.match(t.message(),/Zapis zablokowany/);
  t.consent();assert.equal(t.get('demo-save-local').disabled,false);
  t.edit('compose-description','Syntetyczna zmiana');assert.equal(t.get('demo-save-local').disabled,true);
  assert.equal(t.get('demo-synthetic-only').checked,false);
});
test('round trip restores every editable field and allows incomplete drafts',()=>{
  const t=setup();
  const edits={'compose-description':'Syntetyczny szkic po F5','compose-type':'synthetic-letter','compose-sender-name':'Osoba Syntetyczna C','compose-sender-lines':'ul. Testowa 9\nMiasto Testowe','compose-sender-postal':'00-009','compose-sender-country':'PL','compose-recipient-name':'Instytucja Testowa D','compose-recipient-lines':'ul. Testowa 10\nMiasto Testowe','compose-recipient-postal':'00-010','compose-recipient-country':'PL'};
  for(const [id,value]of Object.entries(edits))t.edit(id,value);
  t.consent();t.save();assert.match(t.message(),/Zapisano szkic lokalnie/);
  const record=JSON.parse(t.store.get(key));assert.deepEqual(Object.keys(record).sort(),['form','kind','version']);assert.deepEqual(Object.keys(record.form).sort(),['description','document_type','recipient','sender']);
  const reload=setup(t.store);for(const [id,value]of Object.entries(edits))assert.equal(reload.get(id).value,value);
  assert.match(reload.message(),/Przywrócono lokalny szkic/);assert.equal(reload.writes.length,0);
  reload.edit('compose-sender-name','');reload.consent();reload.save();assert.equal(setup(t.store).get('compose-sender-name').value,'');
});
test('delete resets example, survives reload and preserves unrelated storage',()=>{
  const t=setup(new Map([['unrelated-demo-setting','preserve']]));t.edit('compose-description','Syntetyczny szkic do usunięcia');t.consent();t.save();t.reset();
  assert.deepEqual(t.removals,[key]);assert.equal(t.store.has(key),false);assert.equal(t.store.get('unrelated-demo-setting'),'preserve');
  assert.match(t.message(),/Usunięto lokalny szkic/);assert.equal(t.get('compose-sender-name').value,'Osoba Syntetyczna A');assert.equal(setup(t.store).get('compose-description').value,t.get('compose-description').value);
});
test('corrupt, unknown and credential-shaped records are refused without mutation',()=>{
  const good=setup();good.consent();good.save();const original=JSON.parse(good.store.get(key));
  const cases=['{',JSON.stringify({...original,version:2}),JSON.stringify({...original,token:'SYNTHETIC-NOT-A-CREDENTIAL'}),JSON.stringify({...original,form:{...original.form,password:'SYNTHETIC-NOT-A-PASSWORD'}}),JSON.stringify({...original,form:{...original.form,document_type:['synthetic-request']}}),'x'.repeat(65537)];
  for(const raw of cases){const t=setup(new Map([[key,raw]]));assert.match(t.message(),/Nie przywrócono/);assert.equal(t.store.get(key),raw);assert.equal(t.writes.length,0);assert.equal(t.removals.length,0);assert.equal(t.get('compose-sender-name').value,'Osoba Syntetyczna A');}
});
test('storage denial and quota errors never report successful save or deletion',()=>{
  const denied=setup(new Map(),{get:true,set:true,remove:true});assert.match(denied.message(),/Nie przywrócono/);denied.consent();denied.save();assert.match(denied.message(),/Nie zapisano szkicu/);assert.equal(denied.writes.length,0);
  denied.edit('compose-description','Syntetyczny tekst pozostawiony');denied.reset();assert.match(denied.message(),/Nie usunięto/);assert.equal(denied.get('compose-description').value,'Syntetyczny tekst pozostawiony');
});
test('local save and restore leave production controls disabled',()=>{
  const t=setup();t.consent();t.save();
  for(const page of [t,setup(t.store)])for(const id of ['compose-save','compose-refresh','compose-generate','compose-validate','compose-render','compose-plan','compose-profile'])assert.equal(page.get(id).disabled,true,id);
});
console.log(JSON.stringify({scope:'NEW_LOCAL_DRAFT_ONLY',passed:tests.length,failed:0,network_requests:0}));
