const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const html = fs.readFileSync('android/app/src/main/assets/share.html', 'utf8');
assert(!/<(?:script|link|img)[^>]+(?:src|href)=/i.test(html), 'Chooser must not fetch remote resources');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(x => x[1]);
const chooser = scripts.at(-1);
async function scenario(button, path, options={}) {
 const elements = {};
 const element = id => elements[id] ||= {style:{},textContent:'',disabled:false,addEventListener(_,f){this.click=f},appendChild(){}};
 const bytes = Buffer.from('<html>medicine & exact bytes</html>');
 element('shared-payload').textContent = JSON.stringify({filename:'DOC.htm',ext:options.pdf?'.pdf':'.htm',type:'HTML',size:bytes.length,data_b64:bytes.toString('base64')});
 let puts=0, nav='';
 const store={base64ToBlob:(v)=>Buffer.from(v,'base64'),fmtSize:()=> '1 KB',putFile:async(n,t,e,b)=>{puts++;assert.deepEqual(b,bytes);if(options.fail&&puts===1)throw Error('storage');return {id:'local-id'}},clearOtherDestinationStates:async()=>{},appendToIndexBatch:async()=>({ok:!options.full}),getDiffState:async()=>({}),setDiffState:async()=>{},deleteFile:async()=>{}};
 const c={document:{getElementById:element,querySelectorAll:()=>Object.values(elements).filter(x=>x.click),createElement:()=>element('temporary')},window:{location:{get href(){return nav},set href(v){nav=v}}},SharedStore:store,performance:{now:()=>0},console:{debug(){},warn(){}},requestAnimationFrame:f=>f(),setTimeout:f=>f(),Promise};
 vm.createContext(c);vm.runInContext(chooser,c);
 assert.equal(puts,0,'No storage/upload before action');
 element(button).click();
 await new Promise(r=>setImmediate(r));
 if(options.fail){assert.equal(nav,'');assert.equal(element(button).disabled,false);element(button).click();await new Promise(r=>setImmediate(r));}
 if(options.full){assert.equal(nav,'');assert.equal(element('destGenHtml').disabled,false);element('destGenHtml').click();await new Promise(r=>setImmediate(r));assert.equal(puts,1,'Reuse saved record after full batch');}
 assert.equal(nav,path);
}
(async()=>{
 await scenario('destUpload','/');
 await scenario('destSearch','/search?sharedid=local-id');
 await scenario('destGenHtml','/make_html?sharedid=local-id');
 await scenario('destDiff','/diff');
 await scenario('destDedup','/deduplicate?sharedid=local-id');
 await scenario('destGenHtml','/make_html?sharedid=local-id',{fail:true});
 await scenario('destUpload','/make_html?sharedid=local-id',{full:true});
 console.log('PASS: local chooser, byte preservation, destinations, retry and full batch recovery');
})().catch(e=>{console.error(e);process.exit(1)});
