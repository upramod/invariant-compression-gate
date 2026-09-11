#!/usr/bin/env python3
"""Optional raw-vs-gated LLM evaluation using the OpenAI Responses API.

Not used for reported manuscript results. Requires OPENAI_API_KEY and the openai package.
The script logs actual API input/output token usage and exact-answer correctness.
"""
from __future__ import annotations
import argparse, csv, json, os
from pathlib import Path

HERE=Path(__file__).resolve().parent

def compact(obj): return json.dumps(obj,separators=(',',':'),sort_keys=True,ensure_ascii=False)

def gate_context(rows, task):
    if task['name']=='lookup': sel=[r for r in rows if r['issue_number']==task['issue_number']]; fields={'issue_number','title','status','actor','date','url'}
    elif task['name']=='count_open': sel=rows; fields={'status'}
    elif task['name']=='threshold_count': sel=[r for r in rows if r['issue_number']>task['min_issue']]; fields={'issue_number'}
    elif task['name']=='latest_actor': sel=[r for r in rows if r['actor']==task['actor']]; fields={'issue_number','actor','title','status'}
    else: raise ValueError(task['name'])
    return [{k:r[k] for k in r if k in fields} for r in sel]

def build_tasks(rows):
    lookup=next(r for r in rows if r['issue_number']==3354)
    rahul=max((r for r in rows if r['actor']=='rahul-ahuja'),key=lambda r:r['issue_number'])
    return [
      {'name':'lookup','issue_number':3354,'question':'For issue 3354, return its title, status, actor, date, and URL.', 'expected':{'title':lookup['title'],'status':lookup['status'],'actor':lookup['actor'],'date':lookup['date'],'url':lookup['url']}},
      {'name':'count_open','question':'How many records have status open?', 'expected':{'count':sum(r['status']=='open' for r in rows)}},
      {'name':'threshold_count','min_issue':3400,'question':'How many records have issue_number greater than 3400?', 'expected':{'count':sum(r['issue_number']>3400 for r in rows)}},
      {'name':'latest_actor','actor':'rahul-ahuja','question':'Return the highest issue_number authored by rahul-ahuja and that issue title and status.', 'expected':{'issue_number':rahul['issue_number'],'title':rahul['title'],'status':rahul['status']}},
    ]

def schema_for(expected):
    props={}
    for k,v in expected.items():
        props[k]={'type':'integer' if isinstance(v,int) else 'string'}
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}

def run_one(client, model, context, task):
    prompt='You are answering from a structured tool result. Use only the supplied JSON.\nQuestion: '+task['question']+'\nTool result:\n'+compact(context)
    response=client.responses.create(
        model=model,
        input=prompt,
        text={'format':{'type':'json_schema','name':'task_answer','strict':True,'schema':schema_for(task['expected'])}},
        store=False,
    )
    got=json.loads(response.output_text)
    usage=getattr(response,'usage',None)
    return got, getattr(usage,'input_tokens',None), getattr(usage,'output_tokens',None)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--snapshot',default=str(HERE/'real_issue_snapshot.json'))
    ap.add_argument('--model',default='gpt-5',help='Override with the exact model available to your API account.')
    ap.add_argument('--repeats',type=int,default=3)
    ap.add_argument('--output',default=str(HERE/'results'/'llm_pair_results.csv'))
    args=ap.parse_args()
    if not os.getenv('OPENAI_API_KEY'):
        raise SystemExit('OPENAI_API_KEY is not set. No API calls were made.')
    try:
        from openai import OpenAI
    except Exception as e:
        raise SystemExit('Install the OpenAI Python package first: pip install openai\nImport error: '+repr(e))
    client=OpenAI()
    payload=json.load(open(args.snapshot,encoding='utf-8')); rows=payload['records']; tasks=build_tasks(rows)
    out=[]
    for task in tasks:
        contexts={'Raw':rows,'Invariant-preserving gate':gate_context(rows,task)}
        for method,ctx in contexts.items():
            for rep in range(args.repeats):
                got,itok,otok=run_one(client,args.model,ctx,task)
                out.append({'task':task['name'],'method':method,'repeat':rep+1,'model':args.model,'correct':int(got==task['expected']),'input_tokens':itok,'output_tokens':otok,'expected':compact(task['expected']),'observed':compact(got)})
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    with open(args.output,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)
    print('wrote',args.output)

if __name__=='__main__': main()
