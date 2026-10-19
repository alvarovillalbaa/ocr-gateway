import {createServer,type IncomingMessage} from 'node:http';
import {GatewayError,validateRequest} from './validation.js';
import type {KeyPolicy} from './keys.js';
import type {createOCRGateway} from './core.js';

export interface ServerOptions {
  gateway:ReturnType<typeof createOCRGateway>;
  authenticate:(key:string)=>Promise<KeyPolicy|undefined>|KeyPolicy|undefined;
  allowRequestKeys?:boolean;allowedOrigins?:string[];maxConcurrent?:number;maxBodyBytes?:number;
}
async function body(req:IncomingMessage,max:number){const parts:Buffer[]=[];let size=0;for await(const part of req){size+=part.length;if(size>max)throw new GatewayError('body_too_large','Request exceeds body limit',413);parts.push(part);}try{return JSON.parse(Buffer.concat(parts).toString('utf8'));}catch{throw new GatewayError('invalid_json','Request body must be JSON');}}
export function createGatewayServer(options:ServerOptions){
  if(typeof options.authenticate!=='function')throw new GatewayError('missing_authenticator','Authentication is required',500);
  const buckets=new Map<string,{start:number;count:number}>();let active=0;
  const server=createServer(async(req,res)=>{
    let occupied=false;
    const send=(status:number,data:unknown)=>{if(res.destroyed||res.writableEnded)return;res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(status===204?undefined:JSON.stringify(data));};
    try{
      if(req.method==='GET'&&req.url==='/health')return send(200,{status:'ok',version:'0.1.0'});
      const origin=req.headers.origin;if(origin){if(!options.allowedOrigins?.includes(origin))throw new GatewayError('origin_not_allowed','Origin not allowed',403);res.setHeader('Access-Control-Allow-Origin',origin);res.setHeader('Vary','Origin');res.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type');res.setHeader('Access-Control-Allow-Methods','GET, POST, OPTIONS');}
      if(req.method==='OPTIONS')return send(204,null);
      const auth=req.headers.authorization;const policy=auth?.startsWith('Bearer ')?await options.authenticate(auth.slice(7)):undefined;
      if(!policy)throw new GatewayError('unauthorized','Valid gateway bearer key required',401);
      const now=Date.now();for(const [id,b] of buckets)if(now-b.start>=60000)buckets.delete(id);
      if(buckets.size>=10000&&!buckets.has(policy.id))throw new GatewayError('overloaded','Rate limiter capacity reached',503);
      const bucket=buckets.get(policy.id)??{start:now,count:0};buckets.set(policy.id,bucket);bucket.count++;
      if(bucket.count>policy.requestsPerMinute){res.setHeader('Retry-After',String(Math.ceil((60000-now+bucket.start)/1000)));throw new GatewayError('rate_limited','Request limit exceeded',429);}
      const all=options.gateway.providers();const allowed=new Set(policy.providers??all.map(p=>p.id));
      if(req.method==='GET'&&req.url==='/v1/providers')return send(200,{providers:all.filter(p=>allowed.has(p.id))});
      if(req.method!=='POST'||req.url!=='/v1/parse')throw new GatewayError('not_found','Unknown endpoint',404);
      if(!(req.headers['content-type']??'').toLowerCase().startsWith('application/json'))throw new GatewayError('unsupported_media_type','Content-Type must be application/json',415);
      if(active>=(options.maxConcurrent??8))throw new GatewayError('overloaded','Concurrent request limit exceeded',503);active++;occupied=true;
      const request=validateRequest(await body(req,options.maxBodyBytes??29_000_000));
      if(request.providerKeys&&!options.allowRequestKeys)throw new GatewayError('request_keys_disabled','Per-request provider keys disabled',403);
      if([...(request.providers??[]),...Object.keys(request.providerKeys??{}),...Object.keys(request.providerOptions??{})].some(p=>!allowed.has(p)))throw new GatewayError('provider_forbidden','Provider outside gateway key scope',403);
      const cancel=new AbortController();const onClose=()=>{if(!res.writableEnded)cancel.abort();};res.on('close',onClose);
      try{const excludeProviders=[...new Set([...(request.excludeProviders??[]),...all.filter(p=>!allowed.has(p.id)).map(p=>p.id)])];send(200,await options.gateway.parse({...request,...(excludeProviders.length?{excludeProviders}:{})},{signal:cancel.signal}));}
      finally{res.off('close',onClose);}
    }catch(error){const e=error instanceof GatewayError?error:new GatewayError('internal_error','Internal gateway error',500);send(e.status,{error:{code:e.code,message:e.message}});}
    finally{if(occupied)active--;}
  });
  server.requestTimeout=310000;server.headersTimeout=15000;server.timeout=315000;return server;
}
export {createApiKey,listApiKeys,revokeApiKey,keyStoreAuthenticator} from './keys.js';
export type {KeyPolicy} from './keys.js';
