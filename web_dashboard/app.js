/* ==========================================================================
   Lionel Dashboard — App Logic (v2)
   Vanilla JS SPA shell. All live data fetched from the FastAPI backend on
   localhost:8080. Single bootstrap, no framework, no build step.

   Endpoints:
     GET  /api/health            -> { agent, version, roles, skills_indexed, router_models }
     POST /api/login  {email,password}  -> { ok, user_name, user_email } | { ok:false, error }
     GET  /api/sessions          -> [{ id, model, turns, prompt_tokens, completion_tokens,
                                       total_tokens, status, created_at, ... }]
     GET  /api/providers         -> [{ name, status, latency_ms, model, success_rate, ... }]
     GET  /api/tokens/summary    -> { total, prompt, completion, hourly:[{hour,label,value}],
                                       by_provider:[{name,label,value}], requests_today, errors_today }
     GET  /api/skills/summary    -> { count, skills:[...] }
     GET  /api/audit/activities  -> [{ time, event, tool, detail, result, ... }]
   ========================================================================== */

(function () {
  'use strict';

  var API = window.__apiBase || '';
  var LOGIN_EMAIL = '+254712633234@lionel.local';
  var LOGIN_PASS  = 'owner';

  var state = {
    loggedIn: false,
    user: null,
    health: null,
    sessions: [],
    providers: [],
    tokensSummary: null,
    skillsSummary: null,
    auditLog: [],
  };

  var $ = function (id) { return document.getElementById(id); };
  var bySel = function (sel) { return document.querySelector(sel); };
  var bySelAll = function (sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); };

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function fmtNum(n) {
    if (n == null || isNaN(n)) return '—';
    if (Math.abs(n) >= 1e6) return (n/1e6).toFixed(1)+'M';
    if (Math.abs(n) >= 1e3) return (n/1e3).toFixed(1)+'k';
    return String(n);
  }
  function fmtTokens(n) { if (n==null||isNaN(n)) return '—'; return fmtNum(n); }
  function timeAgo(iso) {
    if (!iso) return '';
    var then=new Date(iso), now=new Date(), diff=Math.floor((now-then)/1000);
    if (diff<60) return Math.max(diff,0)+'s ago';
    if (diff<3600) return Math.floor(diff/60)+'m ago';
    if (diff<86400) return Math.floor(diff/3600)+'h ago';
    return Math.floor(diff/86400)+'d ago';
  }

  var STATUS_LABELS={active:'Active',idle:'Idle',error:'Error',completed:'Completed',running:'Running',pending:'Pending',disconnected:'Disconnected',ok:'OK',degraded:'Degraded',disabled:'Disabled',offline:'Offline'};
  var STATUS_CLASS={active:'ok',idle:'idle',error:'danger',completed:'ok',running:'warning',pending:'warning',disconnected:'danger',ok:'ok',degraded:'warning',disabled:'idle',offline:'danger'};

  function statusHtml(status) {
    if (!status) status='unknown';
    var label=STATUS_LABELS[status]||status, cls=STATUS_CLASS[status]||'idle';
    var dot=status==='active'||status==='running'?'dot--ok':status==='error'||status==='disconnected'?'dot--danger':status==='idle'||status==='disabled'?'dot--idle':'dot--warning';
    return '<span class="status"><span class="dot '+dot+'"></span><span class="'+cls+'">'+esc(label)+'</span></span>';
  }

  function api(path, options) {
    var url=API+path, cfg=Object.assign({method:'GET',headers:{'Accept':'application/json'}},options||{});
    if (cfg.body&&typeof cfg.body==='object'){cfg.body=JSON.stringify(cfg.body);cfg.headers['Content-Type']='application/json';}
    return fetch(url,cfg).then(function(res){
      if (res.status===401||res.status===403) throw new Error('unauthorized');
      if (!res.ok) throw new Error('HTTP '+res.status);
      var ct=res.headers.get('content-type')||'';
      if (ct.indexOf('application/json')===-1) return res.text().then(function(t){return{raw:t};});
      return res.json();
    });
  }

  function flash(msg,type,persist){
    var slot=$('banner-slot'); if(!slot) return;
    var el=document.createElement('div'); el.className='banner banner--'+(type||'info'); el.textContent=msg||'';
    slot.appendChild(el);
    if(!persist) setTimeout(function(){if(el.parentNode) el.parentNode.removeChild(el);},6000);
  }
  function clearBanner(){var s=$('banner-slot');if(s) s.innerHTML='';}

  function chartArea(values,opts){
    opts=opts||{}; var w=opts.width||360,h=opts.height||140,padL=opts.padL||5,padR=opts.padR||5,padT=opts.padT||10,padB=opts.padB||22;
    var plotW=w-padL-padR,plotH=h-padT-padB,max=1;
    for(var i=0;i<values.length;i++){var v=values[i].value||0;if(v>max)max=v;}
    if(max===0)max=1;
    var pathA='',pathL='',pts='';
    for(i=0;i<values.length;i++){
      var pct=(values[i].value||0)/max, x=padL+i*(plotW/(values.length-1||1)), y=padT+(1-pct)*plotH;
      pathA+=(i===0?'M':'L')+x+','+y; pathL+=(i===0?'M':'L')+x+','+y;
      pts+='<circle class="chart-point" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="2.5"/>';
    }
    pathA+='L'+(padL+(values.length-1)*(plotW/(values.length-1||1))).toFixed(1)+','+(padT+plotH)+' L'+padL+','+(padT+plotH)+' Z';
    var grid='';
    for(var t=0;t<=4;t++){var gy=padT+(t/4)*plotH;grid+='<line class="chart-grid-line" x1="'+padL+'" y1="'+gy.toFixed(1)+'" x2="'+(w-padR)+'" y2="'+gy.toFixed(1)+'"/>';grid+='<text class="chart-label" x="'+(padL-4)+'" y="'+(gy+3).toFixed(1)+'" text-anchor="end">'+fmtNum(Math.round(max*(1-t/4)))+'</text>';}
    return '<svg class="chart-svg" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none">'+grid+'<path class="chart-area" d="'+pathA+'"/><path class="chart-line" d="'+pathL+'"/>'+pts+'</svg>';
  }

  function chartBars(values,opts){
    opts=opts||{}; var w=opts.width||360,h=opts.height||140,padL=opts.padL||5,padR=opts.padR||5,padT=opts.padT||10,padB=opts.padB||22;
    var plotW=w-padL-padR,plotH=h-padT-padB,max=1;
    for(var i=0;i<values.length;i++){var v=values[i].y!=null?values[i].y:values[i].value||0;if(v>max)max=v;}
    if(max===0)max=1;
    var groupW=plotW/values.length,barW=Math.max(4,groupW-4),bars='';
    for(i=0;i<values.length;i++){
      var v=values[i].y!=null?values[i].y:values[i].value||0, h2=(v/max)*plotH, x=padL+i*groupW+(groupW-barW)/2, y=padT+plotH-h2;
      var cls=v===max&&opts.peak?' chart-bar--peak':'';
      bars+='<rect class="chart-bar'+cls+'" x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+barW.toFixed(1)+'" height="'+h2.toFixed(1)+'" rx="2"/>';
      bars+='<text class="chart-label" x="'+(x+barW/2).toFixed(1)+'" y="'+(h-6).toFixed(1)+'" text-anchor="middle" transform="rotate(-25 '+(x+barW/2).toFixed(1)+' '+(h-6).toFixed(1)+')">'+esc(values[i].x||'')+'</text>';
    }
    var grid='';
    for(var t=0;t<=3;t++){var gy=padT+(t/3)*plotH;grid+='<line class="chart-grid-line" x1="'+padL+'" y1="'+gy.toFixed(1)+'" x2="'+(w-padR)+'" y2="'+gy.toFixed(1)+'"/>';grid+='<text class="chart-label" x="'+(padL-4)+'" y="'+(gy+3).toFixed(1)+'" text-anchor="end">'+fmtNum(Math.round(max*(1-t/3)))+'</text>';}
    return '<svg class="chart-svg" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none">'+grid+bars+'</svg>';
  }

  function renderOverview(){
    var summary=state.tokensSummary;
    var total=summary&&summary.total!=null?summary.total:0;
    var sessions=state.sessions||[];
    var active=sessions.filter(function(s){return s.status==='active'||s.status==='running';}).length;
    var requests=(summary&&summary.requests_today!=null)?summary.requests_today:(summary&&summary.requests!=null)?summary.requests:0;
    var errors=(summary&&summary.errors_today!=null)?summary.errors_today:(summary&&summary.errors!=null)?summary.errors:0;
    var errorRate=(requests&&requests>0)?(errors/requests*100):0;

    var el=$('stat-sessions'); if(el) el.textContent=active;
    el=$('stat-sessions-note'); if(el) el.textContent='of 20 concurrent slots';
    el=$('stat-requests'); if(el) el.textContent=fmtNum(requests);
    el=$('stat-requests-note'); if(el) el.textContent='today';
    el=$('stat-tokens'); if(el) el.textContent=fmtTokens(total)+' / '+fmtTokens(Math.max(total*4,1));
    el=$('stat-tokens-note'); if(el) el.textContent=fmtNum(Math.round((total/Math.max(total*4,1))*100))+'% of monthly budget';
    el=$('stat-errors'); if(el){el.textContent=errorRate<1?errorRate.toFixed(1)+'%':(errorRate<5?errorRate.toFixed(1)+'%':'>5%');el.className='stat-value'+(errorRate<1?' ok':errorRate<5?' warn':' danger');}
    el=$('stat-errors-note'); if(el) el.textContent='last 24 hours';

    var banner=$('live-banner');
    if(banner){
      if(state.health){banner.textContent='Live — '+state.health.skills_indexed+' skills indexed · backend connected';banner.className='banner banner--success';}
      else{banner.textContent='Backend unreachable — showing cached data';banner.className='banner banner--warn';}
    }
    var sc=$('sessions-count'); if(sc) sc.textContent=(state.sessions||[]).length+' sessions';
    var pc=$('providers-count'); if(pc) pc.textContent=(state.providers||[]).length+' providers';
    var tn=$('token-chart-note'); if(tn) tn.textContent='last 24 hours';
    var rn=$('requests-chart-note'); if(rn) rn.textContent='09:00 – 20:00';
  }

  function renderSessionsOverview(){
    var body=$('sessions-body'), empty=$('sessions-empty'), filter=$('content-search');
    var query=(filter?filter.value.trim().toLowerCase():'')||'';
    if(!body) return;
    var data=state.sessions||[];
    if(!data.length){body.innerHTML='';if(empty)empty.hidden=false;return;}
    if(empty) empty.hidden=true;
    var html='', slice=data;
    if(query) slice=data.filter(function(s){return (s.id&&s.id.toLowerCase().indexOf(query)!==-1)||(s.model&&s.model.toLowerCase().indexOf(query)!==-1)||(STATUS_LABELS[s.status]&&STATUS_LABELS[s.status].toLowerCase().indexOf(query)!==-1);});
    for(var j=0;j<slice.length;j++){
      var s=slice[j];
      html+='<tr><td class="id">'+esc(s.id?s.id.substring(0,10):'—')+'</td><td class="model">'+esc(s.model||'—')+'</td><td class="num">'+(s.turns!=null?s.turns:'—')+'</td><td class="num">'+esc(fmtTokens(s.total_tokens!=null?s.total_tokens:0))+'</td><td>'+statusHtml(s.status)+'</td></tr>';
    }
    body.innerHTML=html;
  }

  function renderSessionsFull(){
    var body=$('sessions-full-body'), count=$('sessions-full-count'), empty=$('sessions-full-empty');
    if(!body) return;
    var data=(state.sessions||[]).slice().sort(function(a,b){
      var da=a.created_at?new Date(a.created_at):new Date(0), db=b.created_at?new Date(b.created_at):new Date(0);
      return db-da;
    });
    if(!data.length){if(empty)empty.hidden=false;if(count)count.textContent='0 sessions';return;}
    if(empty) empty.hidden=true;
    if(count) count.textContent=data.length+' sessions';
    var html='';
    for(var j=0;j<data.length;j++){
      var s=data[j], created=s.created_at?timeAgo(s.created_at):'';
      html+='<tr><td class="id">'+esc(s.id?s.id.substring(0,12):'—')+'</td><td class="model">'+esc(s.model||'—')+'</td><td class="num">'+esc(created)+'</td><td class="num">'+(s.turns!=null?s.turns:'—')+'</td><td class="num">'+esc(fmtTokens(s.prompt_tokens!=null?s.prompt_tokens:0))+'</td><td class="num">'+esc(fmtTokens(s.completion_tokens!=null?s.completion_tokens:0))+'</td><td class="num">'+esc(fmtTokens(s.total_tokens!=null?s.total_tokens:0))+'</td><td>'+statusHtml(s.status)+'</td></tr>';
    }
    body.innerHTML=html;
  }

  function renderProviders(){
    var list=$('providers-list'), count=$('providers-count'), empty=$('providers-empty'), filter=$('content-search');
    var query=(filter?filter.value.trim().toLowerCase():'')||'';
    if(!list) return;
    var data=state.providers||[];
    if(!data.length){if(list)list.innerHTML='';if(empty)empty.hidden=false;if(count)count.textContent='0 providers';return;}
    if(empty) empty.hidden=true;
    if(count) count.textContent=data.length+' providers';
    var html='';
    for(var j=0;j<data.length;j++){
      var p=data[j];
      if(query&&p.name&&p.name.toLowerCase().indexOf(query)===-1) continue;
      var lat=p.latency_ms!=null?p.latency_ms:p.avg_latency!=null?p.avg_latency:null;
      var latTxt=lat!=null?lat+'ms':'—';
      var dotCls=(p.status==='connected')?'dot--ok':(p.status==='degraded')?'dot--warning':(p.status==='disconnected')?'dot--danger':'dot--idle';
      html+='<li><span class="provider-name"><span class="dot '+dotCls+'"></span>'+esc(p.name||p.provider||'—')+'</span><span class="provider-latency">'+esc(latTxt)+'</span></li>';
    }
    list.innerHTML=html;
  }

  function renderTokenChartFromSummary(){
    var summary=state.tokensSummary, hourly=summary&&summary.hourly?summary.hourly:null;
    var note=$('token-chart-note'), container=$('token-chart');
    if(!container) return;
    if(!hourly||!hourly.length){container.innerHTML='<div class="empty"><svg class="empty-icon"><use href="#i-chart-line"></use></svg>No token usage data yet.</div>';if(note)note.textContent='no data';return;}
    if(note) note.textContent='last 24 hours';
    var data=hourly.map(function(h){return{value:h.value!=null?h.value:h.tokens||0};});
    container.innerHTML=chartArea(data,{width:360,height:140});
  }

  function renderRequestsChart(){
    var summary=state.tokensSummary, hourly=summary&&summary.hourly?summary.hourly:null;
    var note=$('requests-chart-note'), container=$('requests-chart');
    if(!container) return;
    if(!hourly||!hourly.length){container.innerHTML='<div class="empty"><svg class="empty-icon"><use href="#i-chart-line"></use></svg>No request data yet.</div>';if(note)note.textContent='no data';return;}
    if(note) note.textContent=hourly.length+' hours';
    var data=hourly.map(function(h,i){return{x:(i+9)+':00',y:h.requests!=null?h.requests:0};});
    container.innerHTML=chartBars(data,{width:360,height:140,peak:true});
  }

  function renderTokensHourly(){
    var summary=state.tokensSummary, hourly=summary&&summary.hourly?summary.hourly:null;
    var note=$('tokens-chart-note'), container=$('tokens-hourly-chart');
    if(!container) return;
    if(!hourly||!hourly.length){container.innerHTML='<div class="empty"><svg class="empty-icon"><use href="#i-chart-line"></use></svg>No hourly data yet.</div>';if(note)note.textContent='no data';return;}
    if(note) note.textContent='last 24 hours';
    var data=hourly.map(function(h,i){return{x:(i+9)+':00',y:h.value!=null?h.value:h.tokens||0};});
    container.innerHTML=chartBars(data,{width:360,height:140});
  }

  function renderTokensProvider(){
    var summary=state.tokensSummary, byProvider=summary&&summary.by_provider?summary.by_provider:null;
    var note=$('tokens-provider-note'), container=$('tokens-provider-chart');
    if(!container) return;
    if(!byProvider||!byProvider.length){container.innerHTML='<div class="empty"><svg class="empty-icon"><use href="#i-server"></use></svg>No provider data yet.</div>';if(note)note.textContent='no data';return;}
    if(note) note.textContent=byProvider.length+' providers';
    var data=byProvider.map(function(p){return{x:p.name||p.label||'—',y:p.value!=null?p.value:p.tokens||0};});
    container.innerHTML=chartBars(data,{width:360,height:140});
  }

  function renderSkills(){
    var list=$('skills-list'), empty=$('skills-empty'), count=$('skills-count');
    if(!list) return;
    var summary=state.skillsSummary, skills=summary&&summary.skills?summary.skills:null;
    if(!skills||!skills.length){if(list)list.innerHTML='<div class="empty"><svg class="empty-icon"><use href="#i-sparkle"></use></svg>No skills loaded yet.</div>';if(empty)empty.hidden=false;if(count)count.textContent='0 skills';return;}
    if(empty) empty.hidden=true;
    if(count) count.textContent=skills.length+' skills loaded';
    var html='';
    for(var j=0;j<skills.length;j++){
      var sk=skills[j], cat=sk.category||sk.type||'tool', tags=sk.tags||[];
      var tagHtml=tags.length?tags.map(function(t){return'<span class="badge">'+esc(t)+'</span>';}).join(''):'';
      html+='<li><span class="skill-info"><span class="skill-icon">'+esc((sk.name||'?').charAt(0).toUpperCase())+'</span><span class="skill-name">'+esc(sk.name||'unnamed')+'</span><span class="skill-meta"><span class="badge">'+esc(cat)+'</span>'+tagHtml+'</span></span></li>';
    }
    list.innerHTML=html;
  }

  function renderAuditLog(){
    var body=$('logs-body'), count=$('logs-count'), empty=$('logs-empty');
    if(!body) return;
    var data=state.auditLog||[];
    if(!data.length){if(body)body.innerHTML='<div class="empty"><svg class="empty-icon"><use href="#i-logs"></use></svg>No audit entries yet.</div>';if(empty)empty.hidden=false;if(count)count.textContent='0 entries';return;}
    if(empty) empty.hidden=true;
    if(count) count.textContent=data.length+' entries';
    var html='';
    for(var j=0;j<data.length;j++){
      var r=data[j], resCls=r.result==='ok'?'ok':r.result==='error'?'error':r.result==='warning'?'warning':'ok';
      var resultTxt=r.result!=null?r.result.toUpperCase():'OK', time=r.time?timeAgo(r.time):'', detail=r.detail||'';
      html+='<tr><td class="audit-time">'+esc(time)+'</td><td class="audit-event">'+esc(r.event||'—')+'</td><td class="audit-tool">'+esc(r.tool||'—')+'</td><td class="audit-detail" title="'+esc(detail)+'">'+esc(detail||'—')+'</td><td class="audit-result '+resCls+'">'+esc(resultTxt)+'</td></tr>';
    }
    body.innerHTML=html;
  }

  function renderBudget(){
    var grid=$('budget-grid'); if(!grid) return;
    var summary=state.tokensSummary;
    var total=summary&&summary.total!=null?summary.total:0;
    var monthly=summary&&summary.monthly_limit!=null?summary.monthly_limit:total*4;
    var daily=summary&&summary.daily_limit!=null?summary.daily_limit:total*4;
    var hourly=summary&&summary.hourly_limit!=null?summary.hourly_limit:total*4;
    var spendDay=total;
    var spendHr=(summary&&summary.hourly&&summary.hourly.length)?(summary.hourly[summary.hourly.length-1].value||0):total*0.3;
    var lines=[
      {label:'Monthly Budget',value:fmtTokens(monthly),used:total,max:Math.max(monthly,1),sub:'of '+fmtTokens(monthly)+' monthly'},
      {label:'Daily Spend',value:fmtTokens(spendDay),used:spendDay,max:Math.max(daily,1),sub:'tokens used today'},
      {label:'Hourly Rate',value:fmtTokens(spendHr),used:spendHr,max:Math.max(hourly,1),sub:'tokens this hour'},
    ];
    var pct=function(used,max){return Math.min(100,(used/max)*100);};
    var cls=function(used,max){var p=(used/max);return p>0.8?'danger':p>0.5?'warn':'';};
    var html='';
    for(var j=0;j<lines.length;j++){
      var b=lines[j];
      html+='<div class="budget-card"><p class="budget-label">'+esc(b.label)+'</p><p class="budget-value">'+esc(b.value)+'</p><p class="budget-sub">'+esc(b.sub)+'</p><div class="budget-bar"><div class="budget-bar-fill '+cls(b.used,b.max)+'" style="width:'+pct(b.used,b.max).toFixed(0)+'%"></div></div></div>';
    }
    grid.innerHTML=html;
  }

  function renderRankings(){
    var body=$('rankings-body'), count=$('rankings-count'), empty=$('rankings-empty');
    if(!body) return;
    var data=(state.providers||[]).slice().sort(function(a,b){
      var la=a.latency_ms!=null?a.latency_ms:a.avg_latency!=null?a.avg_latency:9999;
      var lb=b.latency_ms!=null?b.latency_ms:b.avg_latency!=null?b.avg_latency:9999;
      if(la!==lb) return la-lb;
      var sa=a.success_rate!=null?a.success_rate:0, sb=b.success_rate!=null?b.success_rate:0;
      return sb-sa;
    });
    if(!data.length){if(empty)empty.hidden=false;if(count)count.textContent='0';return;}
    if(empty) empty.hidden=true;
    if(count) count.textContent=data.length+' providers';
    var html='';
    for(var j=0;j<data.length;j++){
      var p=data[j], lat=p.latency_ms!=null?p.latency_ms:p.avg_latency!=null?p.avg_latency:'—';
      var succ=p.success_rate!=null?p.success_rate.toFixed(0)+'%':'—', model=p.model||'—';
      html+='<tr><td class="num">'+(j+1)+'</td><td class="model">'+esc(p.name||p.provider||'—')+'</td><td class="num">'+esc(lat)+'</td><td class="num">'+esc(succ)+'</td><td class="model">'+esc(model)+'</td></tr>';
    }
    body.innerHTML=html;
  }

  function updateUserPanel(){
    var nameEl=$('user-name'), emailEl=$('user-email'), avatar=$('avatar');
    if(state.user){
      if(nameEl) nameEl.textContent=state.user.name||'Owner';
      if(emailEl) emailEl.textContent=state.user.email||'—';
      if(avatar) avatar.textContent=(state.user.name||'?').charAt(0).toUpperCase();
    } else {
      if(nameEl) nameEl.textContent='Guest';
      if(emailEl) emailEl.textContent='—';
      if(avatar) avatar.textContent='?';
    }
  }

  var CURRENT_VIEW='overview';

  function showView(name){
    CURRENT_VIEW=name;
    bySelAll('.view-panel').forEach(function(panel){panel.classList.toggle('is-active',panel.getAttribute('data-view')===name);});
    bySelAll('.nav-item').forEach(function(nav){
      var navName=nav.getAttribute('data-nav'), href=nav.getAttribute('href')||'';
      nav.classList.toggle('is-active',(href==='#'+name)||(navName===name));
    });
    var titleEl=$('page-title');
    var titleMap={overview:'Overview',sessions:'Sessions',logs:'Logs',budget:'Budget',tokens:'Tokens',skills:'Skills',rankings:'Provider Rankings',mcp:'MCP',memory:'Memory',routing:'Routing',security:'Security',settings:'Settings'};
    if(titleEl) titleEl.textContent=titleMap[name]||name;
    var eyebrow=$('topbar-eyebrow'); if(eyebrow) eyebrow.textContent='Lionel workspace';
    if(name==='overview'){renderOverview();renderSessionsOverview();renderProviders();renderTokenChartFromSummary();renderRequestsChart();}
    else if(name==='sessions') renderSessionsFull();
    else if(name==='logs') renderAuditLog();
    else if(name==='budget') renderBudget();
    else if(name==='tokens'){renderTokensHourly();renderTokensProvider();}
    else if(name==='skills') renderSkills();
    else if(name==='rankings') renderRankings();
  }

  function initNav(){
    var filter=$('nav-filter');
    if(filter){
      filter.addEventListener('input',function(){
        var q=filter.value.trim().toLowerCase();
        bySelAll('.nav-item').forEach(function(item){
          var label=(item.querySelector('.nav-label')||item).textContent.toLowerCase();
          var sub=(item.querySelector('.nav-sub')||{}).textContent||'';
          item.style.display=(!q||label.indexOf(q)!==-1||sub.toLowerCase().indexOf(q)!==-1)?'':'none';
        });
      });
    }
    bySelAll('.nav-item').forEach(function(nav){
      nav.addEventListener('click',function(e){
        e.preventDefault();
        var view=nav.getAttribute('data-nav');
        if(view) showView(view.toLowerCase());
      });
    });
    var signout=$('sign-out');
    if(signout){
      signout.addEventListener('click',function(){
        state.loggedIn=false; state.user=null;
        clearBanner(); flash('Signed out','warn',false);
        updateUserPanel(); renderLoginView();
      });
    }
  }

  function initTheme(){
    var btn=$('theme-toggle'); if(!btn) return;
    var html=document.documentElement;
    btn.addEventListener('click',function(){
      var isLight=html.classList.contains('light');
      if(isLight){html.classList.remove('light');try{localStorage.setItem('lionel_theme','dark');}catch(e){}}
      else{html.classList.add('light');try{localStorage.setItem('lionel_theme','light');}catch(e){}}
    });
  }

  function initSearch(){
    var search=$('content-search'); if(!search) return;
    var timer=null;
    search.addEventListener('input',function(){
      if(timer) clearTimeout(timer);
      timer=setTimeout(function(){renderSessionsOverview();renderProviders();},200);
    });
  }

  function initSkillsFilter(){
    var filter=$('skills-filter'); if(!filter) return;
    filter.addEventListener('input',function(){
      var q=filter.value.trim().toLowerCase();
      bySelAll('#skills-list li').forEach(function(li){
        var name=(li.querySelector('.skill-name')||li).textContent.toLowerCase();
        var tags=''; var meta=li.querySelector('.skill-meta');
        if(meta) tags=meta.textContent.toLowerCase();
        li.style.display=(!q||name.indexOf(q)!==-1||tags.indexOf(q)!==-1)?'':'none';
      });
    });
  }

  function renderLoginView(){
    var main=document.querySelector('.main'); if(!main) return;
    main.innerHTML =
      '<header class="topbar">'+
        '<div><p class="topbar-eyebrow">Lionel workspace</p><h1 id="page-title">Sign in</h1></div>'+
        '<div class="topbar-actions">'+
          '<button class="icon-button" id="theme-toggle" type="button" aria-pressed="true" title="Toggle theme">'+
            '<svg class="icon icon-moon" aria-hidden="true"><use href="#i-moon"></use></svg>'+
            '<svg class="icon icon-sun"  aria-hidden="true"><use href="#i-sun"></use></svg>'+
          '</button>'+
        '</div>'+
      '</header>'+
      '<main class="content" id="content-area" style="max-width:420px;margin:0 auto">'+
        '<div class="banner banner--info" id="login-banner">'+
          '<svg class="empty-icon" style="width:16px;height:16px"><use href="#i-key"></use></svg> '+
          'Telegram bot <code>8828084719:***</code> · admin <code>1650192264</code> · online: on'+
        '</div>'+
        '<div class="login-card">'+
          '<div class="brand--lg"><span class="brand-mark" aria-hidden="true">L</span><span class="brand-word">LIONEL</span></div>'+
          '<h1 class="login-title">Dashboard sign in</h1>'+
          '<p class="login-sub">Owner access — connect to the live agent backend.</p>'+
          '<form class="login-form" id="login-form" novalidate>'+
            '<div class="field"><label class="field-label" for="login-email">Email</label>'+
              '<input id="login-email" name="email" type="email" value="'+esc('+254712633234@lionel.local')+'" autocomplete="username" required></div>'+
            '<div class="field"><label class="field-label" for="login-pass">Password</label>'+
              '<input id="login-pass" name="password" type="password" value="'+esc(LOGIN_PASS)+'" autocomplete="current-password" required></div>'+
            '<button class="button button--primary button--block" type="submit" id="login-submit">Sign in</button>'+
            '<p class="form-error" id="login-error" hidden></p>'+
          '</form>'+
          '<p class="login-footer">Lionel v0.1.0 · Owner access</p>'+
        '</div>'+
      '</main>';

    initTheme();
    var form=$('login-form'), errorEl=$('login-error'), submitBtn=$('login-submit'), emailInput=$('login-email');
    if(form){
      form.addEventListener('submit',function(e){
        e.preventDefault();
        if(!submitBtn) return;
        submitBtn.disabled=true; submitBtn.textContent='Signing in…';
        var email=(emailInput?emailInput.value:'').trim().toLowerCase();
        var pass=($('login-pass')?$('login-pass').value:'').trim();
        if(!email||!pass){
          if(errorEl){errorEl.hidden=false;errorEl.textContent='Please enter your email and password.';}
          submitBtn.disabled=false; submitBtn.textContent='Sign in';
          return;
        }
        api('/api/login',{method:'POST',body:{email:email,password:pass}}).then(function(data){
          if(data&&data.ok){
            state.loggedIn=true;
            state.user={name:data.user_name||data.user_name||'Owner',email:data.user_email||email};
            clearBanner(); flash('Signed in as '+(state.user.name||'owner'),'success',false);
            updateUserPanel(); renderDashboard();
          } else {
            if(errorEl){errorEl.hidden=false;errorEl.textContent=(data&&data.error)?data.error:'Invalid credentials';}
            submitBtn.disabled=false; submitBtn.textContent='Sign in';
          }
        }).catch(function(err){
          if(errorEl){errorEl.hidden=false;errorEl.textContent=err.message==='unauthorized'?'Invalid credentials':'Backend unavailable — '+err.message;}
          submitBtn.disabled=false; submitBtn.textContent='Sign in';
        });
      });
      if(emailInput&&emailInput.value===LOGIN_EMAIL&&$('login-pass').value===LOGIN_PASS){
        setTimeout(function(){form.dispatchEvent(new Event('submit',{cancelable:true}));},300);
      }
      if(emailInput) setTimeout(function(){emailInput.focus();},100);
    }
  }

  function renderViewPanels(){
    return [
      '<section class="view-panel is-active" id="view-overview" data-view="overview">'+overviewPanels()+'</section>',
      overviewSection('sessions','Sessions','Every chat session the agent has handled, sorted newest first. Shows model, turn count, prompt and completion tokens, total tokens, and current status.', 'sessions-full-body', 'sessions-full-empty', 'sessions-full-count'),
      overviewSection('logs','Logs','Audit trail of tools and commands the agent ran. Each row records the time, event, tool, payload detail, and result.', 'logs-body', 'logs-empty', 'logs-count', 'audit-table'),
      '<section class="view-panel" id="view-budget" data-view="budget"><p class="view-description">Spend limits and live usage against each budget line. Bars fill as the agent consumes tokens.</p><div class="budget-grid" id="budget-grid"></div></section>',
      '<section class="view-panel" id="view-tokens" data-view="tokens"><p class="view-description">Prompt vs completion token consumption over the last 24 hours, plus a per-provider breakdown.</p><div class="grid grid--split"><article class="card"><header class="card-head"><h2>Token Usage by Hour</h2><span class="card-note" id="tokens-chart-note">loading…</span></header><div class="chart" id="tokens-hourly-chart"></div></article><article class="card"><header class="card-head"><h2>By Provider</h2><span class="card-note" id="tokens-provider-note">loading…</span></header><div class="chart" id="tokens-provider-chart"></div></article></div></section>',
      '<section class="view-panel" id="view-skills" data-view="skills"><p class="view-description">Every skill loaded into the agent. Use the filter to search by name or tag.</p><div class="card"><header class="card-head"><h2>Loaded Skills</h2><span class="card-note" id="skills-count">—</span></header><ul class="skills-list" id="skills-list"></ul><p class="empty" id="skills-empty" hidden>No skills loaded yet.</p><input id="skills-filter" type="search" placeholder="Filter skills by name or tag" class="field" style="margin-top:12px" aria-label="Filter skills"></div></section>',
      overviewSection('rankings','Provider Rankings','Latency and reliability ranking across all configured providers, lowest latency first.', 'rankings-body', 'rankings-empty', 'rankings-count'),
      '<section class="view-panel" id="view-mcp" data-view="mcp"><p class="view-description">Model Context Protocol tool servers the agent can reach.</p><p class="empty">Coming soon.</p></section>',
      '<section class="view-panel" id="view-memory" data-view="memory"><p class="view-description">Memory stores the agent reads and writes across sessions.</p><p class="empty">Coming soon.</p></section>',
      '<section class="view-panel" id="view-routing" data-view="routing"><p class="view-description">Current routing strategy and model selection policy.</p><p class="empty">Coming soon.</p></section>',
      '<section class="view-panel" id="view-security" data-view="security"><p class="view-description">Safety policy: rate limits, provider allowlists, and tool sandboxing.</p><p class="empty">Coming soon.</p></section>',
      '<section class="view-panel" id="view-settings" data-view="settings"><p class="view-description">Workspace settings, theme, and profile.</p><p class="empty">Coming soon.</p></section>',
    ].join('');
  }

  function overviewSection(viewId, title, desc, bodyId, emptyId, countId, tableClass) {
    tableClass = tableClass || 'table';
    return '<section class="view-panel" id="view-'+viewId+'" data-view="'+viewId+'">'+
      '<p class="view-description">'+esc(desc)+'</p>'+
      '<article class="card"><header class="card-head"><h2>'+esc(title)+'</h2><span class="card-note" id="'+countId+'">—</span></header>'+
      '<table class="'+tableClass+'"><thead><tr>'+
        '<th scope="col">Session ID</th><th scope="col">Model</th><th scope="col">Started</th>'+
        '<th scope="col" class="num">Turns</th><th scope="col" class="num">Prompt</th>'+
        '<th scope="col" class="num">Completion</th><th scope="col" class="num">Tokens</th><th scope="col">Status</th>'+
      '</tr></thead><tbody id="'+bodyId+'"></tbody></table>'+
      '<p class="empty" id="'+emptyId+'" hidden>No data on record yet.</p></article></section>';
  }

  function overviewPanels(){
    return [
      '<section class="cards" aria-label="Status summary">'+
        statCard('Active Sessions','stat-sessions','stat-sessions-note','of 20 concurrent slots')+
        statCard('Requests Today','stat-requests','stat-requests-note','today')+
        statCard('Tokens Used','stat-tokens','stat-tokens-note','—')+
        statCard('Error Rate','stat-errors','stat-errors-note','last 24 hours')+
      '</section>',
      '<section class="grid grid--split">'+
        '<article class="card"><header class="card-head"><h2>Recent Sessions</h2><span class="card-note" id="sessions-count">—</span></header>'+
          '<table class="table"><thead><tr>'+
            '<th scope="col">Session ID</th><th scope="col">Model</th><th scope="col" class="num">Turns</th>'+
            '<th scope="col" class="num">Tokens</th><th scope="col">Status</th>'+
          '</tr></thead><tbody id="sessions-body"></tbody></table>'+
          '<p class="empty" id="sessions-empty" hidden>No sessions match the current search.</p></article>'+
        '<article class="card"><header class="card-head"><h2>Provider Health</h2><span class="card-note" id="providers-count">—</span></header>'+
          '<ul class="providers" id="providers-list"></ul>'+
          '<p class="empty" id="providers-empty" hidden>No providers match the current search.</p></article>'+
      '</section>',
      '<section class="grid grid--split">'+
        '<article class="card"><header class="card-head"><h2>Token Usage</h2><span class="card-note" id="token-chart-note">loading…</span></header><div class="chart" id="token-chart"></div></article>'+
        '<article class="card"><header class="card-head"><h2>Requests per Hour</h2><span class="card-note" id="requests-chart-note">loading…</span></header><div class="chart" id="requests-chart"></div></article>'+
      '</section>',
    ].join('');
  }

  function statCard(label,valueId,noteId,noteText){
    return '<article class="card stat"><p class="stat-label">'+esc(label)+'</p><p class="stat-value" id="'+valueId+'">—</p><p class="stat-note" id="'+noteId+'">'+esc(noteText)+'</p></article>';
  }

  function refreshAllData(){
    refreshHealth(); refreshSessions(); refreshProviders(); refreshTokensSummary(); refreshSkillsSummary(); refreshAuditLog();
  }

  function refreshHealth(){
    api('/api/health').then(function(h){state.health=h;var ver=$('sidebar-version');if(ver)ver.textContent='v'+(h.version||'0.1.0');}).catch(function(){state.health=null;var ver=$('sidebar-version');if(ver)ver.textContent='v0.1.0 — unreachable';});
  }
  function refreshSessions(){
    api('/api/sessions').then(function(d){state.sessions=Array.isArray(d)?d:[];renderSessionsOverview();renderSessionsFull();renderOverview();}).catch(function(){state.sessions=[];renderSessionsOverview();renderSessionsFull();flash('Failed to load sessions','warn',false);});
  }
  function refreshProviders(){
    api('/api/providers').then(function(d){state.providers=Array.isArray(d)?d:[];renderProviders();renderRankings();}).catch(function(){state.providers=[];renderProviders();renderRankings();flash('Failed to load providers','warn',false);});
  }
  function refreshTokensSummary(){
    api('/api/tokens/summary').then(function(d){state.tokensSummary=d;renderTokenChartFromSummary();renderRequestsChart();renderOverview();renderBudget();}).catch(function(){state.tokensSummary=null;var tc=$('token-chart');if(tc)tc.innerHTML='<div class="empty">No token data</div>';var rc=$('requests-chart');if(rc)rc.innerHTML='<div class="empty">No request data</div>';flash('Failed to load token summary','warn',false);});
  }
  function refreshSkillsSummary(){
    api('/api/skills/summary').then(function(d){state.skillsSummary=d;renderSkills();}).catch(function(){state.skillsSummary=null;var list=$('skills-list');if(list)list.innerHTML='<div class="empty">Skills data unavailable</div>';flash('Failed to load skills','warn',false);});
  }
  function refreshAuditLog(){
    api('/api/audit/activities').then(function(d){state.auditLog=Array.isArray(d)?d:[];renderAuditLog();}).catch(function(){state.auditLog=[];renderAuditLog();flash('Failed to load audit log','warn',false);});
  }

  function renderDashboard(){
    var main=document.querySelector('.main'); if(!main) return;
    var html =
      '<header class="topbar">'+
        '<div><p class="topbar-eyebrow" id="topbar-eyebrow">Lionel workspace</p><h1 id="page-title">Overview</h1></div>'+
        '<div class="topbar-actions">'+
          '<div class="search"><svg class="icon" aria-hidden="true"><use href="#i-search"></use></svg><input id="content-search" type="search" placeholder="Search sessions, providers" aria-label="Search sessions and providers"></div>'+
          '<button class="icon-button" id="theme-toggle" type="button" aria-pressed="true" title="Toggle theme"><svg class="icon icon-moon" aria-hidden="true"><use href="#i-moon"></use></svg><svg class="icon icon-sun"  aria-hidden="true"><use href="#i-sun"></use></svg></button>'+
          '<div class="user"><span class="avatar" id="avatar">?</span><span class="user-meta"><span class="user-name" id="user-name">'+esc(state.user?state.user.name:'Guest')+'</span><span class="user-mail" id="user-email">'+esc(state.user?state.user.email:'—')+'</span></span></div>'+
        '</div>'+
      '</header>'+
      '<main class="content" id="content-area"><div id="banner-slot"></div>'+renderViewPanels()+'</main>';
    main.innerHTML=html;
    updateUserPanel();
    initNav(); initTheme(); initSearch(); initSkillsFilter();
    refreshAllData();
    showView('overview');
    setInterval(function(){
      refreshAllData();
      if(CURRENT_VIEW==='overview'){renderOverview();renderSessionsOverview();renderProviders();renderTokenChartFromSummary();renderRequestsChart();}
      else if(CURRENT_VIEW==='sessions') renderSessionsFull();
      else if(CURRENT_VIEW==='logs') renderAuditLog();
      else if(CURRENT_VIEW==='budget') renderBudget();
      else if(CURRENT_VIEW==='tokens'){renderTokensHourly();renderTokensProvider();}
      else if(CURRENT_VIEW==='skills') renderSkills();
      else if(CURRENT_VIEW==='rankings') renderRankings();
    },30000);
  }

  function init(){
    try{var stored=localStorage.getItem('lionel_theme');var theme=stored==='light'?'light':'dark';document.documentElement.classList.add('theme-'+theme);}catch(e){document.documentElement.classList.add('theme-dark');}
    if(document.getElementById('nav')){
      initNav(); initTheme(); initSearch(); initSkillsFilter();
      refreshAllData(); showView('overview');
      return;
    }
    renderLoginView();
  }

  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',init);}else{init();}

  window.__dashboard={refresh:refreshAllData,state:state,api:api,showView:showView};
})();
