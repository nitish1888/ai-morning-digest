(function(){
const $=id=>document.getElementById(id);
const API={articles:'/api/articles',refresh:'/api/refresh',search:'/api/search',news:'/api/news-feed'};

let poll=null, articles=[], filter='all', searching=false;

const TAG_COLORS={
    'LLM & Foundation Models':'99,102,241','AI Agents & Autonomy':'168,85,247',
    'RAG & Retrieval':'34,211,238','ML Architecture & Systems':'251,146,60',
    'GenAI Applications':'236,72,153','Computer Vision':'52,211,153',
    'NLP & Language':'96,165,250','MLOps & Deployment':'251,191,36',
    'AI Safety & Ethics':'248,113,133','Data Science & Analytics':'45,212,191',
    'Research & Papers':'167,139,250','Tutorials & How-To':'74,222,128',
    'Industry News':'148,163,184','Claude & Anthropic':'217,119,87'
};

function esc(s){if(!s)return '';const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function ago(iso){if(!iso)return '';const h=Math.floor((Date.now()-new Date(iso))/36e5);return h<1?'just now':h<24?h+'h':Math.floor(h/24)+'d'}

// ── Filters ──

function setFilter(f){
    filter=f;
    buildFilters(articles);
    render(articles);
}

function buildFilters(list){
    const tags=new Set();
    list.forEach(a=>{if(a.classification)tags.add(a.classification)});
    tags.add('AI Architect');
    const row=$('filterRow');row.innerHTML='';
    if(!tags.size){$('filterSection').style.display='none';return}

    const allBtn=document.createElement('button');
    allBtn.textContent='All';
    allBtn.className='f-chip'+(filter==='all'?' active':'');
    allBtn.onclick=()=>setFilter('all');
    row.appendChild(allBtn);

    [...tags].sort().forEach(t=>{
        const b=document.createElement('button');
        b.textContent=t;
        b.className='f-chip'+(filter===t?' active':'');
        b.onclick=()=>setFilter(t);
        row.appendChild(b);
    });

    $('filterSection').style.display='block';
}

// ── Render cards ──

function render(list){
    const grid=$('cardsGrid');grid.innerHTML='';
    const show=filter==='all'?list:list.filter(a=>a.classification===filter);
    if(!show.length){grid.innerHTML='<div class="no-results">No articles match "'+esc(filter)+'"</div>';return}

    show.forEach((a,i)=>{
        const hasImg=!!a.image_url;
        const imgHtml=hasImg
            ?`<div class="card-img"><img src="${esc(a.image_url)}" alt="" loading="lazy" onerror="this.parentNode.style.display='none';this.closest('.card').classList.remove('has-img')"></div>`
            :'';

        // Pick best summary: problem_summary > insight > summary
        const desc=a.problem_summary||a.insight||a.summary||'';

        const el=document.createElement('article');
        el.className='card'+(hasImg?' has-img':'');
        el.innerHTML=`
            <div class="card-body">
                <div class="card-num">${i+1}</div>
                <div class="card-title"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a></div>
                ${desc?`<div class="card-desc">${esc(desc)}</div>`:''}
                <div class="card-sub">
                    <span class="src">${esc(a.source)}</span>
                    ${a.classification?'<span class="dot"></span><span>'+esc(a.classification)+'</span>':''}
                    <span class="dot"></span>
                    <span>${ago(a.published)}</span>
                </div>
            </div>${imgHtml}`;
        grid.appendChild(el);
    });
}

function showView(v){
    $('loadingState').style.display=v==='loading'?'flex':'none';
    $('articlesWrap').style.display=v==='articles'?'block':'none';
    $('emptyState').style.display=v==='empty'?'flex':'none';
}

// ── Sidebar — max 10 items ──

async function fetchNewsFeed(){
    try{
        const d=await(await fetch(API.news)).json();
        const items=(d.items||[]).slice(0,10);
        const wrap=$('sidebarItems');
        if(!items.length){wrap.innerHTML='<div class="sidebar-loading">No news yet</div>';return}
        wrap.innerHTML='';

        items.forEach(n=>{
            const a=document.createElement('a');
            a.className='news-item';a.href=n.url;a.target='_blank';a.rel='noopener';
            const hasImg=!!n.image_url;

            const imgHtml=hasImg
                ?`<div class="news-img visible"><img src="${esc(n.image_url)}" alt="" loading="lazy" onerror="this.parentNode.classList.remove('visible')"></div>`
                :'';

            a.innerHTML=`
                ${imgHtml}
                <div class="news-title">${esc(n.title)}</div>
                <div class="news-meta"><span class="src">${esc(n.source)}</span> &middot; ${ago(n.published)}</div>`;
            wrap.appendChild(a);
        });
    }catch(e){console.error(e)}
}

// ── Main fetch ──

async function fetchArticles(){
    try{
        const d=await(await fetch(API.articles)).json();
        if(d.is_loading&&!d.articles.length){
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

// ── Search ──

async function doSearch(q){
    q=q.trim();if(!q){clearSearch();return}
    searching=true;
    $('searchClear').style.display='grid';$('searchKbd').style.display='none';
    $('loadingTitle').textContent=`Searching "${q}"...`;
    $('loadingSub').textContent='Fetching live + re-ranking';
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
    }catch(e){console.error(e);showView('empty')}
}

function clearSearch(){
    searching=false;$('searchInput').value='';
    $('searchClear').style.display='none';$('searchKbd').style.display='';
    document.querySelectorAll('.quick-tags button').forEach(b=>b.classList.remove('active'));
    fetchArticles();
}

async function triggerRefresh(){
    searching=false;clearSearch();
    $('refreshBtn').classList.add('spinning');showView('loading');
    try{await fetch(API.refresh,{method:'POST'});startPoll()}catch(e){$('refreshBtn').classList.remove('spinning')}
}

function startPoll(){if(!poll)poll=setInterval(fetchArticles,3000)}
function stopPoll(){if(poll){clearInterval(poll);poll=null}}

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

setInterval(()=>{if(articles.length&&!searching)fetchArticles()},60000);
setInterval(fetchNewsFeed,300000);
fetchArticles();
fetchNewsFeed();
})();
