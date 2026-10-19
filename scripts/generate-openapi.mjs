import {writeFile} from 'node:fs/promises';
const ref=name=>({$ref:`#/components/schemas/${name}`});
const str={type:'string'},num={type:'number'},bool={type:'boolean'};
const list=items=>({type:'array',items});
const object=(properties,required=[],extra=false)=>({type:'object',properties,required,additionalProperties:extra});
const kinds=['text','heading','table','image','chart','diagram','equation','code','list','unknown'];
const dict={type:'object',additionalProperties:true};
const schemas={
  DocumentInput:{...object({name:{...str,maxLength:255},mimeType:str,url:{...str,format:'uri',pattern:'^https://'},dataBase64:{...str,contentEncoding:'base64'},text:{...str,minLength:1,maxLength:10000000}}),oneOf:[{required:['url'],not:{anyOf:[{required:['dataBase64']},{required:['text']}]}},{required:['dataBase64'],not:{anyOf:[{required:['url']},{required:['text']}]}},{required:['text'],not:{anyOf:[{required:['url']},{required:['dataBase64']}]}}]},
  ChunkOptions:object({maxCharacters:{type:'integer',minimum:100,maximum:100000,default:1600},overlap:{type:'integer',minimum:0,description:'Less than maxCharacters; default min(160,floor(maxCharacters/10))'}}),
  ParseRequest:object({document:ref('DocumentInput'),mode:{...str,enum:['auto','single','parallel','fallback'],default:'auto'},providers:{...list(str),minItems:1,maxItems:100,uniqueItems:true},excludeProviders:{...list(str),maxItems:100},features:list({...str,enum:['tables','images','charts','diagrams','equations']}),maxProviders:{type:'integer',minimum:1,maximum:5,default:2},timeoutMs:{type:'integer',minimum:100,maximum:300000,default:120000},chunking:{oneOf:[ref('ChunkOptions'),{const:false}]},providerKeys:{type:'object',additionalProperties:{...str,minLength:1,maxLength:8192}},providerOptions:{type:'object',additionalProperties:dict},includeRaw:{...bool,default:false}},['document']),
  BoundingBox:object({x:num,y:num,width:{...num,minimum:0},height:{...num,minimum:0},unit:{...str,enum:['pixel','normalized','point']}},['x','y','width','height','unit']),
  Block:object({id:str,kind:{...str,enum:kinds},text:str,start:{type:'integer',minimum:0},end:{type:'integer',minimum:0},citationId:str,bbox:ref('BoundingBox'),confidence:{...num,minimum:0,maximum:1},inferred:bool,imageBase64:{...str,contentEncoding:'base64'},mimeType:str,metadata:dict},['id','kind','text','start','end','citationId']),
  Page:object({pageNumber:{type:'integer',minimum:1},text:str,blocks:list(ref('Block')),width:num,height:num},['text','blocks']),
  Citation:object({id:str,provider:str,pageNumber:{type:'integer',minimum:1},blockId:str,start:{type:'integer',minimum:0},end:{type:'integer',minimum:0},quote:str,bbox:ref('BoundingBox'),inferred:bool},['id','provider','blockId','start','end','quote','inferred']),
  Chunk:object({id:str,text:str,start:{type:'integer',minimum:0},end:{type:'integer',minimum:0},blockIds:list(str),citationIds:list(str),pageNumbers:list({type:'integer',minimum:1})},['id','text','start','end','blockIds','citationIds','pageNumbers']),
  ParsedDocument:object({id:str,provider:str,model:str,text:str,pages:list(ref('Page')),citations:list(ref('Citation')),chunks:list(ref('Chunk')),warnings:list(str),usage:dict,raw:{}},['id','provider','text','pages','citations','chunks','warnings']),
  RoutingDecision:object({router:{...str,enum:['explicit','custom','rule','jev','openai-decisions','heuristic']},providers:list(str),reason:str,confidence:{...num,minimum:0,maximum:1}},['router','providers','reason']),
  ParseResult:object({id:str,document:object({name:str,mimeType:str,url:{...str,format:'uri'}},['mimeType']),primary:ref('ParsedDocument'),results:list(ref('ParsedDocument')),routing:ref('RoutingDecision'),errors:list(object({provider:str,code:str,message:str},['provider','code','message'])),warnings:list(str),durationMs:num},['id','document','primary','results','routing','errors','warnings','durationMs']),
  ProviderInfo:object({id:str,name:str,mimeTypes:list(str),features:list(str),enabled:bool,configured:bool},['id','name','mimeTypes','features','enabled','configured']),
  Error:object({error:object({code:str,message:str},['code','message'])},['error']),
};
const json=schema=>({content:{'application/json':{schema}}});
const errors=Object.fromEntries([400,401,403,404,413,415,429,499,502,503,504].map(status=>[status,{description:'Gateway error',...json(ref('Error'))}]));
const api={openapi:'3.1.0',info:{title:'OCR Gateway',version:'0.1.0',description:'Self-hosted document parsing. Offsets use document-global UTF-16 code units; citations locate extraction output. Provider and key scope always constrain routing.'},servers:[{url:'http://127.0.0.1:8787'}],security:[{bearerAuth:[]}],paths:{
  '/health':{get:{operationId:'health',security:[],responses:{200:{description:'Healthy',...json(object({status:{const:'ok'},version:str},['status','version']))}}}},
  '/v1/providers':{get:{operationId:'providers',responses:{200:{description:'Scoped provider list',...json(object({providers:list(ref('ProviderInfo'))},['providers']))},...errors}}},
  '/v1/parse':{post:{operationId:'parseDocument',requestBody:{required:true,...json(ref('ParseRequest'))},responses:{200:{description:'Parsed document and provenance',...json(ref('ParseResult'))},...errors}}},
},components:{securitySchemes:{bearerAuth:{type:'http',scheme:'bearer'}},schemas}};
await writeFile(new URL('../openapi.json',import.meta.url),`${JSON.stringify(api,null,2)}\n`);
