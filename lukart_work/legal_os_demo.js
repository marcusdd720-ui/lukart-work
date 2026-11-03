(() => {
"use strict";
const $ = id => document.getElementById(id);
const example = {
  description: "Syntetyczna sprawa demonstracyjna: prośba o przekazanie przykładowej informacji. Bez rzeczywistych zdarzeń, roszczeń i danych klientów.",
  document_type: "synthetic-request",
  sender: {name: "Osoba Syntetyczna A", address: {lines: ["ul. Syntetyczna 1", "Miasto Testowe"], postal_code: "00-000", country: "PL"}},
  recipient: {name: "Instytucja Syntetyczna B", address: {lines: ["ul. Demonstracyjna 2", "Miasto Testowe"], postal_code: "00-000", country: "PL"}}
};
const types = {"synthetic-request": "Wniosek — przykład syntetyczny", "synthetic-letter": "Pismo ogólne — przykład syntetyczny"};
const draftKey = "lukart.legal-os.demo.synthetic-draft.v1";
let revision = 0;
function note(text, error=false) { $("status").textContent=text; $("status").classList.toggle("error",error); }
function draftNote(text) { $("demo-draft-status").textContent=text; }
function revokeConsent() { $("demo-synthetic-only").checked=false; $("demo-save-local").disabled=true; }
function invalidate() {
  revision++;
  revokeConsent();
  draftNote("Niezapisane zmiany. Zapis lokalny wymaga potwierdzenia danych syntetycznych.");
  $("demo-document").replaceChildren();
  $("demo-document").textContent="Dane zmienione. Wybierz „Pokaż podgląd danych”, aby odświeżyć podgląd.";
}
function fillForm(form) {
  $("compose-type").replaceChildren(...Object.entries(types).map(([value,label])=>new Option(label,value)));
  $("compose-type").value=form.document_type;
  $("compose-description").value=form.description;
  for (const role of ["sender","recipient"]) {
    const party=form[role];
    for (const [field,value] of Object.entries({name:party.name,lines:party.address.lines.join("\n"),postal:party.address.postal_code,country:party.address.country})) $("compose-"+role+"-"+field).value=value;
  }
  invalidate();
}
function reset() {
  fillForm(example);
  $("case-state").textContent="Syntetyczna · bez WORK";
  $("case-title").textContent="Przykładowa sprawa — demonstracja formularza";
  $("case-seq").textContent="—"; $("heads").textContent="—";
  $("compose-plan").replaceChildren(new Option("ZABLOKOWANE — brak zatwierdzonego planu WORK",""));
  $("compose-profile").replaceChildren(new Option("ZABLOKOWANE — brak autoryzowanego silnika",""));
  $("compose-plan").disabled=true; $("compose-profile").disabled=true;
  for (const id of ["compose-save","compose-refresh","compose-generate","compose-validate","compose-render"]) {
    $(id).disabled=true; $(id).title="Zablokowane w demo: wymaga autoryzowanego WORK";
  }
  note("Demo lokalne: dane syntetyczne. Nic nie zostało zapisane ani zatwierdzone w WORK.");
}
function readForm() {
  const form={description:$("compose-description").value,document_type:$("compose-type").value};
  for (const role of ["sender","recipient"]) form[role]={name:$("compose-"+role+"-name").value,address:{lines:$("compose-"+role+"-lines").value.split(/\r?\n/),postal_code:$("compose-"+role+"-postal").value,country:$("compose-"+role+"-country").value.toUpperCase()}};
  return form;
}
function safeDraftForm(form) {
  const keys=(value,expected)=>value!==null&&typeof value==="object"&&!Array.isArray(value)&&Object.keys(value).sort().join("|")===expected.sort().join("|");
  const text=(value,max)=>typeof value==="string"&&value.length<=max&&!/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value);
  if(!keys(form,["description","document_type","sender","recipient"])||!text(form.description,20000)||!text(form.document_type,80)||!Object.hasOwn(types,form.document_type))throw new Error("Invalid demo draft");
  const result={description:form.description,document_type:form.document_type};
  for(const role of ["sender","recipient"]) {
    const p=form[role], a=p?.address;
    if(!keys(p,["name","address"])||!text(p.name,500)||!keys(a,["lines","postal_code","country"])||!text(a.postal_code,32)||!text(a.country,2)||!Array.isArray(a.lines)||a.lines.length<1||a.lines.length>20||!a.lines.every(line=>text(line,500)))throw new Error("Invalid demo draft");
    result[role]={name:p.name,address:{lines:[...a.lines],postal_code:a.postal_code,country:a.country}};
  }
  return result; // Explicit allowlist: no credentials, WORK state or hidden DOM fields.
}
function restoreDraft() {
  try {
    const raw=localStorage.getItem(draftKey);
    if(raw===null) {draftNote("Brak lokalnego szkicu. Dane przykładowe nie są zapisywane automatycznie.");return;}
    if(raw.length>65536)throw new Error("Oversized draft");
    const data=JSON.parse(raw);
    if(data===null||typeof data!=="object"||Object.keys(data).sort().join("|")!=="form|kind|version"||data.version!==1||data.kind!=="SYNTHETIC_DEMO_DRAFT")throw new Error("Unsupported draft");
    fillForm(safeDraftForm(data.form));
    draftNote("Przywrócono lokalny szkic demonstracyjny po odświeżeniu. Brak zapisu do WORK.");
  } catch(_error) {draftNote("Nie przywrócono szkicu: pamięć jest niedostępna lub zapis ma nieprawidłowy format. Pozostawiono przykład; nie usunięto istniejącego zapisu.");}
}
$("demo-synthetic-only").addEventListener("change",()=>{$("demo-save-local").disabled=!$("demo-synthetic-only").checked;});
$("demo-save-local").addEventListener("click",()=>{
  if(!$("demo-synthetic-only").checked) {draftNote("Zapis zablokowany: potwierdź wyłącznie syntetyczne dane, bez sekretów.");return;}
  try {
    const data=JSON.stringify({kind:"SYNTHETIC_DEMO_DRAFT",version:1,form:safeDraftForm(readForm())});
    if(data.length>65536)throw new Error("Oversized draft");
    localStorage.setItem(draftKey,data);
    draftNote("Zapisano szkic lokalnie w tej przeglądarce. Zostanie przywrócony po F5. Nie zapisano danych w WORK.");
  } catch(_error) {draftNote("Nie zapisano szkicu: pamięć jest niedostępna, pełna lub dane przekraczają dozwolony zakres. Nie potwierdzono zapisu.");}
});
function preview(form) {
  const doc=$("demo-document"); doc.replaceChildren();
  function node(tag,text,cls) { const n=document.createElement(tag); n.textContent=text; if(cls)n.className=cls;doc.append(n); }
  node("p","PODGLĄD FORMULARZA · dane syntetyczne · bez generowania pisma");
  for (const role of ["sender","recipient"]) {
    const p=form[role]; node("address",(role==="sender"?"Nadawca\n":"Adresat\n")+p.name+"\n"+p.address.lines.join("\n")+"\n"+p.address.postal_code+" · "+p.address.country,role);
  }
  node("h3",types[form.document_type]); node("p",form.description);
  node("p","To podgląd wprowadzonych danych. Brak analizy prawnej, podstaw prawnych, podpisu i zatwierdzenia HUMAN. Nie jest wynikiem Generatora Pism 2.0.");
}
$("demo-preview").addEventListener("click",async()=>{
  const button=$("demo-preview"), current=revision; button.disabled=true;
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),5000);
  try {
    const response=await fetch("/demo/validate",{method:"POST",credentials:"omit",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify(readForm()),signal:controller.signal});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error==="DEMO_FORM_INCOMPLETE_OR_INVALID"?"Uzupełnij opis, rodzaj pisma oraz pełne dane i adresy obu stron.":"Podgląd zablokowany: "+data.error);
    if(current!==revision) {note("Dane zmieniły się podczas sprawdzania. Odśwież podgląd.");return;}
    preview(data.form); note("Kompletność formularza sprawdzona przez istniejący adapter. Podgląd gotowy; brak zapisu i generowania.");
    $("demo-document").scrollIntoView({behavior:"smooth",block:"start"});
  } catch(error) { if(current===revision){$("demo-document").textContent="Brak aktualnego podglądu — sprawdź formularz.";note(error.name==="AbortError"?"Przekroczono czas sprawdzania. Nie zapisano danych.":error.message,true);}}
  finally {clearTimeout(timer);button.disabled=false;}
});
$("demo-reset").addEventListener("click",()=>{
  try {localStorage.removeItem(draftKey);}
  catch(_error) {draftNote("Nie usunięto lokalnego szkicu: pamięć przeglądarki jest niedostępna. Dane formularza pozostawiono bez zmian.");return;}
  reset(); draftNote("Usunięto lokalny szkic i przywrócono dane przykładowe. Brak zapisu do WORK.");
});
for(const element of document.querySelectorAll("#compose-description, #compose-type, [id^='compose-sender-'], [id^='compose-recipient-']"))element.addEventListener("input",invalidate);
reset();
restoreDraft();
})();
