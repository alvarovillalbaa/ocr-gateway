import {randomUUID} from 'node:crypto';
import {builtInProviders,keysFromEnv} from './providers.js';
import {chooseProviders} from './routing.js';
import {normalizeDocument} from './normalize.js';
import {GatewayError,validateRequest} from './validation.js';
import {withDeadline} from './http.js';
import type {GatewayOptions,ParseClient,ParseRequest,ParseResult,ParsedDocument} from './types.js';

export const PRESETS:Record<'fast'|'balanced'|'rich',Partial<Omit<ParseRequest,'document'>>> = {
  fast:{mode:'auto',maxProviders:1,timeoutMs:30000,chunking:{maxCharacters:1600,overlap:160}},
  balanced:{mode:'auto',maxProviders:2,timeoutMs:120000,chunking:{maxCharacters:1600,overlap:160}},
  rich:{mode:'auto',maxProviders:2,timeoutMs:240000,features:['tables','images','charts','diagrams','equations'],chunking:{maxCharacters:2400,overlap:240}},
};
export function createOCRGateway(options:GatewayOptions={}){
  const adapters=[...builtInProviders(),...(options.providers??[])];
  if(new Set(adapters.map(a=>a.id)).size!==adapters.length)throw new GatewayError('duplicate_provider','Provider IDs must be unique');
  const keys={...(options.providerKeys??{})};
  const enabled=new Set(options.enabledProviders??adapters.map(a=>a.id));
  if([...enabled].some(id=>!adapters.some(a=>a.id===id)))throw new GatewayError('unknown_provider','Unknown enabled provider');
  const gateway:ParseClient & {providers:()=>{id:string;name:string;mimeTypes:string[];features:string[];enabled:boolean;configured:boolean}[]}={
    providers:()=>adapters.map(a=>({id:a.id,name:a.name,mimeTypes:a.mimeTypes,features:a.features,enabled:enabled.has(a.id),configured:!a.requiresKey||!!keys[a.id]})),
    async parse(input:ParseRequest,call={}){
      const started=Date.now();const request=validateRequest({...PRESETS.balanced,...options.defaults,...input});
      const requestKeys={...keys,...request.providerKeys};
      const unknown=[...(request.providers??[]),...(request.excludeProviders??[]),...Object.keys(request.providerKeys??{}),...Object.keys(request.providerOptions??{})].find(id=>!adapters.some(a=>a.id===id));
      if(unknown)throw new GatewayError('unknown_provider',`Unknown provider: ${unknown}`);
      const candidates=adapters.filter(a=>enabled.has(a.id)&&(!request.providers||request.providers.includes(a.id))&&!request.excludeProviders?.includes(a.id)&&(!a.requiresKey||!!requestKeys[a.id])&&(!request.document.url||a.supportsUrl!==false)&&a.mimeTypes.some(m=>m===request.document.mimeType||m==='*/*'||(m.endsWith('/*')&&request.document.mimeType?.startsWith(m.slice(0,-1))))&&(request.features??[]).every(f=>a.features.includes(f)));
      if(!candidates.length)throw new GatewayError('no_provider','No enabled, configured provider supports this document and requested features',503);
      return withDeadline(request.timeoutMs??120000,call.signal,async signal=>{
        const routing=await chooseProviders(request,candidates,options.router??{},options.fetch??fetch,signal);
        const max=request.maxProviders??2;
        if(!routing.providers.length||routing.providers.length>max||new Set(routing.providers).size!==routing.providers.length||routing.providers.some(id=>!candidates.some(a=>a.id===id)))throw new GatewayError('invalid_route','Router selected an unavailable provider',502);
        const errors:ParseResult['errors']=[];
        const run=async(id:string):Promise<ParsedDocument|undefined>=>{
          signal.throwIfAborted();
          const adapter=candidates.find(a=>a.id===id)!;
          try{
            const output=await adapter.parse(request.document,{apiKey:requestKeys[id],signal,fetch:options.fetch??fetch,options:request.providerOptions?.[id]??{},features:request.features??[]});
            signal.throwIfAborted();
            if(!output||!Array.isArray(output.pages)||!output.pages.length||output.pages.every(p=>!p.text?.trim()&&!p.blocks?.some(b=>b.text?.trim())))throw new GatewayError('empty_document','Provider returned no readable content',502);
            const blocks=output.pages.flatMap(p=>p.blocks??[]);
            if(output.pages.length>500||blocks.length>20000||output.pages.reduce((n,p)=>n+p.text.length,0)+blocks.reduce((n,b)=>n+b.text.length,0)>4_000_000)throw new GatewayError('output_too_large','Provider extraction exceeds 500 pages, 20000 blocks or 4000000 text characters',502);
            const normalized=normalizeDocument(id,output,request);
            if(Buffer.byteLength(JSON.stringify(normalized))>8_000_000)throw new GatewayError('output_too_large','Normalized provider result exceeds 8 MB; reduce document size or disable raw/image output',502);
            return normalized;
          }catch(e){errors.push({provider:id,code:e instanceof GatewayError?e.code:'provider_failed',message:e instanceof GatewayError?e.message:`${id} parsing failed`});return undefined;}
        };
        const results:ParsedDocument[]=[];
        if(request.mode==='parallel'||(request.mode==='auto'&&routing.providers.length>1)){
          for(const result of await Promise.all(routing.providers.map(run)))if(result)results.push(result);
        }else{for(const id of routing.providers){signal.throwIfAborted();const result=await run(id);if(result){results.push(result);break;}}}
        if(!results[0])throw new GatewayError('all_providers_failed',`All selected providers failed (${errors.map(e=>`${e.provider}:${e.code}`).join(', ')})`,502);
        const result:ParseResult={id:randomUUID(),document:{name:request.document.name,mimeType:request.document.mimeType!,url:request.document.url},primary:results[0],results,routing,errors,warnings:errors.length?['Some providers failed; inspect errors and per-document warnings.']:[],durationMs:Date.now()-started};
        if(Buffer.byteLength(JSON.stringify(result))>28_000_000)throw new GatewayError('output_too_large','Combined response exceeds 28 MB; reduce maxProviders or document size',502);
        return result;
      });
    }
  };return gateway;
}
export {keysFromEnv,GatewayError};
export type * from './types.js';
