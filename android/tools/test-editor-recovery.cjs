const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const code = fs.readFileSync(__dirname + '/../app/src/main/assets/editor-recovery.js','utf8');
const pause = () => new Promise(r=>setTimeout(r,20));
const local = new Map(), disk = new Map();
async function page(search='') {
 const listeners={}, elements={};
 for(const id of ['editorTextarea','editorSection','previewContent','logoInput','title','list_no','list_type','output_format','colTp','result','resultMessage','resultButtonsOld','resultButtonsNew']) elements[id]={id,value:'',style:{display:'none'},checked:false,files:[],scrollTop:0,addEventListener(){}};
 elements.list_type.value='M';elements.output_format.value='old';
 let inline=null,downloads=0;
 const context={console,Date,Promise,JSON,URLSearchParams,Set,Map,setTimeout,clearTimeout,
 location:{pathname:'/make_html',search},localStorage:{getItem:k=>local.get(k)||null,setItem:(k,v)=>local.set(k,v)},
 alert:message=>{throw Error(message)},requestAnimationFrame:fn=>setTimeout(fn,0),scrollY:0,scrollTo(x,y){this.scrollY=y;},
 document:{getElementById:id=>elements[id],querySelector:()=>inline,querySelectorAll:()=>Object.values(elements).filter(x=>['title','list_no','list_type','output_format','colTp'].includes(x.id)),addEventListener:(n,fn)=>(listeners[n]??=[]).push(fn)},
 addEventListener:(n,fn)=>(listeners[n]??=[]).push(fn),
 indexedDB:{open(){const req={};setTimeout(()=>{req.result={transaction(){const tx={objectStore(){return {put(v,k){disk.set(k,structuredClone(v));},get(k){const r={};queueMicrotask(()=>{r.result=structuredClone(disk.get(k));r.onsuccess();});return r;}}}};setTimeout(()=>tx.oncomplete?.(),0);return tx;}};req.onsuccess();},0);return req;}},
 currentPreviewSort:'alpha',selectListType(){},selectOutputFormat(){},refreshLogoState(){},loadSessionContent(){throw Error('obsolete loader ran')},
 showEditor(){elements.editorSection.style.display='block';},showTab(tab){elements.editorTextarea.style.display=tab==='edit'?'block':'none';},updateItemCount(){},
 uploadNew(){elements.editorTextarea.value='';elements.editorSection.style.display='none';elements.result.style.display='none';},
 startMarkdown(){elements.editorTextarea.value='';elements.editorSection.style.display='block';},
 downloadGenerated(){downloads++;assert(disk.get('output')?.new);},shareHTML(){},
 };context.window=context;context.top=context;
 vm.createContext(context);vm.runInContext(code,context);
 for(const fn of listeners.DOMContentLoaded||[])fn();
 for(const fn of listeners.load||[])fn();
 await pause();await pause();
 return {context,e:elements,listeners,setInline:v=>inline=v,downloads:()=>downloads};
}
(async()=>{
 let p=await page();
 p.e.editorTextarea.value='Panadol----- 10%|50|1|2';p.context.showEditor();
 p.e.title.value='My vendor';p.e.colTp.checked=true;p.context.currentPreviewSort='rate';p.context.scrollY=900;
 p.context._generatedHTML={new:{name:'test.htm',html:'<html>Saved</html>'},old:null};p.e.result.style.display='block';
 await p.context.__medlistSaveDraft();
 await p.context.downloadGenerated();assert.equal(p.downloads(),1);
 p=await page();
 assert.equal(p.e.editorTextarea.value,'Panadol----- 10%|50|1|2');assert.equal(p.e.title.value,'My vendor');assert.equal(p.e.colTp.checked,true);
 assert.equal(p.context.currentPreviewSort,'rate');assert.equal(p.context.scrollY,900);
 assert.equal(p.context._generatedHTML.new.html,'<html>Saved</html>');assert.equal(p.e.result.style.display,'block');
 p.setInline({value:'22',closest:tag=>tag==='td'?{getAttribute:()=>"editCellInline(this,'value')"}:{dataset:{name:'Panadol',value:'10%',tp:'50',bonus:'1',tax:'2',extended:'1',lineIndex:'0'}}});
 for(const fn of p.listeners.input)fn();
 // Core saved synchronously, before any debounce or async disk completion.
 assert.equal(JSON.parse(local.get('medlist.native.editor.v1')).text,'Panadol----- 22%|50|1|2');
 await pause();p=await page();assert.equal(p.e.editorTextarea.value,'Panadol----- 22%|50|1|2');
 p.context.uploadNew();await pause();p=await page();assert.equal(p.e.editorTextarea.value,'');assert.equal(p.e.editorSection.style.display,'none');assert.equal(p.context._generatedHTML,null);
 p.e.editorTextarea.value='Old draft----- 5%';p.context.showEditor();await p.context.__medlistSaveDraft();
 p=await page('?sharedid=new-document');assert.equal(p.e.editorTextarea.value,'');
 p.e.editorTextarea.value='New import----- 8%';p.context.showEditor();await p.context.__medlistSaveDraft();
 p=await page();assert.equal(p.e.editorTextarea.value,'New import----- 8%');
 const java=fs.readFileSync(__dirname+'/../app/src/main/java/com/medlist/nativeapp/MainActivity.java','utf8');
 assert(!java.includes('web.saveState('));assert(!java.includes('web.restoreState('));assert(java.includes('state.putString("pendingDownload"'));
 console.log('PASS: restart, settings, pending inline edits, generated downloads, explicit reset, fresh shared import and small native state');
})().catch(e=>{console.error(e);process.exitCode=1;});
