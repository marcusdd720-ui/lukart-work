// Focused frontend contract checks. Simulated DOM/HTTP, NOT browser or engine E2E.
// Usage: node tests/test_legal_os_composer_dom.cjs extracted-case.js extracted-case.html
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {randomUUID} = require('node:crypto');
const script = fs.readFileSync(process.argv[2], 'utf8');
const html = fs.readFileSync(process.argv[3], 'utf8');
const plan = '11111111-1111-4111-8111-111111111111';
const draft = '22222222-2222-4222-8222-222222222222';
const run = '33333333-3333-4333-8333-333333333333';
const render = '44444444-4444-4444-8444-444444444444';
const form = {description:'Syntetyczny opis sprawy.', document_type:'synthetic',
  sender:{name:'Osoba Testowa',address:{country:'PL',postal_code:'00-000',lines:['ul. Syntetyczna 1']}},
  recipient:{name:'Instytucja Testowa',address:{country:'PL',postal_code:'00-000',lines:['ul. Syntetyczna 2']}}};
class Element {
  constructor(){this.value='';this.disabled=false;this.dataset={};this.options=[];this.listeners={};this.textContent='';this.children=[];this.classList={toggle(){}};}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  async emit(name){for(const fn of this.listeners[name]??[])await fn({target:this});}
  replaceChildren(...children){this.children=children;this.options=children;this.value=children[0]?.value??'';}
  add(option){this.options.push(option);if(this.options.length===1)this.value=option.value;}
  append(...children){this.children.push(...children);}
  set selectedIndex(index){this.value=this.options[index]?.value??'';}
  get childElementCount(){return this.children.length;}
  click(){this.clicked=true;}
  remove(){}
}
function setup(){
  const elements=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  const requests=[];let seq=8;let failure=null;let delayed=null;let downloads=0;
  const context={result_type:'COMPOSITION_CONTEXT',document_types:[{id:'synthetic',label:'Pismo testowe'}],
    profiles:['QUICK'],plans:[{id:plan,revision:1,label:'Plan testowy',form}],required_gate:null};
  const fetch=async (url,options)=>{
    assert.equal(url,'/api/embedded_session');
    assert.equal(options.credentials,'omit');
    const body=JSON.parse(options.body);requests.push(body);
    assert.equal(options.headers.Authorization,'Bearer synthetic-unit-only');
    if(failure===body.action)return {ok:false,status:403};
    let data;
    switch(body.action){
      case 'open_case':data={result_type:'CASE_HEAD',case_sequence:seq,heads:[]};break;
      case 'list_saved':data={result_type:'SAVED_RENDERS',items:[{render_id:render,created_at:'2026-10-27T12:00:00Z'}]};break;
      case 'list_drafts':data={result_type:'DRAFT_LIST',drafts:[{id:draft,revision:1}]};break;
      case 'composition_context':data={...context,case_sequence:seq};break;
      case 'save_document_brief':seq++;data={result_type:'DOCUMENT_BRIEF_SAVED',native_result:{registration:{state:'APPLIED',case_sequence:seq},ingestion:{body:{status:'EXTRACTED',fragments:[{text:JSON.stringify(form)}],candidates:[]}},source_id:plan,run_id:run}};break;
      case 'review_context':data={result_type:'REVIEW_CONTEXT',case_sequence:seq,candidates:[]};break;
      case 'generate_document':seq++;data={result_type:'DOCUMENT_GENERATED',draft:{id:draft,revision:1}};break;
      case 'validate_document':seq++;data={result_type:'DOCUMENT_VALIDATED',draft:{id:draft,revision:2},validation_run_id:run};break;
      case 'render_document':seq++;data={result_type:'DOCUMENT_RENDERED',render_id:render};break;
      case 'download':return {ok:true,blob:async()=>{downloads++;return new Blob(['synthetic']);}};
      default:throw new Error('Unexpected synthetic action: '+body.action);
    }
    return {ok:true,json:async()=>{
      if(delayed===body.action){elements.token.value='';await elements.token.emit('input');}
      return data;
    }};
  };
  vm.runInNewContext(script,{document:{getElementById(id){assert.ok(elements[id],id);return elements[id];},
      createElement:()=>new Element(),body:new Element()},
    window:{addEventListener(){}},Option:function(text,value){this.textContent=text;this.value=value;},
    fetch,crypto:{randomUUID},URL:{createObjectURL:()=> 'blob:synthetic',revokeObjectURL(){}},
    setTimeout,TextEncoder,Blob,console});
  return {elements,requests,setFailure:value=>{failure=value;},setDelayed:value=>{delayed=value;},downloads:()=>downloads};
}
async function flush(){for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));}
async function open(t){t.elements.token.value='synthetic-unit-only';await t.elements.token.emit('input');await t.elements.open.emit('click');await flush();}
async function test(name,fn){await fn();console.log('PASS '+name);}
(async()=>{
  await test('initial gate and authoritative plan prefilling',async()=>{
    const t=setup();assert.equal(t.elements['compose-save'].disabled,true);await open(t);
    assert.equal(t.elements['compose-description'].value,form.description);
    assert.equal(t.elements['compose-sender-name'].value,form.sender.name);
    assert.equal(t.elements['compose-generate'].disabled,false);
    assert.equal(t.requests.filter(r=>r.action==='generate_document').length,0);
  });
  await test('required form data prevents write',async()=>{
    const t=setup();await open(t);t.elements['compose-recipient-postal'].value='';
    await t.elements['compose-save'].emit('click');
    assert.equal(t.requests.filter(r=>r.action==='save_document_brief').length,0);
    assert.match(t.elements['compose-result'].textContent,/Uzupełnij/);
  });
  await test('one interface dispatches save/generate/validate/render and both downloads',async()=>{
    const t=setup();await open(t);
    for(const id of ['compose-save','compose-generate','compose-validate','compose-render']){
      assert.equal(t.elements[id].disabled,false,id);await t.elements[id].emit('click');
    }
    const saved=t.requests.find(r=>r.action==='save_document_brief');assert.deepEqual(saved.form,form);
    assert.ok(t.requests.some(r=>r.action==='review_context'));
    assert.match(t.elements['intake-preview'].textContent,/Osoba Testowa/);
    const generated=t.requests.find(r=>r.action==='generate_document');assert.equal(generated.plan_id,plan);
    assert.equal(generated.expected_case_sequence,9);
    const rendered=t.requests.find(r=>r.action==='render_document');assert.equal(rendered.validation_run_id,run);
    assert.equal(rendered.draft_revision,2);assert.equal(rendered.expected_case_sequence,11);
    await t.elements.pdf.emit('click');await flush();await t.elements.docx.emit('click');await flush();
    assert.equal(t.downloads(),2);
    for(const request of t.requests){assert.ok(!('tenant_id' in request));assert.ok(!('confirmed' in request));}
    await t.elements.clear.emit('click');assert.equal(t.elements['compose-sender-name'].value,'');assert.equal(t.elements.token.value,'');
  });
  await test('write rejection locks controls without automatic retry',async()=>{
    const t=setup();await open(t);t.setFailure('generate_document');
    await t.elements['compose-generate'].emit('click');assert.equal(t.elements['compose-generate'].disabled,true);
    await t.elements['compose-generate'].emit('click');
    assert.equal(t.requests.filter(r=>r.action==='generate_document').length,1);
    assert.match(t.elements['compose-result'].textContent,/Nie ponawiaj/);
  });
  await test('late context response cannot repopulate a cleared session',async()=>{
    const t=setup();await open(t);t.setDelayed('composition_context');
    await t.elements['compose-refresh'].emit('click');
    assert.equal(t.elements['compose-sender-name'].value,'');assert.equal(t.elements['compose-description'].value,'');
    assert.equal(t.elements['compose-generate'].disabled,true);
  });
  console.log('5/5 PASS; synthetic DOM/HTTP only; live engine/browser E2E NOT VERIFIED');
})().catch(error=>{console.error(error);process.exitCode=1;});
