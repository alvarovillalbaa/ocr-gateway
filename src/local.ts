import {spawn} from 'node:child_process';
import type {ProviderAdapter, ProviderOutput} from './types.js';
import {GatewayError} from './validation.js';

const MAX_OUTPUT=16*1024*1024;
const MIME_TYPES=[
  'text/plain','text/markdown','text/x-markdown','text/x-rst','text/html','text/csv','application/csv','text/tab-separated-values',
  'application/json','text/json','application/xml','text/xml','application/pdf',
  'image/png','image/jpeg','image/webp','image/gif','image/tiff','image/bmp',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/vnd.oasis.opendocument.text',
];

/** Opt-in: install the Python package and optional native tools on this host. */
export function createLocalProvider(options:{python?:string}={}):ProviderAdapter {
  return {
    id:'local', name:'Local Python extraction', mimeTypes:MIME_TYPES,
    features:['tables','images'], requiresKey:false, supportsUrl:false,
    async parse(document, context):Promise<ProviderOutput> {
      if(document.url) throw new GatewayError('local_url_unsupported','Local parsing accepts bytes/text and never fetches URLs');
      if(context.signal.aborted) throw new GatewayError('timeout','Local parsing was cancelled',408);
      const input=JSON.stringify(document);
      if(Buffer.byteLength(input)>46*1024*1024) throw new GatewayError('input_too_large','Local input exceeds size limit',413);
      return new Promise<ProviderOutput>((resolve,reject)=>{
        const detached=process.platform!=='win32';
        const child=spawn(options.python??'python3',['-m','ocr_gateway.local'],{stdio:['pipe','pipe','pipe'],detached,windowsHide:true});
        let done=false, size=0, errorSize=0;
        const output:Buffer[]=[], errors:Buffer[]=[];
        const kill=()=>{
          try {if(detached&&child.pid) process.kill(-child.pid,'SIGKILL'); else child.kill('SIGKILL');} catch {/* Already exited. */}
        };
        const finish=(error?:Error, value?:ProviderOutput)=>{
          if(done) return;
          done=true; clearTimeout(timer); context.signal.removeEventListener('abort',abort);
          if(error){kill();reject(error);} else resolve(value!);
        };
        const abort=()=>finish(new GatewayError('timeout','Local parsing was cancelled or exceeded the request deadline',408));
        const timer=setTimeout(abort,300_000);
        context.signal.addEventListener('abort',abort,{once:true});
        if(context.signal.aborted){abort();return;}
        child.on('error',()=>finish(new GatewayError('local_unavailable','Could not start Python local parser; install ocr-gateway-client and configure the Python executable',502)));
        child.stdin.on('error',()=>{/* A failed child is reported by error/close. */});
        child.stdout.on('data',(chunk:Buffer)=>{
          size+=chunk.length;
          if(size>MAX_OUTPUT){finish(new GatewayError('output_too_large','Local output exceeds 16 MiB limit',502));return;}
          output.push(chunk);
        });
        child.stderr.on('data',(chunk:Buffer)=>{
          errorSize+=chunk.length;
          if(errorSize<=16_384) errors.push(chunk);
        });
        child.on('close',code=>{
          if(done) return;
          if(code!==0){
            let message='Local extraction failed; verify format support and optional Python/native dependencies';
            try {
              const detail=JSON.parse(Buffer.concat(errors).toString('utf8')) as {error?:{message?:unknown}};
              if(typeof detail.error?.message==='string') message=detail.error.message.slice(0,500);
            } catch {/* Do not expose arbitrary child stderr. */}
            finish(new GatewayError('local_parse_error',message,502));return;
          }
          try {
            const value=JSON.parse(Buffer.concat(output).toString('utf8')) as ProviderOutput;
            if(!value||!Array.isArray(value.pages)||value.pages.length>500||value.pages.some(page=>!page||typeof page.text!=='string'||(page.pageNumber!==undefined&&(!Number.isInteger(page.pageNumber)||page.pageNumber<1)))) throw new Error('invalid');
            finish(undefined,value);
          } catch {finish(new GatewayError('invalid_provider_response','Local parser returned an invalid document',502));}
        });
        child.stdin.end(input);
      });
    },
  };
}
