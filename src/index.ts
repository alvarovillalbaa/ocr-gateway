import {readJson,withDeadline} from './http.js';
import {GatewayError} from './validation.js';
import type {ParseClient,ParseRequest,ParseResult,DocumentInput} from './types.js';

export interface ClientOptions {baseUrl:string;apiKey?:string;defaults?:Partial<Omit<ParseRequest,'document'>>;fetch?:typeof fetch;timeoutMs?:number}
export class OCRGateway implements ParseClient {
  private baseUrl:string;
  constructor(private options:ClientOptions){
    if(options.timeoutMs!==undefined&&(!Number.isFinite(options.timeoutMs)||options.timeoutMs<=0))throw new GatewayError('invalid_timeout','Client timeoutMs must be finite and positive');
    const url=new URL(options.baseUrl);
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new GatewayError('invalid_base_url','Use an HTTP(S) URL without credentials, query, or fragment');
    if(url.protocol!=='https:'&&!['localhost','127.0.0.1','[::1]'].includes(url.hostname))throw new GatewayError('insecure_base_url','Remote connections require HTTPS');
    this.baseUrl=url.href.replace(/\/$/,'');
  }
  private request<T>(path:string,data?:unknown,signal?:AbortSignal):Promise<T>{
    return withDeadline(this.options.timeoutMs??305000,signal,async deadline=>{
      let response:Response;
      try{response=await(this.options.fetch??fetch)(`${this.baseUrl}${path}`,{method:data?'POST':'GET',headers:{...(this.options.apiKey?{Authorization:`Bearer ${this.options.apiKey}`} :{}),...(data?{'Content-Type':'application/json'}:{})},...(data?{body:JSON.stringify(data)}:{}),signal:deadline,redirect:'error'});}catch{throw new GatewayError('connection_failed','Gateway connection failed',502);}
      const result=await readJson(response);
      if(!response.ok)throw new GatewayError(result?.error?.code??'gateway_error',result?.error?.message??`Gateway returned ${response.status}`,response.status);
      return result as T;
    });
  }
  parse(request:ParseRequest,options?:{signal?:AbortSignal}):Promise<ParseResult>{return this.request('/v1/parse',{...this.options.defaults,...request},options?.signal);}
  providers():Promise<{providers:{id:string;name:string;mimeTypes:string[];features:string[];enabled:boolean;configured:boolean}[]}>{return this.request('/v1/providers');}
}
export async function documentFromFile(file:Blob & {name?:string}):Promise<DocumentInput>{
  if(file.size>20*1024*1024)throw new GatewayError('file_too_large','File exceeds 20 MiB');
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let at=0;at<bytes.length;at+=8192)binary+=String.fromCharCode(...bytes.subarray(at,at+8192));
  return {name:file.name,mimeType:file.type||undefined,dataBase64:btoa(binary)};
}
export {GatewayError};
export {createParseTool,parseToolDefinition} from './tools.js';
export type * from './types.js';
