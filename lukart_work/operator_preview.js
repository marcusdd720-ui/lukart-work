// Display only raster pages derived from the authorized persisted PDF.
const previewPages=document.getElementById('previewPages');
const pdfStatus=document.getElementById('pdfStatus');
let pageUrls=[];
const originalClearArtifact=clearArtifact;
clearArtifact=function(){
  originalClearArtifact();
  previewPages.hidden=true;previewPages.replaceChildren();pdfStatus.textContent='';
  for(const url of pageUrls)URL.revokeObjectURL(url);
  pageUrls=[];
};
function decodeLocalBytes(encoded){
  const raw=atob(encoded),bytes=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
  return bytes;
}
const originalDocxClick=document.getElementById('docx').onclick;
document.getElementById('docx').onclick=()=>{download.textContent='Pobierz DOCX';originalDocxClick();};
document.getElementById('pdf').onclick=async()=>{
  if(!knownCase()||!idReady(render.value))return;
  if(!token.value.trim()){
    result.textContent='Brak tokenu dostępu. Wklej aktualny token uprawnienia.';
    token.focus();return;
  }
  const current=++generation;clearArtifact();send.disabled=true;
  pdfStatus.textContent='Wczytywanie i wyświetlanie stron PDF…';
  try{
    const response=await fetch('/api/query_finalization',{method:'POST',cache:'no-store',credentials:'omit',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+token.value,
        'Accept':'application/vnd.lukart.local-pdf-preview+json'},
      body:JSON.stringify({contract:'urn:lukart:work:FinalizationQuery:1.0.0',operation:'ReadFinalArtifact',
        tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),render_id:render.value.trim(),format:'PDF'})});
    const data=await response.json();if(current!==generation)return;
    if(response.status===503&&data.error==='PDF_PREVIEW_NOT_CONFIGURED'){
      await submit('query_finalization',{contract:'urn:lukart:work:FinalizationQuery:1.0.0',operation:'ReadFinalArtifact',
        tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),render_id:render.value.trim(),format:'PDF'});
      if(generation===current+1)pdfStatus.textContent='Podgląd nie jest skonfigurowany. Możesz pobrać oryginalny PDF.';
      return;
    }
    if(!response.ok||data.kind!=='LOCAL_PDF_PREVIEW'||!Array.isArray(data.pages)||!data.pages.length){
      pdfStatus.textContent=response.status===403?'Odmowa dostępu do PDF. Wczytaj aktualny token.':
        'Nie udało się utworzyć podglądu PDF. Dokument nie został zmieniony.';
      return;
    }
    artifactUrl=URL.createObjectURL(new Blob([decodeLocalBytes(data.pdf_base64)],{type:'application/pdf'}));
    download.href=artifactUrl;download.download='document.pdf';download.textContent='Pobierz oryginalny PDF';download.hidden=false;
    const images=data.pages.map(item=>{
      const image=document.createElement('img');image.alt='Strona '+item.page+' dokumentu PDF';
      const url=URL.createObjectURL(new Blob([decodeLocalBytes(item.png_base64)],{type:'image/png'}));
      pageUrls.push(url);image.src=url;previewPages.append(image);return image;
    });
    await Promise.all(images.map(image=>image.decode()));if(current!==generation)return;
    if(images.some(image=>image.naturalWidth===0))throw Error('PDF_IMAGE_NOT_LOADED');
    previewPages.hidden=false;
    pdfStatus.textContent='Wyświetlono PDF — liczba stron: '+images.length+'.';
    result.textContent='Podgląd pochodzi z zapisanego PDF. SHA-256: '+data.source_sha256;
    const status=document.getElementById('sessionStatus');
    if(status)status.textContent='PDF jest wyświetlony w sekcji 5. Możesz również pobrać oryginalny plik.';
  }catch{
    if(current===generation){
      clearArtifact();pdfStatus.textContent='Nie udało się wyświetlić PDF. Sprawdź połączenie z panelem.';
    }
  }finally{if(current===generation)send.disabled=false;}
};
