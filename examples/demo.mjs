// Synthetic in-process example. No provider credentials or network are required.
import {createOCRGateway} from '../dist/core.js';
const gateway=createOCRGateway({providers:[{
  id:'demo',name:'Synthetic document parser',mimeTypes:['text/plain'],features:['tables'],requiresKey:false,supportsUrl:false,
  async parse(document){return {pages:[{pageNumber:1,text:document.text,blocks:[{kind:'text',text:document.text}]}],warnings:['Synthetic demo parser; use a real provider for OCR.']};}
}],enabledProviders:['demo']});
const result=await gateway.parse({document:{name:'demo.txt',text:'Quarterly report\nRevenue: 42 units.\nA synthetic document for a gateway example.'},chunking:{maxCharacters:100,overlap:10}});
console.log(JSON.stringify({provider:result.primary.provider,text:result.primary.text,citations:result.primary.citations,chunks:result.primary.chunks,routing:result.routing},null,2));
