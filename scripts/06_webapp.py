# -*- coding: utf-8 -*-
"""06 本地网页：能提问、答案带出处、点出处回原文。
用法：python 06_webapp.py  然后浏览器打开 http://127.0.0.1:5000
"""
import importlib.util
import os

from flask import Flask, jsonify, request, render_template_string

HERE = os.path.dirname(os.path.abspath(__file__))


def load_rag():
    spec = importlib.util.spec_from_file_location("rag05", os.path.join(HERE, "05_rag.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rag = load_rag()
app = Flask(__name__)
ENGINE = None

PAGE = r"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>自选股财报问答库</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1c1c1e;--muted:#6b6b70;
      --accent:#1e2761;--accent2:#2f3c7e;--line:#e4e4e2;--hit:#f0f3ff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.65}
header{background:var(--accent);color:#fff;padding:26px 28px}
header h1{margin:0;font-size:20px;font-weight:600;letter-spacing:.3px}
header p{margin:6px 0 0;font-size:13px;opacity:.82}
.wrap{max-width:940px;margin:0 auto;padding:22px 18px 60px}
form{display:flex;gap:10px;margin-bottom:8px}
input[type=text]{flex:1;padding:13px 15px;font-size:15px;border:1px solid var(--line);
     border-radius:10px;background:var(--card);outline:none;font-family:inherit}
input[type=text]:focus{border-color:var(--accent2)}
button{padding:13px 22px;font-size:15px;border:0;border-radius:10px;background:var(--accent2);
     color:#fff;cursor:pointer;font-family:inherit}
button:disabled{opacity:.5;cursor:default}
.opts{font-size:12.5px;color:var(--muted);margin-bottom:20px}
.opts label{margin-right:14px;cursor:pointer}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
      padding:20px 22px;margin-bottom:16px}
.card h2{font-size:14px;margin:0 0 12px;color:var(--muted);font-weight:600;letter-spacing:.5px}
.ans{white-space:pre-wrap;font-size:15px}
.ans b{color:var(--accent)}
.src{border-top:1px solid var(--line);padding:12px 0 0;margin-top:8px}
.src:first-of-type{border-top:0;padding-top:0}
.src summary{cursor:pointer;font-size:13.5px;color:var(--accent2);font-weight:600}
.src .body{font-size:13px;color:#333;background:#fafafa;border:1px solid var(--line);
     border-radius:8px;padding:12px;margin-top:9px;white-space:pre-wrap;
     max-height:340px;overflow:auto;font-family:ui-monospace,Consolas,monospace;line-height:1.5}
.tag{display:inline-block;background:var(--hit);color:var(--accent2);border-radius:5px;
     padding:1px 7px;font-size:12px;margin-right:6px}
.score{color:var(--muted);font-size:12px;font-weight:400}
.hint{color:var(--muted);font-size:12.5px;margin-top:8px}
.qs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}
.qs span{font-size:12.5px;background:var(--card);border:1px solid var(--line);
     border-radius:20px;padding:6px 13px;cursor:pointer;color:var(--accent2)}
.qs span:hover{background:var(--hit)}
#err{color:#b3261e;font-size:13px}
</style></head><body>
<header>
  <h1>自选股财报问答库</h1>
  <p>14 只主板 · 2026 年半年度报告全文 · 本地向量 + BM25 混合检索 · 答案带出处可回原文</p>
</header>
<div class="wrap">
  <form id="f">
    <input type="text" id="q" placeholder="例：锡装股份上半年营业收入和归母净利润是多少？" autocomplete="off">
    <button id="btn" type="submit">提问</button>
  </form>
  <div class="opts">
    <label><input type="radio" name="mode" value="hybrid" checked> 混合检索（向量+BM25）</label>
    <label><input type="radio" name="mode" value="vector"> 只用向量</label>
    <label><input type="checkbox" id="llm" checked> 生成回答（关掉只看召回原文）</label>
  </div>
  <div class="qs" id="qs"></div>
  <div id="err"></div>
  <div class="card" id="ansCard" style="display:none">
    <h2>回答</h2><div class="ans" id="ans"></div>
    <div class="hint" id="ansMeta"></div>
  </div>
  <div class="card" id="srcCard" style="display:none">
    <h2>召回的原文（点开看出处与全文）</h2>
    <div id="srcs"></div>
  </div>
</div>
<script>
const EXAMPLES=["锡装股份上半年营业收入和归母净利润是多少？",
 "华工科技上半年研发投入占营业收入的比例是多少？",
 "万华化学上半年经营活动产生的现金流量净额是多少？",
 "这14家公司里，哪家上半年归母净利润同比增长最快？",
 "英维克上半年营业收入同比增速是多少，主要驱动是什么？"];
const qs=document.getElementById('qs');
EXAMPLES.forEach(t=>{const s=document.createElement('span');s.textContent=t;
  s.onclick=()=>{document.getElementById('q').value=t;document.getElementById('f').requestSubmit();};
  qs.appendChild(s);});
// 支持 ?q=问题&mode=hybrid&llm=0 直接出结果：
// 一是方便把某个问题的答案直接发链接，二是截图/自动化时不用手点。
const P=new URLSearchParams(location.search);
if(P.get('mode')){const r=document.querySelector(`input[name=mode][value="${P.get('mode')}"]`);if(r)r.checked=true;}
if(P.get('llm')==='0'){document.getElementById('llm').checked=false;}
if(P.get('q')){document.getElementById('q').value=P.get('q');}
// 生成模型返回的是 Markdown。原先用 textContent 直接塞，于是「**结论：**」的星号
// 原样显示在页面上——交作业的截图里满屏星号。这里只做够用的三件事：
// **粗体**、行首 - 的列表、段落换行；不做完整 Markdown 解析（够用即可）。
// 先 esc 再替换，顺序不能反：反了会把模型输出里的 < > 当标签执行。
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function mdLite(s){
  const out=[]; let inUl=false;
  for(const raw of esc(s).split('\n')){
    const m=raw.match(/^\s*[-*]\s+(.*)$/);
    if(m){ if(!inUl){out.push('<ul style="margin:.3em 0 .3em 1.2em;padding:0">');inUl=true;}
           out.push('<li>'+m[1]+'</li>'); continue; }
    if(inUl){out.push('</ul>');inUl=false;}
    out.push('<p style="margin:.3em 0">'+raw+'</p>');
  }
  if(inUl) out.push('</ul>');
  return out.join('').replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
}
document.getElementById('f').onsubmit=async e=>{
  e.preventDefault();
  const q=document.getElementById('q').value.trim(); if(!q) return;
  const mode=document.querySelector('input[name=mode]:checked').value;
  const useLLM=document.getElementById('llm').checked;
  const btn=document.getElementById('btn'); btn.disabled=true; btn.textContent='检索中';
  document.getElementById('err').textContent='';
  try{
    const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({q,mode,use_llm:useLLM})});
    const d=await r.json();
    if(d.error){document.getElementById('err').textContent=d.error;return;}
    document.getElementById('ansCard').style.display='block';
    document.getElementById('srcCard').style.display='block';
    const a=document.getElementById('ans');
    a.innerHTML=mdLite(d.answer||'（未生成）');
    document.getElementById('ansMeta').textContent =
      d.model? ('生成模型：'+d.model+' ｜ 召回 '+d.hits.length+' 块 ｜ 检索：'+d.mode)
             : ('召回 '+d.hits.length+' 块 ｜ 检索：'+d.mode);
    const box=document.getElementById('srcs'); box.innerHTML='';
    d.hits.forEach((h,i)=>{
      const det=document.createElement('details'); det.className='src';
      const sum=document.createElement('summary');
      sum.innerHTML=`<span class="tag">[${i+1}]</span>${h.name}(${h.code}) ｜ ${h.section||'—'} ｜ 第 ${h.page}-${h.page_end} 页
        <span class="score">score ${h.score.toFixed(4)}</span>`;
      const body=document.createElement('div'); body.className='body'; body.textContent=h.text;
      det.appendChild(sum); det.appendChild(body); box.appendChild(det);
    });
  }catch(err){document.getElementById('err').textContent='请求失败：'+err;}
  finally{btn.disabled=false; btn.textContent='提问';}
};
if(P.get('q')) document.getElementById('f').requestSubmit();
</script></body></html>"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/ask", methods=["POST"])
def ask():
    global ENGINE
    data = request.get_json(force=True)
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify({"error": "问题为空"})
    if ENGINE is None:
        ENGINE = rag.RagEngine()
    r = ENGINE.answer(q, topk=8, mode=data.get("mode", "hybrid"),
                      use_llm=bool(data.get("use_llm", True)))
    return jsonify({
        "answer": r["answer"], "model": r.get("model"), "mode": data.get("mode", "hybrid"),
        "hits": [{k: h[k] for k in ("id", "code", "name", "section", "page", "page_end",
                                    "score", "text")} for h in r["hits"]],
    })


if __name__ == "__main__":
    print("加载引擎（首次要几十秒）...")
    ENGINE = rag.RagEngine()
    print("就绪 -> http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
