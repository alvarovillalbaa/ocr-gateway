'use client';
import {useCallback,useEffect,useMemo,useState} from 'react';
import type {ParseClient,ParseRequest,ParseResult} from './types.js';

interface ParseState { data:ParseResult|null;error:Error|null;loading:boolean }
interface ClientLease { generation:number;controller:AbortController|null;active:boolean;state:ParseState }

/** Use an authenticated application proxy; keep reusable gateway/provider keys server-side. */
export function useOCRGateway(client:ParseClient){
  // Pre-effect requests stay on their client; cleanup cannot abort a replacement's work.
  const lease=useMemo<ClientLease>(()=>({generation:0,controller:null,active:false,state:{data:null,error:null,loading:false}}),[client]);
  const [snapshot,setSnapshot]=useState(()=>({lease,state:lease.state}));
  const publish=useCallback(()=>{if(lease.active)setSnapshot({lease,state:lease.state});},[lease]);
  useEffect(()=>{
    lease.active=true;publish();
    return()=>{
      lease.active=false;lease.generation++;
      const previous=lease.controller;lease.controller=null;
      lease.state={...lease.state,loading:false};previous?.abort();
    };
  },[lease,publish]);
  const cancel=useCallback(()=>{
    lease.generation++;
    const previous=lease.controller;lease.controller=null;
    lease.state={...lease.state,loading:false};publish();previous?.abort();
  },[lease,publish]);
  const parse=useCallback(async(request:ParseRequest)=>{
    const previous=lease.controller;const current=++lease.generation;
    const next=new AbortController();lease.controller=next;
    lease.state={...lease.state,loading:true,error:null};publish();previous?.abort();
    if(lease.generation!==current||lease.controller!==next){
      next.abort();throw new DOMException('Parsing cancelled','AbortError');
    }
    try{
      const result=await client.parse(request,{signal:next.signal});
      if(lease.generation===current&&lease.controller===next){lease.state={...lease.state,data:result};publish();}
      return result;
    }
    catch(e){
      const failure=e instanceof Error?e:new Error('Parsing failed');
      if(lease.generation===current&&lease.controller===next){lease.state={...lease.state,error:failure};publish();}
      throw failure;
    }
    finally{
      if(lease.generation===current&&lease.controller===next){lease.controller=null;lease.state={...lease.state,loading:false};publish();}
    }
  },[client,lease,publish]);
  const state=snapshot.lease===lease?snapshot.state:lease.state;
  return {...state,parse,cancel};
}
