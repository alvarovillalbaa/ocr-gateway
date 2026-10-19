import type {ParseRequest} from './types.js';

export class GatewayError extends Error {
  constructor(public code:string, message:string, public status=400) { super(message); this.name='GatewayError'; }
}
const object=(v:unknown):v is Record<string,unknown>=>!!v && typeof v==='object' && !Array.isArray(v);
const fail=(message:string):never=>{throw new GatewayError('invalid_request',message);};
const extensions:Record<string,string>={pdf:'application/pdf',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',gif:'image/gif',tif:'image/tiff',tiff:'image/tiff',txt:'text/plain',md:'text/markdown',html:'text/html',htm:'text/html',csv:'text/csv',json:'application/json',xml:'application/xml',docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',pptx:'application/vnd.openxmlformats-officedocument.presentationml.presentation',xlsx:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',odt:'application/vnd.oasis.opendocument.text',rtf:'application/rtf',doc:'application/msword',ppt:'application/vnd.ms-powerpoint',xls:'application/vnd.ms-excel',epub:'application/epub+zip'};
export function inferMime(name?:string) {return extensions[name?.split(/[?#]/)[0]?.split('.').pop()?.toLowerCase()??''];}
export function validateRequest(raw:unknown):ParseRequest {
  if(!object(raw)||!object(raw.document)) return fail('document is required');
  const allowed=['document','mode','providers','excludeProviders','maxProviders','timeoutMs','features','chunking','providerKeys','providerOptions','includeRaw'];
  if(Object.keys(raw).some(k=>!allowed.includes(k))) fail('Unknown request field');
  const d=raw.document;
  if(Object.keys(d).some(k=>!['name','mimeType','url','text','dataBase64'].includes(k))) fail('Unknown document field');
  for(const key of Object.keys(d)) if(d[key]!==undefined&&typeof d[key]!=='string') fail(`document.${key} must be a string`);
  if(['url','text','dataBase64'].filter(k=>d[k]!==undefined).length!==1) fail('Supply exactly one of url, text, dataBase64');
  if(d.name!==undefined && (d.name as string).length>255) fail('name must have at most 255 characters');
  if(d.url!==undefined){
    let url:URL; try{url=new URL(d.url as string);}catch{return fail('Invalid document URL');}
    if(url.protocol!=='https:'||url.username||url.password||(d.url as string).length>8192) fail('Document URLs require HTTPS without credentials');
  }
  if(d.text!==undefined&&(!(d.text as string).trim()||(d.text as string).length>10_000_000)) fail('text must contain 1 to 10000000 characters');
  if(d.dataBase64!==undefined){const b=d.dataBase64 as string;const padding=b.endsWith('==')?2:b.endsWith('=')?1:0;if(!b.length||b.length%4!==0||b.length/4*3-padding>20*1024*1024||! /^[A-Za-z0-9+/]*={0,2}$/.test(b)) fail('dataBase64 must be valid base64, at most 20 MiB decoded');}
  const mime=(d.mimeType as string|undefined)??inferMime((d.name??d.url) as string|undefined)??(d.text!==undefined?'text/plain':undefined);
  if(!mime||mime.length>200||! /^[a-z0-9.+-]+\/[a-z0-9.+-]+$/i.test(mime)) fail('Specify a valid mimeType or recognized filename');
  if(raw.mode!==undefined&&!['auto','single','parallel','fallback'].includes(raw.mode as string)) fail('Invalid mode');
  for(const key of ['providers','excludeProviders']) if(raw[key]!==undefined && (!Array.isArray(raw[key])||(key==='providers'&&!(raw[key] as unknown[]).length)||(raw[key] as unknown[]).length>100||(raw[key] as unknown[]).some(v=>typeof v!=='string'||! /^[a-z][a-z0-9_-]{0,63}$/.test(v)))) fail(`${key} must be an array of provider IDs`);
  for(const [key,min,max] of [['maxProviders',1,5],['timeoutMs',100,300000]] as const) if(raw[key]!==undefined && (!Number.isInteger(raw[key])||(raw[key] as number)<min||(raw[key] as number)>max)) fail(`${key} must be ${min} to ${max}`);
  if(raw.features!==undefined&&(!Array.isArray(raw.features)||raw.features.some(v=>!['tables','images','charts','diagrams','equations'].includes(v)))) fail('Invalid features');
  if(raw.chunking!==undefined&&raw.chunking!==false){
    if(!object(raw.chunking)||Object.keys(raw.chunking).some(k=>!['maxCharacters','overlap'].includes(k))) fail('Invalid chunking');
    const c=raw.chunking as Record<string,unknown>; const max=c.maxCharacters??1600,overlap=c.overlap??Math.min(160,Math.floor((max as number)/10));
    if(!Number.isInteger(max)||(max as number)<100||(max as number)>100000||!Number.isInteger(overlap)||(overlap as number)<0||(overlap as number)>=(max as number)) fail('Chunk size must be 100 to 100000 and overlap less than size');
  }
  for(const key of ['providerKeys','providerOptions']) if(raw[key]!==undefined&&!object(raw[key])) fail(`${key} must be an object`);
  if(raw.providerKeys&&Object.entries(raw.providerKeys as object).some(([k,v])=>! /^[a-z][a-z0-9_-]{0,63}$/.test(k)||typeof v!=='string'||!v||v.length>8192)) fail('Invalid providerKeys');
  if(raw.providerOptions&&Object.entries(raw.providerOptions as object).some(([k,v])=>! /^[a-z][a-z0-9_-]{0,63}$/.test(k)||!object(v))) fail('Invalid providerOptions');
  if(raw.includeRaw!==undefined&&typeof raw.includeRaw!=='boolean') fail('includeRaw must be boolean');
  return {...raw,document:{...Object.fromEntries(Object.entries(d).filter(([,v])=>v!==undefined)),mimeType:mime!.toLowerCase()}} as unknown as ParseRequest;
}
