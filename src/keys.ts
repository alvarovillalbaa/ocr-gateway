import {createHash,randomBytes,timingSafeEqual} from 'node:crypto';
import {mkdir,open,readFile,rename,unlink,lstat} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
import {GatewayError} from './validation.js';

export interface KeyPolicy {id:string;name:string;providers?:string[];requestsPerMinute:number}
interface KeyRecord extends KeyPolicy {hash:string;createdAt:string;revokedAt?:string}
interface Store {version:1;keys:KeyRecord[]}
const hash=(value:string)=>createHash('sha256').update(value).digest('hex');
async function safePath(path:string){
  let current=resolve(path);while(true){try{if((await lstat(current)).isSymbolicLink())throw new GatewayError('unsafe_key_store','Key store path cannot contain symlinks',500);}catch(e:any){if(e.code!=='ENOENT')throw e;}const parent=dirname(current);if(parent===current)break;current=parent;}
}
async function readStore(path:string):Promise<Store>{
  await safePath(path);
  try{const value=JSON.parse(await readFile(path,'utf8'));if(value.version!==1||!Array.isArray(value.keys)||value.keys.some((k:any)=>typeof k.id!=='string'||typeof k.hash!=='string'||!/^[a-f0-9]{64}$/.test(k.hash)||!Number.isInteger(k.requestsPerMinute)||k.requestsPerMinute<1||(k.providers!==undefined&&(!Array.isArray(k.providers)||!k.providers.length||k.providers.some((p:unknown)=>typeof p!=='string')))))throw new Error('Invalid store');return value;}
  catch(e:any){if(e.code==='ENOENT')return {version:1,keys:[]};throw new GatewayError('invalid_key_store','Cannot read key store',500);}
}
async function mutate(path:string,update:(store:Store)=>void){
  path=resolve(path);await safePath(path);await mkdir(dirname(path),{recursive:true,mode:0o700});
  let lock;try{lock=await open(`${path}.lock`,'wx',0o600);}catch{throw new GatewayError('key_store_busy','Key store locked by another process; retry after it exits',409);}
  const temp=`${path}.${randomBytes(8).toString('hex')}.tmp`;
  try{const store=await readStore(path);update(store);const file=await open(temp,'wx',0o600);try{await file.writeFile(`${JSON.stringify(store,null,2)}\n`);await file.sync();}finally{await file.close();}await rename(temp,path);}
  finally{await unlink(temp).catch(()=>{});await lock.close();await unlink(`${path}.lock`);}
}
export async function createApiKey(path:string,options:{name?:string;providers?:string[];requestsPerMinute?:number}={}){
  const rpm=options.requestsPerMinute??60;
  if(!Number.isInteger(rpm)||rpm<1||rpm>10000||options.name!==undefined&&(typeof options.name!=='string'||options.name.length>100)||options.providers!==undefined&&(!options.providers.length||options.providers.some(p=>! /^[a-z][a-z0-9_-]{0,63}$/.test(p))))throw new GatewayError('invalid_key_policy','Invalid key name, provider scope or requestsPerMinute');
  const id=randomBytes(8).toString('hex');const apiKey=`ogk_${id}.${randomBytes(32).toString('base64url')}`;
  const record:KeyRecord={id,name:options.name??'default',providers:options.providers,requestsPerMinute:rpm,hash:hash(apiKey),createdAt:new Date().toISOString()};
  await mutate(path,store=>store.keys.push(record));const {hash:_,...metadata}=record;return {apiKey,...metadata};
}
export async function listApiKeys(path:string){return (await readStore(path)).keys.map(({hash:_,...key})=>key);}
export async function revokeApiKey(path:string,id:string){await mutate(path,store=>{const key=store.keys.find(k=>k.id===id);if(!key)throw new GatewayError('key_not_found','Key ID not found',404);key.revokedAt=new Date().toISOString();});}
export function keyStoreAuthenticator(path:string){return async(apiKey:string):Promise<KeyPolicy|undefined>=>{
  if(! /^ogk_[a-f0-9]{16}\.[A-Za-z0-9_-]{43}$/.test(apiKey))return;
  const digest=Buffer.from(hash(apiKey),'hex');for(const key of (await readStore(path)).keys){if(key.revokedAt)continue;const stored=Buffer.from(key.hash,'hex');if(stored.length===digest.length&&timingSafeEqual(stored,digest))return {id:key.id,name:key.name,providers:key.providers,requestsPerMinute:key.requestsPerMinute};}
};}
