import type {DispatchState,ReadState} from './mission';
type Locale='en'|'zh-CN';
const DISPATCH:Record<DispatchState,readonly[string,string]>={
 WAITING_CAPACITY:['Waiting for capacity','等待容量'],RECEIVER_SELECTED:['Receiver selected','已选定接收方'],
 DELIVERY_SENT:['Delivery sent','已发送交付'],PICKUP_ACKNOWLEDGED:['Pickup acknowledged','已确认接收'],
 STARTED:['Start recorded','已记录启动'],RETURNED:['Return recorded','已记录返回'],
 CONTINUED:['Continuation recorded','已记录继续请求'],STOPPED:['Stop recorded','已记录停止'],
 DELIVERY_UNCONSUMED:['Delivery not yet consumed','交付尚未接收处理'],WATCH_UNPROVEN:['Monitoring not confirmed','监测尚未确认'],
 RUNTIME_BINDING_RECONCILIATION_REQUIRED:['Work connection needs checking','工作关联需要核查'],
 EFFECT_UNKNOWN:['Outcome unknown','结果未知'],UNKNOWN:['Dispatch not confirmed','派发尚未确认'],
};
export function workStatusPresentation(input:{dispatch:DispatchState;review:'approve'|'reject'|'NOT_YET';acceptance:'NOT_PROJECTED'|'ACCEPTED';read:ReadState},locale:Locale) {
 const index=locale==='zh-CN'?1:0;
 const reviews={approve:['Review approved','审阅通过'],reject:['Changes requested','需要修改'],NOT_YET:['Review not yet reported','尚未报告审阅结果']} as const;
 const acceptance={ACCEPTED:['Accepted','已验收'],NOT_PROJECTED:['Acceptance not supplied','未提供验收信息']} as const;
 const caveats:Record<ReadState,readonly[string,string]|null>={CURRENT:null,
  PARTIAL:['Some source information is missing or may be out of date.','部分来源信息缺失或可能已过期。'],
  HISTORICAL:['This is historical source information; it does not confirm current status.','这是历史来源信息，不能据此确认当前状态。'],
  UNAVAILABLE:['Source information is unavailable; current status cannot be confirmed.','来源信息不可用，无法确认当前状态。']};
 return {dispatch:DISPATCH[input.dispatch][index],review:reviews[input.review][index],acceptance:acceptance[input.acceptance][index],readCaveat:caveats[input.read]?.[index]??null};
}
