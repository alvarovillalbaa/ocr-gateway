import {GatewayError} from './validation.js';

export async function readJson(response:Response,maxBytes=32_000_000):Promise<any>{
  const reader=response.body?.getReader();if(!reader)throw new GatewayError('empty_response','Empty response',502);
  const chunks:Uint8Array[]=[];let size=0;
  try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>maxBytes)throw new GatewayError('response_too_large','Response exceeds limit',502);chunks.push(value);}}finally{await reader.cancel().catch(()=>{});}
  const data=new Uint8Array(size);let at=0;for(const chunk of chunks){data.set(chunk,at);at+=chunk.length;}
  try{return JSON.parse(new TextDecoder().decode(data));}catch{throw new GatewayError('invalid_response','Response must be JSON',502);}
}
/** A referenced timer also bounds custom adapters that ignore AbortSignal. */
export async function withDeadline<T>(ms:number,parent:AbortSignal|undefined,run:(signal:AbortSignal)=>Promise<T>):Promise<T>{
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let listener:()=>void=()=>{};
  const cancelled=new Promise<never>((_,reject)=>{
    listener=()=>{controller.abort();reject(new GatewayError('cancelled','Request cancelled',499));};
    parent?.addEventListener('abort',listener,{once:true});
    timer=setTimeout(()=>{controller.abort();reject(new GatewayError('timeout','Request deadline exceeded',504));},ms);
  });
  try{if(parent?.aborted)throw new GatewayError('cancelled','Request cancelled',499);return await Promise.race([run(controller.signal),cancelled]);}
  finally{clearTimeout(timer);parent?.removeEventListener('abort',listener);}
}
