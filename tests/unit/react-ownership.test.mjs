// T2: actual React DOM with jsdom and controlled promises; no browser or service calls.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire,registerHooks} from 'node:module';
import {resolve,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const fixtureRoot=process.env.OCR_GATEWAY_REACT_FIXTURE_ROOT
  ? resolve(process.env.OCR_GATEWAY_REACT_FIXTURE_ROOT)
  : fileURLToPath(new URL('../../',import.meta.url));
const fixtureRequire=createRequire(pathToFileURL(join(fixtureRoot,'package.json')));
const React=fixtureRequire('react');
const {act}=React;
const {createRoot}=fixtureRequire('react-dom/client');
const {JSDOM}=fixtureRequire('jsdom');
const hookSource=process.env.OCR_GATEWAY_REACT_HOOK_SOURCE
  ? pathToFileURL(resolve(process.env.OCR_GATEWAY_REACT_HOOK_SOURCE)).href
  : new URL('../../src/react.ts',import.meta.url).href;
const loader=registerHooks({
  resolve(specifier,context,nextResolve){
    if(specifier==='react'&&context.parentURL===hookSource)
      return {url:pathToFileURL(fixtureRequire.resolve('react')).href,shortCircuit:true};
    return nextResolve(specifier,context);
  },
});
let useOCRGateway;
try{({useOCRGateway}=await import(hookSource));}
finally{loader.deregister();}

const options={concurrency:false,timeout:3000};
const request=name=>({document:{text:name}});
function result(text){
  const primary={id:`document-${text}`,provider:'fixture',text,pages:[],citations:[],chunks:[],warnings:[]};
  return {id:`result-${text}`,document:{mimeType:'text/plain'},primary,results:[primary],routing:{router:'explicit',providers:['fixture'],reason:'Authored fixture'},errors:[],warnings:[],durationMs:0};
}
function client(){
  const calls=[];
  return {
    calls,
    parse(input,{signal}){
      let resolve,reject;
      const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
      calls.push({request:input,signal,resolve,reject});
      return promise;
    },
  };
}
const observe=promise=>promise.then(value=>({value}),error=>({error}));
async function start(view,name){
  let promise;
  await act(async()=>{promise=observe(view.current.parse(request(name)));});
  return {promise};
}
async function complete(call,promise,value){
  await act(async()=>{call.resolve(value);await promise;});
}
async function fail(call,promise,error){
  await act(async()=>{call.reject(error);await promise;});
}
async function mount(initialClient,{strict=false,layout}={}){
  const dom=new JSDOM('<div id="root"></div>',{url:'https://fixture.invalid'});
  const globals=['window','document','IS_REACT_ACT_ENVIRONMENT'];
  const previous=new Map(globals.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  for(const [name,value] of [['window',dom.window],['document',dom.window.document],['IS_REACT_ACT_ENVIRONMENT',true]])
    Object.defineProperty(globalThis,name,{configurable:true,writable:true,value});
  const history=[];
  let current;
  function Child({hook,onLayout}){
    React.useLayoutEffect(()=>{onLayout?.(hook);},[hook.parse,onLayout]);
    return React.createElement('section',null,
      React.createElement('button',{id:'upload',disabled:hook.loading},'Upload'),
      React.createElement('output',null,hook.error?.message??hook.data?.primary.text??(hook.loading?'loading':'empty')));
  }
  function Probe({gateway,onLayout}){
    current=useOCRGateway(gateway);
    history.push({client:gateway,data:current.data,error:current.error,loading:current.loading});
    return React.createElement(Child,{hook:current,onLayout});
  }
  const root=createRoot(dom.window.document.getElementById('root'));
  let live=true;
  const view={
    get current(){return current;},
    get uploadDisabled(){return dom.window.document.getElementById('upload').disabled;},
    history,
    async render(gateway,onLayout){
      await act(async()=>{
        const element=React.createElement(Probe,{gateway,onLayout});
        root.render(strict?React.createElement(React.StrictMode,null,element):element);
      });
    },
    async unmount(){if(live){live=false;await act(async()=>root.unmount());}},
    async close(){
      try{await view.unmount();}
      finally{
        dom.window.close();
        for(const name of globals){const descriptor=previous.get(name);if(descriptor)Object.defineProperty(globalThis,name,descriptor);else delete globalThis[name];}
      }
    },
  };
  try{await view.render(initialClient,layout);return view;}
  catch(error){await view.close();throw error;}
}

test('client replacement clears a pending parse and restores an idle upload control',options,async()=>{
  const oldClient=client(),replacement=client();
  const view=await mount(oldClient);
  try{
    const pending=await start(view,'old');
    assert.equal(view.current.loading,true);
    await view.render(replacement);
    assert.equal(oldClient.calls[0].signal.aborted,true);
    assert.equal(view.current.loading,false);
    assert.equal(view.uploadDisabled,false);
    assert.equal(view.current.data,null);
    assert.equal(view.current.error,null);
    await complete(oldClient.calls[0],pending.promise,result('old'));
    assert.equal(view.current.data,null);
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});

test('replacement hides prior data and errors before its passive setup publishes',options,async()=>{
  const oldClient=client(),replacement=client();
  const view=await mount(oldClient);
  try{
    const success=await start(view,'seed');
    await complete(oldClient.calls[0],success.promise,result('seed'));
    const failure=await start(view,'bad');
    await fail(oldClient.calls[1],failure.promise,new Error('old failure'));
    assert.equal(view.current.data.primary.text,'seed');
    assert.equal(view.current.error.message,'old failure');
    const before=view.history.length;
    await view.render(replacement);
    const firstReplacement=view.history.slice(before).find(value=>value.client===replacement);
    assert.deepEqual({data:firstReplacement.data,error:firstReplacement.error,loading:firstReplacement.loading},{data:null,error:null,loading:false});
    assert.equal(view.current.data,null);
    assert.equal(view.current.error,null);
  }finally{await view.close();}
});

test('late prior-client resolve reject and cancel cannot clear replacement work',options,async()=>{
  const oldClient=client(),replacement=client();
  const view=await mount(oldClient);
  try{
    const first=await start(view,'old first');
    const second=await start(view,'old second');
    const oldCancel=view.current.cancel;
    await view.render(replacement);
    const current=await start(view,'replacement');
    await act(async()=>oldCancel());
    await complete(oldClient.calls[0],first.promise,result('stale result'));
    await fail(oldClient.calls[1],second.promise,new Error('stale failure'));
    assert.equal(replacement.calls[0].signal.aborted,false);
    assert.equal(view.current.loading,true);
    assert.equal(view.current.data,null);
    assert.equal(view.current.error,null);
    await complete(replacement.calls[0],current.promise,result('replacement'));
    assert.equal(view.current.data.primary.text,'replacement');
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});

test('a replacement parse started in a child layout effect survives old passive cleanup',options,async()=>{
  const oldClient=client(),replacement=client();
  const view=await mount(oldClient);
  try{
    const old=await start(view,'old');
    let pending;
    await view.render(replacement,hook=>{pending=observe(hook.parse(request('layout')));});
    assert.equal(oldClient.calls[0].signal.aborted,true);
    assert.equal(replacement.calls.length,1);
    assert.equal(replacement.calls[0].signal.aborted,false);
    assert.equal(view.current.loading,true);
    await complete(replacement.calls[0],pending,result('layout'));
    await complete(oldClient.calls[0],old.promise,result('old'));
    assert.equal(view.current.data.primary.text,'layout');
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});

test('StrictMode replay and unmount preserve only current owned work',options,async()=>{
  const gateway=client(),pending=[];
  const view=await mount(gateway,{strict:true,layout:hook=>pending.push(observe(hook.parse(request('strict'))))});
  try{
    assert.equal(gateway.calls.length,2);
    assert.equal(gateway.calls[0].signal.aborted,true);
    assert.equal(gateway.calls[1].signal.aborted,false);
    assert.equal(view.current.loading,true);
    await complete(gateway.calls[0],pending[0],result('replayed'));
    assert.equal(view.current.loading,true);
    await complete(gateway.calls[1],pending[1],result('current'));
    assert.equal(view.current.data.primary.text,'current');
    const last=await start(view,'unmount');
    await view.unmount();
    assert.equal(gateway.calls[2].signal.aborted,true);
    await complete(gateway.calls[2],last.promise,result('after unmount'));
  }finally{await view.close();}
});

test('overlapping parses retain same-client data and ignore superseded failures',options,async()=>{
  const gateway=client(),view=await mount(gateway);
  try{
    const seed=await start(view,'seed');
    await complete(gateway.calls[0],seed.promise,result('seed'));
    const older=await start(view,'older'),newer=await start(view,'newer');
    assert.equal(gateway.calls[1].signal.aborted,true);
    assert.equal(view.current.data.primary.text,'seed');
    await fail(gateway.calls[1],older.promise,new Error('superseded'));
    assert.equal(view.current.loading,true);
    assert.equal(view.current.error,null);
    await complete(gateway.calls[2],newer.promise,result('newer'));
    assert.equal(view.current.data.primary.text,'newer');
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});

test('cancel publishes idle before an abort listener starts a newer parse',options,async()=>{
  const gateway=client(),view=await mount(gateway);
  try{
    const older=await start(view,'older');
    let newer;
    gateway.calls[0].signal.addEventListener('abort',()=>{newer=observe(view.current.parse(request('reentered')));},{once:true});
    await act(async()=>view.current.cancel());
    assert.equal(gateway.calls.length,2);
    assert.equal(gateway.calls[1].signal.aborted,false);
    assert.equal(view.current.loading,true);
    await fail(gateway.calls[0],older.promise,new Error('cancelled'));
    assert.equal(view.current.error,null);
    assert.equal(view.current.loading,true);
    await complete(gateway.calls[1],newer,result('reentered'));
    assert.equal(view.current.data.primary.text,'reentered');
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});

test('a superseding parse yields to a newer synchronous abort-listener parse',options,async()=>{
  const gateway=client(),view=await mount(gateway);
  try{
    const first=await start(view,'first');
    let reentered;
    gateway.calls[0].signal.addEventListener('abort',()=>{reentered=observe(view.current.parse(request('reentered')));},{once:true});
    const superseded=await start(view,'superseded before dispatch');
    const cancelled=await superseded.promise;
    assert.equal(cancelled.error.name,'AbortError');
    assert.deepEqual(gateway.calls.map(call=>call.request.document.text),['first','reentered']);
    assert.equal(view.current.loading,true);
    await complete(gateway.calls[0],first.promise,result('first'));
    assert.equal(view.current.loading,true);
    await complete(gateway.calls[1],reentered,result('reentered'));
    assert.equal(view.current.data.primary.text,'reentered');
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});

test('errors normalize and explicit cancellation fences a late successful result',options,async()=>{
  const gateway=client(),view=await mount(gateway);
  try{
    const failure=await start(view,'bad');
    await fail(gateway.calls[0],failure.promise,'not an Error');
    assert.equal(view.current.error.message,'Parsing failed');
    assert.equal(view.current.loading,false);
    const pending=await start(view,'cancelled');
    await act(async()=>view.current.cancel());
    assert.equal(gateway.calls[1].signal.aborted,true);
    assert.equal(view.current.loading,false);
    assert.equal(view.current.error,null);
    await complete(gateway.calls[1],pending.promise,result('late'));
    assert.equal(view.current.data,null);
    assert.equal(view.current.error,null);
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});

test('obsolete callbacks cannot publish into a returned client owner',options,async()=>{
  const firstClient=client(),middleClient=client(),view=await mount(firstClient);
  try{
    const oldParse=view.current.parse,oldCancel=view.current.cancel;
    await view.render(middleClient);
    const middle=await start(view,'middle');
    await complete(middleClient.calls[0],middle.promise,result('middle'));
    await view.render(firstClient);
    assert.equal(view.current.data,null);
    const current=await start(view,'returned client');
    let obsolete;
    await act(async()=>{obsolete=observe(oldParse(request('obsolete callback')));oldCancel();});
    assert.equal(firstClient.calls[0].signal.aborted,false);
    assert.equal(view.current.loading,true);
    await complete(firstClient.calls[1],obsolete,result('obsolete'));
    assert.equal(view.current.data,null);
    assert.equal(view.current.loading,true);
    await complete(firstClient.calls[0],current.promise,result('returned client'));
    assert.equal(view.current.data.primary.text,'returned client');
    assert.equal(view.current.loading,false);
  }finally{await view.close();}
});
