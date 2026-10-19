'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import type {ParseClient,ParseRequest,ParseResult} from './types.js';

/** Use an authenticated application proxy; keep reusable gateway/provider keys server-side. */
export function useOCRGateway(client:ParseClient){
  const [data,setData]=useState<ParseResult|null>(null);const [error,setError]=useState<Error|null>(null);const [loading,setLoading]=useState(false);
  const generation=useRef(0);const controller=useRef<AbortController|null>(null);
  useEffect(()=>()=>{generation.current++;controller.current?.abort();},[client]);
  const cancel=useCallback(()=>{generation.current++;controller.current?.abort();setLoading(false);},[]);
  const parse=useCallback(async(request:ParseRequest)=>{
    controller.current?.abort();const current=++generation.current;const next=new AbortController();controller.current=next;setLoading(true);setError(null);
    try{const result=await client.parse(request,{signal:next.signal});if(generation.current===current)setData(result);return result;}
    catch(e){const failure=e instanceof Error?e:new Error('Parsing failed');if(generation.current===current)setError(failure);throw failure;}
    finally{if(generation.current===current)setLoading(false);}
  },[client]);
  return {data,error,loading,parse,cancel};
}
