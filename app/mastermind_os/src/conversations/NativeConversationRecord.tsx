import {useEffect,useRef,useState} from 'react';
import type {FreshNativeInput,FreshNativeResult} from './fresh-conversation-reference';
import type {FreshNativeAnswer} from './fresh-native-content';
import {SourceMarkdown,PREVIEW_CHARACTER_LIMIT} from './SourceMarkdown';

/** Exact original input and answer, withdrawn with their existing READ ticket. */
export function NativeConversationRecord(props:{
  input:FreshNativeInput;result:FreshNativeResult|null;locale?:'en'|'zh-CN';
  current:()=>boolean;readInput:(signal:AbortSignal)=>Promise<string>;
  readResult:(signal:AbortSignal)=>Promise<FreshNativeAnswer>;
}){
  const {input,result}=props,zh=props.locale==='zh-CN';
  const t=(en:string,cn:string)=>zh?cn:en;
  const [full,setFull]=useState<string|null>(null),[answer,setAnswer]=useState<FreshNativeAnswer|null>(null);
  const [state,setState]=useState<'idle'|'input'|'reply'|'input-unavailable'|'reply-unavailable'>('idle');
  const pending=useRef<AbortController|null>(null),live=useRef(props);live.current=props;
  useEffect(()=>{pending.current?.abort();setFull(null);setAnswer(null);setState('idle');
    return()=>pending.current?.abort();},[input,result]);
  async function read(kind:'input'|'reply'){
    if(!live.current.current()||kind==='reply'&&!result)return;
    pending.current?.abort();const controller=new AbortController();pending.current=controller;setState(kind);
    try{
      const value=await (kind==='input'?props.readInput(controller.signal):props.readResult(controller.signal));
      if(controller.signal.aborted||live.current.input!==input||live.current.result!==result||!live.current.current())return;
      if(kind==='input')setFull(value as string);else setAnswer(value as FreshNativeAnswer);
      setState('idle');
    }catch{
      if(!controller.signal.aborted&&live.current.input===input&&live.current.result===result&&live.current.current())
        setState(kind==='input'?'input-unavailable':'reply-unavailable');
    }
  }
  const visible=props.current(),text=visible?(full??input.preview):null,busy=state==='input'||state==='reply';
  return <>
    <h3>{t('Your message','您的消息')}</h3>
    {text!==null?<p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{text}</p>:null}
    {visible&&!input.complete&&full===null?<button type="button" disabled={busy} onClick={()=>void read('input')}>
      {state==='input'?t('Reading full message…','正在读取完整消息…'):t('Read full message','读取完整消息')}
    </button>:null}
    {visible&&state==='input-unavailable'?<p role="status">{t('The full message could not be read. Try again.','暂时无法读取完整消息，请重试。')}</p>:null}
    <h3>{t('Reply','回复')}</h3>
    {visible&&result&&answer===null?<button type="button" disabled={busy} onClick={()=>void read('reply')}>
      {state==='reply'?t('Reading reply…','正在读取回复…'):t('Read reply','读取回复')}
    </button>:null}
    {visible&&state==='reply-unavailable'?<p role="status">{t('The original reply could not be read. Try again.','暂时无法读取原始回复，请重试。')}</p>:null}
    {visible&&answer?.state==='CONTENT'?answer.messages.map((message,index)=>
      message.length<=PREVIEW_CHARACTER_LIMIT?<SourceMarkdown key={index} source={message} locale={props.locale}/>:
        <p key={index} style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{message}</p>):null}
    {visible&&answer?.state==='NO_ANSWER'?<p>{t('This turn ended without an assistant reply.','此轮已结束，未生成助手回复。')}</p>:null}
    {visible&&answer?.state==='CONTENT'&&!answer.messages.some(Boolean)?<p>{t('The recorded response contains no reply text.','已记录的响应中没有回复文本。')}</p>:null}
    {visible&&!result?<p>{t('The original turn still needs reconciliation. Refresh to check its result.','原始轮次仍需核对，请刷新以检查结果。')}</p>:null}
  </>;
}
