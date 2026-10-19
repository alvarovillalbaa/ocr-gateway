#!/usr/bin/env node
import {readFile,stat} from 'node:fs/promises';
import {createOCRGateway,keysFromEnv} from './core.js';
import {OCRGateway} from './index.js';
import {createGatewayServer,createApiKey,listApiKeys,revokeApiKey,keyStoreAuthenticator} from './server.js';
import {createLocalProvider} from './local.js';
import {createParseTool,parseToolDefinition} from './tools.js';
import {GatewayError,inferMime} from './validation.js';
import type {GatewayOptions,ParseClient,ParseRequest} from './types.js';

const args=process.argv.slice(2);const flag=(name:string)=>{const at=args.indexOf(`--${name}`);if(at<0)return undefined;const value=args[at+1];if(!value||value.startsWith('--'))throw new GatewayError('invalid_flag',`--${name} needs a value`);return value;};
const store=()=>flag('store')??'.ocr-gateway/keys.json';
async function gateway(){
  const configPath=flag('config');const config=configPath?JSON.parse(await readFile(configPath,'utf8')):{};
  if(!config||typeof config!=='object'||Array.isArray(config)||Object.keys(config).some(k=>!['enabledProviders','defaults','router'].includes(k)))throw new GatewayError('invalid_config','Config supports enabledProviders, defaults, router');
  if(config.router&&Object.keys(config.router).some(k=>!['rules','confidenceThreshold'].includes(k)))throw new GatewayError('invalid_config','Router config supports rules and confidenceThreshold');
  if(config.defaults&&(typeof config.defaults!=='object'||Array.isArray(config.defaults)||'document' in config.defaults))throw new GatewayError('invalid_config','Defaults must be request options without document');
  if(config.defaults?.providerKeys)throw new GatewayError('invalid_config','Configure credentials through environment variables');
  const options:GatewayOptions={...config,providerKeys:keysFromEnv(),router:{...config.router,jevApiKey:process.env.TYPESAFE_API_KEY,openaiApiKey:process.env.OPENAI_API_KEY}};
  if(args.includes('--local')||process.env.OCR_GATEWAY_LOCAL==='1')options.providers=[createLocalProvider({python:process.env.OCR_GATEWAY_PYTHON})];
  const providers=flag('providers');if(providers)options.enabledProviders=providers.split(',');return createOCRGateway(options);
}
async function mcp(client:ParseClient){
  const tool=createParseTool(client);
  async function* lines(){
    let pending=Buffer.alloc(0);
    for await(const part of process.stdin){
      const bytes=Buffer.isBuffer(part)?part:Buffer.from(part);let at=0;
      while(at<bytes.length){
        const newline=bytes.indexOf(10,at);const end=newline<0?bytes.length:newline;const piece=bytes.subarray(at,end);
        if(pending.length+piece.length>1_000_000)throw new GatewayError('mcp_message_too_large','MCP message exceeds 1 MB');
        pending=Buffer.concat([pending,piece]);
        if(newline<0)break;
        yield pending.toString('utf8').replace(/\r$/,'');pending=Buffer.alloc(0);at=newline+1;
      }
    }
    if(pending.length)yield pending.toString('utf8');
  }
  // stdio transport: stdout is JSON-RPC only. Process sequentially to bound work.
  for await(const line of lines()){
    if(Buffer.byteLength(line)>1_000_000){process.stderr.write('MCP message exceeds limit\n');continue;}
    let request:any;try{request=JSON.parse(line);}catch{process.stdout.write(`${JSON.stringify({jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}})}\n`);continue;}
    if(!request||typeof request!=='object'||Array.isArray(request)||request.jsonrpc!=='2.0'||typeof request.method!=='string'||(request.id!==undefined&&request.id!==null&&typeof request.id!=='string'&&typeof request.id!=='number')){process.stdout.write(`${JSON.stringify({jsonrpc:'2.0',id:null,error:{code:-32600,message:'Invalid request'}})}\n`);continue;}
    if(request.id===undefined)continue;
    const send=(data:unknown)=>process.stdout.write(`${JSON.stringify({jsonrpc:'2.0',id:request.id,...data as object})}\n`);
    try{
      if(request.method==='initialize')send({result:{protocolVersion:'2024-11-05',capabilities:{tools:{}},serverInfo:{name:'ocr-gateway',version:'0.1.0'}}});
      else if(request.method==='ping')send({result:{}});
      else if(request.method==='tools/list')send({result:{tools:[{name:parseToolDefinition.name,description:parseToolDefinition.description,inputSchema:parseToolDefinition.parameters}]}});
      else if(request.method==='tools/call'){
        if(request.params?.name!==tool.name)throw new GatewayError('unknown_tool','Unknown tool');
        const result=await tool.execute(request.params.arguments);send({result:{content:[{type:'text',text:JSON.stringify(result)}],isError:false}});
      }else send({error:{code:-32601,message:'Method not found'}});
    }catch(e){send({result:{content:[{type:'text',text:e instanceof GatewayError?e.message:'Document parsing failed'}],isError:true}});}
  }
}
async function main(){
  if(args[0]==='key'){
    if(args[1]==='create')console.log(JSON.stringify(await createApiKey(store(),{name:flag('name'),providers:flag('providers')?.split(','),requestsPerMinute:flag('rpm')===undefined?undefined:Number(flag('rpm'))}),null,2));
    else if(args[1]==='list')console.log(JSON.stringify(await listApiKeys(store()),null,2));
    else if(args[1]==='revoke'&&args[2]){await revokeApiKey(store(),args[2]);console.log(JSON.stringify({revoked:args[2]}));}
    else throw new GatewayError('usage','Use key create|list|revoke <id>');return;
  }
  if(args[0]==='serve'){
    const service=await gateway();const server=createGatewayServer({gateway:service,authenticate:keyStoreAuthenticator(store()),allowRequestKeys:args.includes('--allow-request-keys'),allowedOrigins:flag('origins')?.split(',')});
    const port=Number(flag('port')??8787);if(!Number.isInteger(port)||port<1||port>65535)throw new GatewayError('invalid_port','Port must be 1 to 65535');
    server.on('error',e=>{process.stderr.write(`Server failed: ${e.message}\n`);process.exitCode=1;});
    server.listen(port,flag('host')??'127.0.0.1',()=>process.stderr.write(`OCR Gateway listening on ${flag('host')??'127.0.0.1'}:${port}\n`));
    for(const event of ['SIGINT','SIGTERM'] as const)process.on(event,()=>server.close());return;
  }
  if(args[0]==='providers'){console.log(JSON.stringify((await gateway()).providers(),null,2));return;}
  const remote=flag('base-url');const client:ParseClient=remote?new OCRGateway({baseUrl:remote,apiKey:process.env.OCR_GATEWAY_API_KEY}):await gateway();
  if(args[0]==='mcp'){await mcp(client);return;}
  if(args[0]==='parse'){
    const file=flag('file');const url=flag('url');if(!!file===!!url)throw new GatewayError('usage','Provide --file or --url');
    if(file&&(await stat(file)).size>20*1024*1024)throw new GatewayError('file_too_large','File exceeds 20 MiB');
    const document=file?{name:file.split(/[\\/]/).pop(),mimeType:flag('mime-type')??inferMime(file),dataBase64:(await readFile(file)).toString('base64')}:{url,mimeType:flag('mime-type'),name:flag('name')};
    console.log(JSON.stringify(await client.parse({document,mode:(flag('mode')??'auto') as ParseRequest['mode'],...(flag('providers')?{providers:flag('providers')!.split(',')}:{})}),null,2));return;
  }
  console.log('OCR Gateway\n\nkey create|list|revoke <id> [--store path] [--name app] [--providers ids] [--rpm 60]\nserve [--host 127.0.0.1] [--port 8787] [--local] [--config path] [--allow-request-keys]\nparse --file path|--url https://... [--providers ids] [--mode auto|single|parallel|fallback] [--base-url URL]\nproviders [--local]\nmcp [--base-url URL] [--local]\n\nConfigure provider keys in environment variables; see PROVIDERS.md.');
}
main().catch(error=>{process.stderr.write(`${error instanceof GatewayError?`${error.code}: ${error.message}`:'Command failed; check configuration and input'}\n`);process.exitCode=1;});
