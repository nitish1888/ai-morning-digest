(function(){
const $=id=>document.getElementById(id);
const API={articles:'/api/articles',refresh:'/api/refresh',search:'/api/search',news:'/api/news-feed'};

let poll=null, articles=[], filter='all', searching=false;

const TAG_COLORS={
    'LLM & Foundation Models':'99,102,241','AI Agents & Autonomy':'168,85,247',
    'RAG & Retrieval':'34,211,238','ML Architecture & Systems':'251,146,60',
    'GenAI Applications':'236,72,153','Computer Vision':'52,211,153',
    'NLP & Language':'96,165,250','MLOps & Deployment':'251,191,36',
    'AI Safety & Ethics':'248,113,113','Data Science & Analytics':'45,212,191',
    'Research & Papers':'167,139,250','Tutorials & How-To':'74,222,128',
    'Industry News':'148,163,184','Claude & Anthropic':'217,119,87'
};

function esc(s){if(!s)return '';const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function ago(iso){if(!iso)return '';const h=Math.floor((Date.now()-new Date(iso))/36e5);return h<1?'just now':h<24?h+'h ago':Math.floor(h/24)+'d ago'}
function badgeStyle(tag){const c=TAG_COLORS[tag]||'139,92,246';return `background:rgba(${c},.08);border-color:rgba(${c},.2);color:rgba(${c},1)`}

// ── Filters ──────────────────────────────────────────────────────

function buildFilters(list){
    const tags=new Set();
    list.forEach(a=>{if(a.classification)tags.add(a.classification)});
    const row=$('filterRow');row.innerHTML='';

    // "Top 10" pill — always first
    const top=document.createElement('button');
    top.textContent='\u2B50 Top 10';
    top.className='filter-chip top10'+(filter==='all'?' on':'');
    top.onclick=()=>{filter='all';buildFilters(articles);render(articles)};
    row.appendChild(top);

    // Category pills
    [...tags].sort().forEach(t=>{
        const b=document.createElement('button');b.textContent=t;
        b.className='filter-chip'+(filter===t?' on':'');
        b.onclick=()=>{filter=t;buildFilters(articles);render(articles)};
        row.appendChild(b);
    });

    $('filterSection').style.display=tags.size?'block':'none';
}

// ── Render article cards ─────────────────────────────────────────

function render(list){
    const grid=$('cardsGrid');grid.innerHTML='';
    const show=filter==='all'?list:list.filter(a=>a.classification===filter);
    if(!show.length){grid.innerHTML='<div class="no-results">No articles match this filter</div>';return}

    show.forEach((a,i)=>{
        const pct=Math.round((a.score||0)*100);
        const cls=a.classification?`<span class="badge" style="${badgeStyle(a.classification)}">${esc(a.classification)}</span>`:'';
        const prob=a.problem_summary?`<div class="card-problem"><span class="lbl">Solves</span><span class="val">${esc(a.problem_summary)}</span></div>`:'';
        const ins=a.insight?`<div class="card-insight"><span class="val">${esc(a.insight)}</span><span class="g4">Gemma</span></div>`:'';
        const tags=(a.tags||[]).slice(0,3).map(t=>`<span>${esc(t)}</span>`).join('');

        const el=document.createElement('article');el.className='card';el.style.animationDelay=`${i*.02}s`;
        el.innerHTML=`
            <div class="card-num">${i+1}</div>
            <div class="card-top">
                <div class="card-badges"><span class="badge badge-source">${esc(a.source)}</span>${cls}</div>
                <span class="score-pill">${pct}%</span>
            </div>
            <div class="card-title"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a></div>
            ${prob}${ins}
            <div class="card-summary">${esc(a.summary||'')}</div>
            <div class="card-foot"><div class="card-tags">${tags}</div><span class="card-meta">${ago(a.published)}</span></div>`;
        grid.appendChild(el);
    });
}

function showView(v){
    $('loadingState').style.display=v==='loading'?'flex':'none';
    $('articlesWrap').style.display=v==='articles'?'block':'none';
    $('emptyState').style.display=v==='empty'?'flex':'none';
}

// ── News sidebar ─────────────────────────────────────────────────

async function fetchNewsFeed(){
    try{
        const d=await(await fetch(API.news)).json();
        const items=d.items||[];
        const wrap=$('sidebarItems');
        if(!items.length){wrap.innerHTML='<div class="sidebar-loading">No news yet</div>';return}
        wrap.innerHTML='';

        items.forEach(n=>{
            const a=document.createElement('a');
            a.className='news-item';a.href=n.url;a.target='_blank';a.rel='noopener';

            const thumb=n.image_url
                ?`<img src="${esc(n.image_url)}" alt="" loading="lazy" onerror="this.parentNode.innerHTML='<span class=placeholder>\u{1F4F0}</span>'">`
                :'<span class="placeholder">\u{1F4F0}</span>';

            a.innerHTML=`
                <div class="news-thumb">${thumb}</div>
                <div class="news-body">
                    <div class="news-title">${esc(n.title)}</div>
                    <div class="news-meta"><span class="news-src">${esc(n.source)}</span><span class="dot"></span><span>${ago(n.published)}</span></div>
                </div>`;
            wrap.appendChild(a);
        });
    }catch(e){console.error('News feed error:',e)}
}

// ── Fetch main articles ──────────────────────────────────────────

async function fetchArticles(){
    try{
        const d=await(await fetch(API.articles)).json();
        if(d.is_loading&&!d.articles.length){
            $('loadingTitle').textContent='Scanning AI/ML sources...';
            $('loadingSub').textContent='Scoring articles from TDS, Medium, ArXiv & more';
            showView('loading');$('refreshBtn').classList.add('spinning');startPoll();return;
        }
        $('refreshBtn').classList.remove('spinning');stopPoll();
        if(!d.articles.length&&!searching){showView('empty');return}
        if(!searching){
            articles=d.articles;filter='all';buildFilters(articles);render(articles);showView('articles');
        }
        $('metaCount').textContent=d.articles.length;
        $('metaScanned').textContent=d.total_scanned||'--';
        $('metaTime').textContent=d.last_refresh?ago(d.last_refresh):'--';
    }catch(e){console.error(e)}
}

// ── Search ───────────────────────────────────────────────────────

async function doSearch(q){
    q=q.trim();if(!q){clearSearch();return}
    searching=true;
    $('searchClear').style.display='grid';$('searchKbd').style.display='none';
    $('loadingTitle').textContent=`Searching "${q}"...`;
    $('loadingSub').textContent='Fetching live from sources + re-ranking with LLM';
    showView('loading');
    document.querySelectorAll('.quick-tags button').forEach(b=>b.classList.remove('active'));

    try{
        const d=await(await fetch(API.search,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})})).json();
        if(!d.articles||!d.articles.length){
            $('emptyTitle').textContent='No results';
            $('emptySub').textContent=`Nothing matched "${q}"`;
            showView('empty');return;
        }
        articles=d.articles;filter='all';buildFilters(articles);render(articles);showView('articles');
    }catch(e){console.error(e);$('emptyTitle').textContent='Search failed';showView('empty')}
}

function clearSearch(){
    searching=false;$('searchInput').value='';
    $('searchClear').style.display='none';$('searchKbd').style.display='';
    document.querySelectorAll('.quick-tags button').forEach(b=>b.classList.remove('active'));
    fetchArticles();
}

// ── Refresh ──────────────────────────────────────────────────────

async function triggerRefresh(){
    searching=false;clearSearch();
    $('refreshBtn').classList.add('spinning');showView('loading');
    $('loadingTitle').textContent='Scanning AI/ML sources...';
    $('loadingSub').textContent='Scoring articles from TDS, Medium, ArXiv & more';
    try{await fetch(API.refresh,{method:'POST'});startPoll()}catch(e){$('refreshBtn').classList.remove('spinning')}
}

function startPoll(){if(!poll)poll=setInterval(fetchArticles,3000)}
function stopPoll(){if(poll){clearInterval(poll);poll=null}}

// ── Events ───────────────────────────────────────────────────────

$('refreshBtn').onclick=triggerRefresh;
$('searchInput').onkeydown=e=>{if(e.key==='Enter')doSearch($('searchInput').value);if(e.key==='Escape')clearSearch()};
$('searchClear').onclick=clearSearch;

document.querySelectorAll('.quick-tags button').forEach(b=>{
    b.onclick=()=>{
        document.querySelectorAll('.quick-tags button').forEach(x=>x.classList.remove('active'));
        b.classList.add('active');
        $('searchInput').value=b.dataset.q;
        doSearch(b.dataset.q);
    };
});

// Auto-refresh main every 60s (if not searching), sidebar every 5 min
setInterval(()=>{if(articles.length&&!searching)fetchArticles()},60000);
setInterval(fetchNewsFeed,300000);

// Boot
fetchArticles();
fetchNewsFeed();
})();
