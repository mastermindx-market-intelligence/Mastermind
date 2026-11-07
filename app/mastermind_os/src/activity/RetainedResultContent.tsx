import './retained-result-content.css';
export function RetainedResultContent({locale,summary,roleResult,nextActions}: {
  locale:'en'|'zh-CN';summary:string;roleResult:unknown;nextActions:readonly string[];
}) {
  const zh=locale==='zh-CN';
  return <article className="mm-result-reading" lang={locale}>
    <h3>{zh?'摘要':'Summary'}</h3>
    <p className="mm-result-reading__summary">{summary}</p>
    {nextActions.length>0?<><h3>{zh?'建议的下一步':'Suggested next actions'}</h3><ul>{nextActions.map((text,index)=><li key={index}>{text}</li>)}</ul></>:null}
    <details className="reason-details"><summary>{zh?'结构化结果':'Structured result'}</summary><pre>{JSON.stringify(roleResult,null,2)}</pre></details>
  </article>;
}
