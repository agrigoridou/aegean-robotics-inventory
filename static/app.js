'use strict';
const $=s=>document.querySelector(s);
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>n==null?'—':new Intl.NumberFormat('el-GR').format(n);
const state={auth:null,view:'find',categories:[],locations:[],filters:{q:'',category:'',location:'',unknown:false},stats:null,items:[],selected:null,scanStream:null,scanActive:false};
let searchTimer=null,toastTimer=null;

async function req(path,method='GET',body){
 const opt={method,headers:{}};
 if(method!=='GET'&&state.auth?.csrf)opt.headers['X-CSRF-Token']=state.auth.csrf;
 if(body!==undefined){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
 const r=await fetch(path,opt);
 let obj;try{obj=await r.json()}catch(_){throw new Error('Αδυναμία επικοινωνίας με τον server.');}
 if(r.status===401){location.assign('/login');throw new Error('Η συνεδρία έληξε.');}
 if(!r.ok)throw new Error(obj.error||`HTTP ${r.status}`);
 return obj;
}
function notify(msg,error=false){const n=$('#toast');n.className='toast'+(error?' error':'');n.textContent=msg;clearTimeout(toastTimer);toastTimer=setTimeout(()=>n.classList.add('hidden'),4200)}
function handleError(err){console.error(err);notify(err?.message||'Κάτι πήγε στραβά.',true)}
function locLabel(id,compact=false){if(!id)return 'Χωρίς θέση';const l=state.locations.find(x=>x.id===id);return compact?id.replace('C','Ν').replace('-S',' · Θ'):l?.label||id}
function optionList(arr,selected,emptyLabel='Επιλογή...',labelKey='label',idKey='id'){
 return `<option value="">${e(emptyLabel)}</option>`+arr.map(x=>`<option value="${e(x[idKey])}" ${x[idKey]===selected?'selected':''}>${e(x[labelKey])}</option>`).join('');
}
function categoriesOptions(selected){return state.categories.map(x=>`<option ${x===selected?'selected':''} value="${e(x)}">${e(x)}</option>`).join('');}
function locationsOptions(selected,empty='Επίλεξε θέση'){return optionList(state.locations.filter(x=>x.id!=='C99-S00'),selected,empty)}

async function refreshStats(){const s=await req('/api/stats');state.stats=s;state.categories=s.categories;
 $('#stats').innerHTML=[['▦','Διαφορετικές εγγραφές',s.items],['◈','Διαθέσιμα τεμάχια',s.units_in],['↗','Εκτός αποθήκης',s.units_out],['!','Άγνωστες ποσότητες',s.unknown]].map(x=>`<div class="stat"><div class="stat-icon">${x[0]}</div><div><span class="stat-label">${e(x[1])}</span><div class="stat-value">${fmt(x[2])}</div></div></div>`).join('');}
async function refreshLocations(){state.locations=await req('/api/locations')}
function setView(view){
 state.view=view;
 document.querySelectorAll('.navlink').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 const info={find:['Πού είναι;','Βρες ό,τι χρειάζεσαι','Γράψε τι ψάχνεις και δες σε ποια ντουλάπα και θέση βρίσκεται τώρα.'],inventory:['Αποθήκη','Οργάνωση αποθήκης','Όλα τα εξαρτήματα, οι θέσεις και οι κινήσεις σε ένα σημείο.'],locations:['Ντουλάπες','Χάρτης αποθήκευσης','Πού βρίσκεται κάθε εξάρτημα στο εργαστήριο.'],history:['Κινήσεις','Ιστορικό κινήσεων','Ιχνηλασιμότητα για παραλαβές, αφαιρέσεις και επιστροφές.'],audit:['AI Απογραφή','Απογραφή με φωτογραφία','Οπτική εκτίμηση ραφιού με Gemini και χειροκίνητη επιβεβαίωση.'],loans:['Δανεισμοί','Εξοπλισμός σε χρήση','Ποιος έχει τι, για ποιο project και πότε πρέπει να επιστραφεί.'],alerts:['Ειδοποιήσεις','Πρόβλεψη και όρια αποθεμάτων','Χαμηλές ποσότητες, εκκρεμότητες και ενδεικτικές ανάγκες.'],assistant:['AI Βοηθός','Ρώτησε το εργαστήριο','Απαντήσεις με πραγματικά δεδομένα από τις ντουλάπες.'],users:['Χρήστες','Διαχείριση πρόσβασης','Δημιουργία, ρόλοι και διαχείριση λογαριασμών.'],settings:['Ρυθμίσεις','Ρυθμίσεις συστήματος','QR ετικέτες, αντίγραφα ασφαλείας και σύνδεση κινητών.']}[view];
 $('#crumbCurrent').textContent=info[0];$('#viewTitle').textContent=info[1];$('#viewSubtitle').textContent=info[2];
 $('#stats').style.display=view==='settings'?'none':'';
 $('#addItemBtn').style.display=view==='inventory'?'':'none';
 if(view==='find')showFind();
 if(view==='inventory')showInventory();
 if(view==='locations')showLocations();
 if(view==='history')showHistory();
 if(view==='settings')showSettings();
 if(view==='audit')showAudit();
 if(view==='loans')showLoans();
 if(view==='alerts')showAlerts();
 if(view==='assistant')showAssistant();
 if(view==='users')showUsers();
}
function renderFindMatch(match,idx){
 const total=match.quantity_unknown?`${fmt(match.quantity)}+ γνωστά τεμ. · εκκρεμεί απογραφή`:`${fmt(match.quantity)} τεμάχια`;
 const locs=match.locations.length?match.locations.map(loc=>`<div class="find-location">
  <div class="find-loc-photo">${loc.photo_url?`<img src="${e(loc.photo_url)}" alt="Φωτογραφία ${e(loc.label)}" loading="lazy">`:'<span>▤</span>'}</div>
  <div class="find-loc-details"><strong>${e(loc.label)}</strong><small>${e(loc.id)} · ${fmt(loc.quantity)} καταγεγραμμένα τεμάχια</small></div>
  <button class="btn btn-outline" data-go-location="${e(loc.id)}">Δες ράφι →</button>
 </div>`).join(''):'<div class="banner warn">Δεν υπάρχει διαθέσιμο τεμάχιο σε γνωστή θέση. Δες τις εκκρεμείς αφαιρέσεις ή κάνε απογραφή.</div>';
 return `<article class="find-match ${idx===0?'best':''}">
 <div class="find-match-head">${match.photos.length?`<img class="find-item-photo" src="${e(match.photos[0])}" alt="${e(match.name)}">`:''}<div class="find-match-name"><span class="find-eyebrow">${idx===0?'ΚΑΛΥΤΕΡΗ ΑΝΤΙΣΤΟΙΧΙΣΗ':'ΕΝΑΛΛΑΚΤΙΚΟ ΑΠΟΤΕΛΕΣΜΑ'}</span><h3>${e(match.name)}</h3><p>${e(match.category)} · ${match.skus.length} ${match.skus.length===1?'καταχώριση':'καταχωρίσεις'} Excel</p></div>
  <div class="find-total"><b>${fmt(match.quantity)}</b><small>${match.quantity_unknown?'Γνωστά, + άγνωστα':'Τεμάχια σε απόθεμα'}</small></div></div>
 ${locs}
 ${match.checked_out?`<p class="find-out">↗ ${fmt(match.checked_out)} επιπλέον τεμάχια έχουν καταγραφεί ως εκτός αποθήκης.</p>`:''}
 ${!match.locations.length&&match.initial_positions?.length?`<p class="find-help">Αρχική θέση Excel (όχι επιβεβαιωμένο απόθεμα): ${e(match.initial_positions.join(', '))}</p>`:''}
 <div class="find-actions">${match.skus.map(sku=>`<button class="btn btn-quiet" data-find-item="${e(sku)}">Άνοιγμα είδους ${e(sku)} →</button>`).join('')}</div>
 </article>`;
}
async function lookupFind(){
 const inp=$('#findInput');if(!inp)return;
 const query=inp.value.trim();const out=$('#findResults');
 if(!query){out.innerHTML='<div class="find-empty">Γράψε ένα είδος για να εμφανιστούν οι θέσεις του.</div>';return}
 out.innerHTML='<div class="find-empty">Αναζήτηση στο πραγματικό απόθεμα…</div>';
 try{
  const data=await req('/api/find?'+new URLSearchParams({q:query}));
  if(state.view!=='find'||!$('#findResults'))return;
  if($('#findInput').value.trim()!==query)return;
  out.innerHTML=data.matches.length?`<p class="find-answer">Βρέθηκαν ${data.matches.length} ${data.matches.length===1?'αντιστοίχιση':'πιθανές αντιστοιχίσεις'} για «${e(query)}».</p>${data.matches.map(renderFindMatch).join('')}<p class="find-help">Τα δεδομένα ενημερώνονται από τις επιβεβαιωμένες κινήσεις. Πραγματική τοποθέτηση και ποσότητες χρειάζονται αρχική απογραφή.</p>`:
   `<div class="find-empty">${e(data.message||'Δεν βρέθηκε το αντικείμενο.')}<div style="margin-top:14px"><button class="btn btn-outline" id="findPhotoInstead">✦ Δοκίμασε φωτογραφία με Gemini</button></div></div>`;
  if($('#findPhotoInstead'))$('#findPhotoInstead').onclick=showPhotoSearch;
  out.querySelectorAll('[data-find-item]').forEach(b=>b.onclick=()=>openItem(b.dataset.findItem));
  out.querySelectorAll('[data-go-location]').forEach(b=>b.onclick=()=>{
    state.filters={q:'',category:'',location:b.dataset.goLocation,unknown:false};setView('inventory');
  });
 }catch(err){handleError(err);if($('#findResults'))$('#findResults').innerHTML='<div class="banner warn">Δεν ήταν δυνατή η αναζήτηση.</div>'}
}
function showFind(){
 $('#content').innerHTML=`<section class="find-hero"><div class="find-eyebrow">SMART INVENTORY · ΒΡΕΣ ΤΟ ΣΕ ΔΕΥΤΕΡΟΛΕΠΤΑ</div>
  <h2>Τι ψάχνεις στο εργαστήριο;</h2><p>Ρώτησε με φυσική γλώσσα. Η απάντηση βασίζεται στα πραγματικά δεδομένα του inventory, όχι σε εικασίες του Gemini.</p>
  <form id="findForm" class="find-form"><input id="findInput" class="input" autocomplete="off" placeholder="π.χ. Πού βρίσκεται ένα Raspberry Pi 4;" aria-label="Αναζήτηση είδους και θέσης"><button class="btn btn-primary" type="submit">⌕ Αναζήτηση</button></form>
  <div class="find-samples">Δοκίμασε: <button data-example="Πού είναι το Raspberry Pi 4;">Raspberry Pi 4</button><button data-example="Arduino Uno">Arduino Uno</button><button data-example="servo">Servo motors</button></div>
 </section><div id="findResults" class="find-results"><div class="find-empty">Πληκτρολόγησε ή επίλεξε ένα παράδειγμα για να δεις πού βρίσκεται.</div></div>`;
 $('#findForm').addEventListener('submit',ev=>{ev.preventDefault();lookupFind()});
 document.querySelectorAll('[data-example]').forEach(b=>b.onclick=()=>{$('#findInput').value=b.dataset.example;lookupFind()});
 // Allow incoming shared search links from the same local server.
 const fromUrl=new URLSearchParams(window.location.search).get('find');
 if(fromUrl){$('#findInput').value=fromUrl.slice(0,300);lookupFind()}
}

async function showInventory(){
 $('#content').innerHTML=`<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Κατάλογος εξοπλισμού</h2><p class="panel-caption">Κάθε εγγραφή έχει μοναδικό QR και διατηρεί την αρχική της θέση.</p></div><div class="section-actions"><a class="btn btn-outline" href="/labels?type=items" target="_blank">▦ QR</a><a class="btn btn-primary" href="/export/inventory.xlsx">↓ Export Excel</a></div></div>
 <div class="filters"><div class="search-box"><input class="input" id="inventorySearch" placeholder="Αναζήτηση ονόματος ή AR-κωδικού" value="${e(state.filters.q)}"></div><select class="select" id="categoryFilter">${optionList(state.categories.map(x=>({id:x,label:x})),state.filters.category,'Όλες οι κατηγορίες')}</select><select class="select" id="locationFilter">${optionList(state.locations,state.filters.location,'Όλες οι θέσεις')}</select><label class="checkbox-inline"><input id="unknownFilter" type="checkbox" ${state.filters.unknown?'checked':''}> Για απογραφή</label></div>
 <div class="table-wrap"><table><thead><tr><th>Είδος</th><th>Κατηγορία</th><th>Απόθεμα</th><th>Σε χρήση</th><th>Αρχική θέση</th><th></th></tr></thead><tbody id="inventoryRows"></tbody></table></div><div class="list-caption" id="inventoryCount"></div></section>`;
 $('#inventorySearch').addEventListener('input',ev=>{state.filters.q=ev.target.value;clearTimeout(searchTimer);searchTimer=setTimeout(loadItems,180)});
 $('#categoryFilter').addEventListener('change',ev=>{state.filters.category=ev.target.value;loadItems()});
 $('#locationFilter').addEventListener('change',ev=>{state.filters.location=ev.target.value;loadItems()});
 $('#unknownFilter').addEventListener('change',ev=>{state.filters.unknown=ev.target.checked;loadItems()});
 $('#inventoryRows').addEventListener('click',ev=>{const btn=ev.target.closest('[data-open-item]');if(btn)openItem(btn.dataset.openItem)});
 await loadItems();
}
async function loadItems(){
 try{
  const p=new URLSearchParams();if(state.filters.q)p.set('q',state.filters.q);if(state.filters.category)p.set('category',state.filters.category);if(state.filters.location)p.set('location',state.filters.location);if(state.filters.unknown)p.set('unknown','1');
  const items=await req('/api/items?'+p.toString());state.items=items;
  if(state.view!=='inventory'||!$('#inventoryRows'))return;
  $('#inventoryRows').innerHTML=items.length?items.map(x=>`<tr>
   <td><span class="item-main">${e(x.name)}</span><span class="item-sku">${e(x.sku)}</span></td><td><span class="chip">${e(x.category)}</span></td>
   <td>${x.quantity_unknown?'<span class="unknown">Άγνωστο</span>':`<span class="qty-strong">${fmt(x.on_hand)}</span>`}</td>
   <td>${x.checked_out?`<span class="negative">${fmt(x.checked_out)}</span>`:'—'}</td><td><span class="loc-pill">${e(locLabel(x.default_location,true))}</span></td>
   <td><button class="text-button" data-open-item="${e(x.sku)}">Διαχείριση →</button></td></tr>`).join(''):'<tr><td colspan="6" class="table-empty">Δεν υπάρχουν καταχωρίσεις που να ταιριάζουν.</td></tr>';
  $('#inventoryCount').textContent=`${items.length} εγγραφές • Τα τεμάχια χωρίς επιβεβαιωμένη απογραφή εμφανίζονται ως «Άγνωστο».`;
 }catch(err){handleError(err)}
}
async function openItem(sku){
 try{
  const item=await req('/api/items/'+encodeURIComponent(sku));state.selected=item;
  $('#drawerOverlay').classList.remove('hidden');$('#drawerOverlay').setAttribute('aria-hidden','false');
  const rec=item.recommendation?.location_id;
  $('#drawerContent').innerHTML=`<div class="drawer-head"><div><div class="drawer-kicker">ΑΝΤΙΚΕΙΜΕΝΟ · ${e(item.sku)}</div><div style="font-size:11px;color:#90a2ae;margin-top:4px">Αρχική γραμμή Excel: ${item.source_row??'νέο είδος'}</div></div><button class="iconbutton" id="closeDrawer" aria-label="Κλείσιμο">✕</button></div>
   <div class="drawer-body"><h2 class="drawer-title">${e(item.name)}</h2><p class="drawer-sub">${e(item.notes||'Δεν υπάρχει περιγραφή.')}</p>
    <div class="item-details"><div class="mini-metric"><small>Στη ντουλάπα</small><b>${item.quantity_unknown?'?':fmt(item.on_hand)}</b></div><div class="mini-metric"><small>Εκτός</small><b>${fmt(item.checked_out)}</b></div><div class="mini-metric"><small>Θέσεις</small><b>${item.stocks.length}</b></div></div>
    <div class="category-chooser"><select class="select" id="itemCategory">${categoriesOptions(item.category)}</select><button class="btn btn-outline" id="saveCategory">Αλλαγή</button></div>
    <div class="section-header">ΦΩΤΟΓΡΑΦΙΕΣ ΑΝΑΦΟΡΑΣ</div>
    <div class="photo-reference">
      <div class="reference-strip">${item.photos.length?item.photos.map(x=>`<img src="${e(x.url)}" alt="Δείγμα ${e(item.name)}" loading="lazy">`).join(''):'<span class="helper">Δεν έχει προστεθεί φωτογραφία. Πρόσθεσε ένα δείγμα για οπτική αναζήτηση.</span>'}</div>
      <label class="btn btn-outline photo-upload-label">＋ Φωτογραφία του είδους<input id="itemPhotoInput" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden></label>
    </div>
    <div class="section-header">ΕΞΥΠΝΕΣ ΡΥΘΜΙΣΕΙΣ ΕΙΔΟΥΣ</div>
    <div class="field-row"><div class="field"><label>Όριο προειδοποίησης</label><input class="input" id="reorderPoint" type="number" min="0" max="100000" value="${item.reorder_point??0}"></div><div class="field"><label>Ημέρες αναπλήρωσης</label><input class="input" id="leadDays" type="number" min="1" max="365" value="${item.lead_days??14}"></div></div>
    <div class="field"><label>Κατηγορία μεγέθους (χειροκίνητη εκτίμηση)</label><select id="itemSize" class="select">${[['unknown','Άγνωστο'],['small','Μικρό'],['medium','Μεσαίο'],['large','Μεγάλο']].map(([v,t])=>`<option value="${v}" ${item.size_class===v?'selected':''}>${t}</option>`).join('')}</select></div>
    <button class="btn btn-outline" id="saveItemSmart">Αποθήκευση ορίου & μεγέθους</button>
    <div class="section-header">ΠΡΟΤΕΙΝΟΜΕΝΗ ΘΕΣΗ</div>
    <div class="suggestion"><span class="suggest-label">✦ Smart placement</span><strong>${rec?e(locLabel(rec)):'Επίλεξε νέα θέση'}</strong><small>${e(item.recommendation.reason)}<br>Η φυσική χωρητικότητα δεν έχει καταγραφεί. Εσύ επιβεβαιώνεις ότι το αντικείμενο μπήκε στη σωστή θέση.</small></div>
    ${item.smart_placement?.alternatives?.length?`<div class="v4-suggestions">${item.smart_placement.alternatives.slice(0,3).map(x=>`<div class="v4-suggestion"><b>${e(x.label)}</b><small>${e(x.reasons.join(' · '))}${x.capacity_units!=null?' · '+x.units+'/'+x.capacity_units+' δηλωμένες μονάδες':''}</small></div>`).join('')}</div>`:''}
    <div class="section-header">ΠΡΑΓΜΑΤΙΚΟ ΑΠΟΘΕΜΑ ΑΝΑ ΘΕΣΗ</div>
    <div>${item.stocks.length?item.stocks.map(x=>`<div class="stock-line"><span>${e(x.label)} <span class="loc-code">${e(x.location_id)}</span></span><b>${fmt(x.quantity)} τμχ.</b></div>`).join(''):'<p class="helper">Δεν υπάρχουν επιβεβαιωμένα τεμάχια μέσα στην αποθήκη.</p>'}</div>
    <div class="section-header">ΚΙΝΗΣΗ ΑΝΤΙΚΕΙΜΕΝΟΥ</div>
    ${item.quantity_unknown?'<div class="banner warn">Η ποσότητα είναι άγνωστη στο Excel. Ξεκίνα με «Απογραφή» για να ορίσεις τον πραγματικό αριθμό τεμαχίων.</div>':''}
    <div class="modes" id="moveModes"><button class="mode" data-mode="OUT">Αφαίρεση</button><button class="mode" data-mode="RETURN">Επιστροφή</button><button class="mode" data-mode="RECEIVE">Προσθήκη</button><button class="mode" data-mode="TRANSFER">Μεταφορά</button><button class="mode" data-mode="COUNT">Απογραφή</button></div>
    <form id="movementForm"><div id="moveFields"></div><div class="form-actions"><button class="btn btn-primary btn-full" type="submit">Επιβεβαίωση κίνησης →</button></div></form>
    <p class="helper">Σκάναρε ξανά το ίδιο QR για την επόμενη κίνηση. <a href="/labels?type=items&location=${encodeURIComponent(item.default_location||'')}" target="_blank">Ετικέτες QR</a></p>
   </div>`;
  $('#closeDrawer').onclick=closeDrawer;
  $('#itemPhotoInput').onchange=async ev=>{
   const file=ev.target.files?.[0];if(!file)return;
   try{const image=await photoData(file);await req('/api/photos','POST',{kind:'item',id:item.sku,image});notify('Η φωτογραφία προστέθηκε ως παράδειγμα αναγνώρισης.');await openItem(item.sku)}catch(err){handleError(err)}
  };
  $('#saveItemSmart').onclick=async()=>{try{await req('/api/item/settings','POST',{sku:item.sku,reorder_point:$('#reorderPoint').value,lead_days:$('#leadDays').value,size_class:$('#itemSize').value});notify('Οι έξυπνες ρυθμίσεις ενημερώθηκαν.');await openItem(sku)}catch(err){handleError(err)}};
  $('#saveCategory').onclick=async()=>{try{await req('/api/category','POST',{sku:item.sku,category:$('#itemCategory').value});notify('Η κατηγορία ενημερώθηκε.');await syncAll();await openItem(sku)}catch(err){handleError(err)}};
  $('#moveModes').addEventListener('click',ev=>{const b=ev.target.closest('[data-mode]');if(b)fillMovementForm(b.dataset.mode,item)});
  $('#movementForm').addEventListener('submit',async ev=>{ev.preventDefault();const f=ev.target;const data={sku:item.sku,action:f.dataset.mode,quantity:f.elements.quantity.value,holder:f.elements.holder?.value||'',from_location:f.elements.from_location?.value||'',to_location:f.elements.to_location?.value||'',issue_id:f.elements.issue_id?.value||null,project:f.elements.project?.value||'',due_date:f.elements.due_date?.value||'',note:f.elements.note?.value||''};
   const btn=f.querySelector('button[type=submit]');btn.disabled=true;
   try{await req('/api/movement','POST',data);notify('Η κίνηση καταχωρίστηκε επιτυχώς.');await syncAll();await openItem(item.sku)}catch(err){handleError(err)}finally{btn.disabled=false}
  });
  fillMovementForm(item.quantity_unknown?'COUNT':'OUT',item);
 }catch(err){handleError(err)}
}
function fillMovementForm(mode,item){
 document.querySelectorAll('.mode').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
 const form=$('#movementForm');form.dataset.mode=mode;
 const loc=item.stocks[0]?.location_id||item.default_location||'';
 const recommended=item.recommendation?.location_id||item.default_location||'';
 let fields='';
 if(mode==='OUT')fields+=`<div class="field"><label>Από ποια θέση το παίρνεις;</label><select class="select" name="from_location" required>${optionList(item.stocks.map(x=>({id:x.location_id,label:`${x.label} (${x.quantity} τμχ.)`})),loc)}</select></div><div class="field"><label>Ποιος το παίρνει;</label><input class="input" name="holder" required placeholder="Όνομα ή ομάδα"></div><div class="field-row"><div class="field"><label>Project</label><input class="input" name="project" placeholder="π.χ. Kalypso"></div><div class="field"><label>Επιστροφή έως</label><input class="input" name="due_date" type="date"></div></div>`;
 if(mode==='RETURN'){
   const issues=item.issues||[];
   fields+=`<div class="field"><label>Σε ποια εκκρεμή αφαίρεση ανήκει;</label><select class="select" name="issue_id" required>${issues.length?issues.map(x=>`<option value="${x.id}">${e(x.holder)} · ${x.quantity_open} τμχ. · #${x.id}</option>`).join(''):'<option value="">Δεν υπάρχουν εκκρεμείς αφαιρέσεις</option>'}</select></div>`;
 }
 if(mode==='TRANSFER')fields+=`<div class="field"><label>Από ποια θέση;</label><select class="select" name="from_location" required>${optionList(item.stocks.map(x=>({id:x.location_id,label:`${x.label} (${x.quantity} τμχ.)`})),loc)}</select></div>`;
 if(mode!=='OUT')fields+=`<div class="field"><label>${mode==='COUNT'?'Σε ποια θέση μέτρησες;':mode==='TRANSFER'?'Πού το μεταφέρεις;':'Πού το τοποθέτησες πραγματικά;'}</label><select class="select" name="to_location" required>${locationsOptions(recommended)}</select><div class="field-help">Μπορείς να επιλέξεις διαφορετική θέση από την προτεινόμενη.</div></div>`;
 fields+=`<div class="field"><label>${mode==='COUNT'?'Πόσα τεμάχια μέτρησες πραγματικά;':'Ποσότητα (τεμάχια)'}</label><input class="input" name="quantity" type="number" min="${mode==='COUNT'?'0':'1'}" step="1" ${mode==='COUNT'?'placeholder="Πληκτρολόγησε την πραγματική ποσότητα"':'value="1"'} required></div>`;
 fields+=`<div class="field"><label>Σημείωση (προαιρετική)</label><textarea class="textarea" name="note" rows="2" placeholder="π.χ. χρήση σε πείραμα ή παρατηρήσεις"></textarea></div>`;
 $('#moveFields').innerHTML=fields;
 const submit=form.querySelector('[type=submit]');submit.disabled=mode==='RETURN'&&!item.issues.length;
}
function closeDrawer(){$('#drawerOverlay').classList.add('hidden');$('#drawerOverlay').setAttribute('aria-hidden','true');state.selected=null}
async function syncAll(){await Promise.all([refreshLocations(),refreshStats()]);if(state.view==='inventory')await loadItems();if(state.view==='locations')await showLocations();if(state.view==='history')await showHistory();if(state.view==='loans')await showLoans();if(state.view==='alerts')await showAlerts()}

async function showLocations(){
 $('#content').innerHTML=`<div class="banner">Οι κωδικοί <b>C05-S04</b> διαβάζονται προσωρινά ως «Ντουλάπα 5 · Θέση 4». Αυτή είναι παραδοχή βάσει του μορφότυπου του Excel και πρέπει να ελεγχθεί στο εργαστήριο.</div>
 <div class="panel-header" style="border:0;padding:8px 0 0"><div><h2 class="panel-title">${state.locations.filter(x=>x.id!=='C99-S00').length} κωδικοί θέσεων + χώρος προς τακτοποίηση</h2><p class="panel-caption">Τα QR θέσεων ανοίγουν τη λίστα των αντικειμένων της θέσης.</p></div><div class="section-actions"><a class="btn btn-outline" target="_blank" href="/labels?type=locations">▦ QR θέσεων</a><button class="btn btn-primary" id="addLocationBtn">+ Νέα θέση</button></div></div>
 <section class="v4-twin-panel"><div class="panel-header"><h2 class="panel-title">Ψηφιακό δίδυμο ντουλαπών</h2><p class="panel-caption">Άνοιξε μια ντουλάπα και πάτησε πάνω σε ένα ράφι για να δεις τι περιέχει και να δηλώσεις χωρητικότητα.</p></div><div id="cabinetDigitalTwin"></div></section>
 <div class="cabinet-grid">${state.locations.map(l=>`<div class="location-visual-card"><button class="location-card" data-location="${e(l.id)}">${l.photo_url?`<img class="location-photo" src="${e(l.photo_url)}?v=${Date.now()}" alt="Φωτογραφία θέσης ${e(l.id)}">`:'<div class="location-photo-placeholder">▤</div>'}<div class="location-top"><span class="location-icon">▤</span><span class="loc-code">${e(l.id)}</span></div><div class="location-name">${e(l.label)}</div><div class="location-meta">${fmt(l.item_types)} είδη · ${fmt(l.units)} γνωστά τεμάχια</div><div class="location-cat">${e(l.dominant_category||'Χωρίς καταμετρημένα τεμάχια')}</div></button><label class="location-photo-btn">📷 Φωτογραφία θέσης<input type="file" data-photo-location="${e(l.id)}" accept="image/jpeg,image/png,image/webp" capture="environment" hidden></label></div>`).join('')}</div>`;
 showCabinetTwin();
 $('#addLocationBtn').onclick=showNewLocation;
 document.querySelectorAll('[data-location]').forEach(el=>el.addEventListener('click',()=>{state.filters.location=el.dataset.location;state.filters.q='';state.filters.category='';state.filters.unknown=false;setView('inventory')}));
 document.querySelectorAll('[data-photo-location]').forEach(el=>el.addEventListener('change',async ev=>{
  const file=ev.target.files?.[0];if(!file)return;
  try{await req('/api/photos','POST',{kind:'location',id:el.dataset.photoLocation,image:await photoData(file)});notify('Η φωτογραφία της θέσης καταχωρίστηκε.');await refreshLocations();showLocations()}catch(err){handleError(err)}
 }));
}
const actionNames={OUT:'Αφαίρεση',RETURN:'Επιστροφή',RECEIVE:'Προσθήκη',TRANSFER:'Μεταφορά',COUNT:'Απογραφή'};
async function showHistory(){
 try{const rows=await req('/api/history?limit=100');
 $('#content').innerHTML=`<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Πρόσφατες κινήσεις</h2><p class="panel-caption">Εμφανίζονται έως 100 πρόσφατες κινήσεις. Δεν επινοούνται ιστορικές κινήσεις από το αρχικό Excel.</p></div><a class="btn btn-outline" href="/export/history.csv">↓ CSV</a></div>
 <div class="table-wrap"><table class="history-table"><thead><tr><th>Ημερομηνία</th><th>Είδος</th><th>Κίνηση</th><th>Ποσότητα</th><th>Από → Σε</th><th>Χρήστης</th></tr></thead><tbody>${rows.length?rows.map(x=>`<tr><td>${e(new Date(x.ts).toLocaleString('el-GR'))}</td><td><button class="text-button" data-open="${e(x.sku)}">${e(x.name)}</button><div class="item-sku">${e(x.sku)}</div></td><td><span class="activity ${e(x.action)}">${actionNames[x.action]||e(x.action)}</span></td><td><b>${fmt(x.quantity)}</b></td><td>${e(x.from_location||'—')} → ${e(x.to_location||'—')}</td><td>${e(x.holder||'—')}</td></tr>`).join(''):'<tr><td colspan="6" class="table-empty">Δεν έχει καταχωριστεί καμία κίνηση ακόμη.</td></tr>'}</tbody></table></div></section>`;
 document.querySelectorAll('[data-open]').forEach(el=>el.onclick=()=>openItem(el.dataset.open));
 }catch(err){handleError(err)}
}
async function showSettings(){
 try{const config=await req('/api/settings');
 const displayUrl=config.public_base_url||config.computed_base;
 const ai=await req('/api/ai/status');
 $('#content').innerHTML=`<div class="settings-cols"><section class="panel settings-section"><h3>QR από κινητό</h3><p>Για να ανοίγουν τα QR μέσω της κάμερας του κινητού, οι συσκευές πρέπει να είναι στο ίδιο Wi-Fi και ο QR σύνδεσμος να περιέχει τη σωστή διεύθυνση IP του υπολογιστή/server.</p>
 <div class="settings-row"><label>Δημόσια διεύθυνση στο τοπικό δίκτυο</label><input id="baseUrl" class="input" placeholder="http://192.168.1.20:8989" value="${e(config.public_base_url||'')}"><small class="field-help">Μόνο διεύθυνση server χωρίς /i/ ή /l/. Αν την αλλάξεις, τύπωσε ξανά τις ετικέτες.</small></div>
 <div class="settings-url">Τρέχουσα διεύθυνση QR: <b>${e(displayUrl)}</b></div><div class="setting-actions"><button class="btn btn-primary" id="saveUrl">Αποθήκευση διεύθυνσης</button></div>
 <div class="divider"></div><h3>✦ Gemini AI</h3><p>Αναγνώριση φωτογραφίας με το δικό σου API key. Το κλειδί παραμένει στο .env του server, δεν αποστέλλεται ποτέ στη σελίδα.</p>
 <div class="settings-url">Κατάσταση: <b>${ai.configured?'● Συνδεδεμένο (ρυθμισμένο)':'○ Δεν έχει ρυθμιστεί'}</b> · Μοντέλο: <code>${e(ai.model)}</code></div>
 <div class="setting-actions"><button class="btn btn-outline" id="testGemini" ${ai.configured?'':'disabled'}>✦ Έλεγχος σύνδεσης Gemini</button></div>
 <small class="field-help">Πρόσθεσε GEMINI_API_KEY στο αρχείο .env και κάνε επανεκκίνηση. Ο έλεγχος κάνει ένα μικρό αίτημα API και ενδέχεται να καταναλώσει quota.</small>
 <div class="divider"></div><h3>Κανόνες θέσεων</h3><p>Η αντιστοίχιση <b>5.4 → Ντουλάπα 5 · Θέση 4</b> αποτελεί υπόθεση. Δεν υπάρχουν διαστάσεις ή πραγματικές χωρητικότητες στο αρχικό αρχείο. Το σύστημα προτείνει θέσεις με βάση την υφιστάμενη αποθήκευση και την κατηγορία, όχι βάσει φυσικής χωρητικότητας.</p></section>
 <section class="panel settings-section"><h3>Εκτύπωση & αντίγραφα</h3><p>Εκτύπωσε τις ετικέτες σε αυτοκόλλητο χαρτί Α4. Κάθε QR αντικειμένου οδηγεί στις επιλογές «Αφαίρεση / Επιστροφή / Προσθήκη».</p>
 <div class="setting-actions"><a target="_blank" class="btn btn-primary" href="/labels?type=items">▦ QR αντικειμένων</a><a target="_blank" class="btn btn-outline" href="/labels?type=locations">▤ QR θέσεων</a></div>
 <div class="divider"></div><h3>Εξαγωγή δεδομένων</h3><p>Κατέβασε ενημερωμένο Excel με 8 φύλλα, μαζί με την αναλυτική κατάσταση ανά θέση, κινήσεις και δανεισμούς. Διατίθεται και CSV. Για πλήρες αντίγραφο δεδομένων αντέγραψε, ενώ ο server είναι κλειστός, το αρχείο <code>data/inventory.db</code>.</p>
 <div class="setting-actions"><a class="btn btn-primary" href="/export/inventory.xlsx">↓ Export Excel (.xlsx)</a><a class="btn btn-outline" href="/export/inventory.csv">↓ Κατάλογος CSV</a><a class="btn btn-outline" href="/export/history.csv">↓ Κινήσεις CSV</a></div>
 <div class="divider"></div><h3>Ασφάλεια πρόσβασης</h3><p>Η εφαρμογή απαιτεί σύνδεση και διαθέτει ρόλους. Για δημόσια χρήση απαιτούνται HTTPS, ασφαλής server, ενημερώσεις και έλεγχος ασφάλειας. Μην ανοίξεις απευθείας τη θύρα 8989 στο Internet.</p><button id="changePasswordSettings" class="btn btn-outline">Αλλαγή κωδικού πρόσβασης</button></section></div>`;
 $('#changePasswordSettings').onclick=showPasswordChange;
 $('#saveUrl').onclick=async()=>{try{await req('/api/settings','POST',{public_base_url:$('#baseUrl').value});notify('Η διεύθυνση των QR ενημερώθηκε.');showSettings()}catch(err){handleError(err)}};
 $('#testGemini').onclick=async()=>{const b=$('#testGemini');b.disabled=true;b.textContent='Γίνεται έλεγχος…';try{const r=await req('/api/ai/test','POST',{});notify(r.ok?'Επιτυχής σύνδεση Gemini ('+r.model+').':'Το Gemini απάντησε, αλλά όχι με το αναμενόμενο OK.',!r.ok)}catch(err){handleError(err)}finally{b.disabled=false;b.textContent='✦ Έλεγχος σύνδεσης Gemini'}};
 }catch(err){handleError(err)}
}
function showModal(head,htmlBody,onSubmit){
 $('#modalOverlay').classList.remove('hidden');$('#modalOverlay').setAttribute('aria-hidden','false');
 $('#modalContent').innerHTML=`<div class="modal-head"><h2>${e(head)}</h2><button id="closeModal" class="iconbutton">✕</button></div><form id="popupForm"><div class="modal-body">${htmlBody}</div><div class="modal-footer"><button class="btn btn-primary" type="submit">Αποθήκευση →</button></div></form>`;
 $('#closeModal').onclick=closeModal;
 $('#popupForm').onsubmit=async ev=>{ev.preventDefault();try{await onSubmit(new FormData(ev.target));closeModal();await syncAll()}catch(err){handleError(err)}};
}
function closeModal(){$('#modalOverlay').classList.add('hidden');$('#modalOverlay').setAttribute('aria-hidden','true')}
function showNewItem(){
 showModal('Καταχώριση νέου είδους',`<div class="field"><label>Όνομα είδους</label><input name="name" class="input" required placeholder="π.χ. Raspberry Pi Zero 2 W"></div>
 <div class="field"><label>Κατηγορία</label><select class="select" name="category">${categoriesOptions('Λοιπά')}</select></div>
 <div class="field-row"><div class="field"><label>Αρχική ποσότητα</label><input class="input" name="quantity" type="number" min="0" step="1" placeholder="Άγνωστη"></div><div class="field"><label>Θέση</label><select class="select" name="location_id">${locationsOptions('')}</select></div></div>
 <div class="field"><label>Σημειώσεις</label><textarea class="textarea" rows="3" name="notes"></textarea></div><div class="banner">Αν δεν γνωρίζεις την ποσότητα, άφησέ την κενή και κάνε απογραφή αργότερα.</div>`,async f=>{
  const result=await req('/api/items','POST',Object.fromEntries(f.entries()));notify('Το αντικείμενο δημιουργήθηκε: '+result.sku);setTimeout(()=>openItem(result.sku),250);
 });
}
function showNewLocation(){
 showModal('Νέα θέση / ντουλάπα',`<div class="field-row"><div class="field"><label>Αριθμός ντουλάπας</label><input name="cabinet" class="input" type="number" min="1" max="99" required placeholder="π.χ. 8"></div><div class="field"><label>Αριθμός θέσης</label><input name="slot" class="input" type="number" min="1" max="99" required placeholder="π.χ. 1"></div></div><div class="field"><label>Περιγραφή (προαιρετική)</label><input name="label" class="input" placeholder="π.χ. Ντουλάπα 8 · Συρτάρι 1"></div>`,async f=>{await req('/api/locations','POST',Object.fromEntries(f.entries()));notify('Η νέα θέση προστέθηκε.');});
}
function photoData(file){
 return new Promise((resolve,reject)=>{
  if(!file||file.size>5_000_000)return reject(new Error('Επίλεξε φωτογραφία μέχρι 5 MB.'));
  if(!['image/jpeg','image/png','image/webp'].includes(file.type))return reject(new Error('Επίλεξε αρχείο JPG, PNG ή WebP.'));
  const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Δεν ήταν δυνατή η ανάγνωση της φωτογραφίας.'));reader.readAsDataURL(file);
 });
}
function showPhotoSearch(){
 closeDrawer();
 $('#modalOverlay').classList.remove('hidden');$('#modalOverlay').setAttribute('aria-hidden','false');
 $('#modalContent').innerHTML=`<div class="modal-head"><h2>◎ Βρες αντικείμενο με φωτογραφία</h2><button class="iconbutton" id="closePhotoSearch">✕</button></div>
 <div class="modal-body">
  <p class="helper"><b>Gemini AI:</b> Φωτογράφισε ένα εξάρτημα και δες προτάσεις από τις πραγματικές εγγραφές του Excel. Επιβεβαίωσε πριν αλλάξει το απόθεμα. Η φωτογραφία αποστέλλεται στο Google Gemini μόνο αν έχεις ρυθμίσει API key.</p>
  <label class="photo-drop">📷 Φωτογραφία από κινητό ή υπολογιστή<input id="searchPhoto" type="file" accept="image/jpeg,image/png,image/webp" capture="environment"></label>
  <div id="photoPreview"></div>
  <button id="matchPhoto" class="btn btn-primary btn-full" disabled>✦ Αναγνώριση με Gemini →</button>
  <div id="photoResults" class="photo-results"></div>
  <div class="divider"></div><div class="field"><label>Ή βρες το από το όνομα/τύπο</label><input id="photoNameSearch" class="input" placeholder="π.χ. Arduino, HC-SR04, servo"></div>
  <div id="photoTextResults"></div>
 </div>`;
 $('#closePhotoSearch').onclick=closeModal;
 let image=null;
 $('#searchPhoto').onchange=async ev=>{
  const f=ev.target.files?.[0];if(!f)return;
  try{image=await photoData(f);$('#photoPreview').innerHTML=`<img class="query-photo" alt="Η φωτογραφία σου" src="${image}">`;$('#matchPhoto').disabled=false;$('#photoResults').innerHTML='';}catch(err){handleError(err)}
 };
 $('#matchPhoto').onclick=async()=>{
  if(!image)return;
  const btn=$('#matchPhoto');btn.disabled=true;btn.textContent='Αναλύεται η φωτογραφία…';
  try{
   const res=await req('/api/vision/search','POST',{image});
   const top=res.results;
   const g=res.gemini;
   const confidence={high:'Υψηλή εκτίμηση',medium:'Μέτρια εκτίμηση',low:'Χαμηλή εκτίμηση'};
   let output='';
   if(g){
    output+=`<div class="ai-card"><div class="ai-card-head"><span>✦ GEMINI AI</span><small>${e(g.model)}</small></div><p><b>Τι βλέπει:</b> ${e(g.description||'Δεν αναγνωρίστηκε με βεβαιότητα.')}</p>${g.markings?`<p class="helper">Ορατές σημάνσεις: ${e(g.markings)}</p>`:''}${g.uncertain?'<div class="banner warn">Η αναγνώριση έχει αβεβαιότητα. Έλεγξε με προσοχή το μοντέλο και τις σημάνσεις.</div>':''}</div>`;
    output+='<h3>Υποψήφια είδη από το Excel</h3>';
    output+=(g.candidates||[]).length?g.candidates.map(x=>`<button class="photo-result" data-ai-choice="${e(x.sku)}"><span><b>${e(x.name)}</b><small>${e(x.category)} · ${e(x.sku)}</small><small>${e(confidence[x.confidence]||confidence.low)} · ${e(x.default_location?locLabel(x.default_location):'Άγνωστη θέση')}</small><small>${e(x.reason)}</small></span><span>→</span></button>`).join(''):'<div class="banner warn">Δεν βρέθηκε αρκετά αξιόπιστη αντιστοίχιση με το Excel. Αναζήτησε χειροκίνητα το είδος.</div>';
   }else if(res.gemini_warning){
    output+=`<div class="banner warn">Gemini: ${e(res.gemini_warning)}<br>Μπορείς να χρησιμοποιήσεις την αναζήτηση ονόματος και φωτογραφιών αναφοράς.</div>`;
   }else if(!res.ai_configured){
    output+='<div class="banner">Για αυτόματη αναγνώριση συμπλήρωσε το GEMINI_API_KEY στο αρχείο .env και επανεκκίνησε τον server. Μέχρι τότε λειτουργεί η αναζήτηση με δείγματα φωτογραφιών.</div>';
   }
   if(top.length){
    output+='<div class="divider"></div><h3>Οπτικά παρόμοιες αποθηκευμένες φωτογραφίες</h3>';
    output+=top.map(x=>`<button class="photo-result" data-choice="${e(x.sku)}"><img src="${e(x.photo_url)}" alt=""><span><b>${e(x.name)}</b><small>${e(x.category)} · ${e(x.sku)}</small><small>Οπτική ομοιότητα: ${x.similarity}% (όχι πιθανότητα ταύτισης)</small></span><span>→</span></button>`).join('');
   }
   $('#photoResults').innerHTML=output||'<div class="banner">Δεν βρέθηκαν αντιστοιχίσεις. Δοκίμασε αναζήτηση με όνομα.</div>';
   if(res.ai_description || res.ai_warning){
    const aiCandidates=(res.ai_candidates||[]).map(x=>`<button class="photo-result" data-ai-choice="${e(x.sku)}"><span><b>${e(x.name)}</b><small>${e(x.category)} · ${e(x.sku)} · σχετικότητα ονόματος ${x.text_relevance}%</small></span><span>→</span></button>`).join('');
    $('#photoResults').innerHTML+=`<div class="divider"></div><h3>Τοπικό μοντέλο όρασης (προαιρετικό)</h3>${res.ai_description?`<p class="helper">Περιγραφή μοντέλου: ${e(res.ai_description)}</p>`:''}${res.ai_warning?`<p class="banner warn">${e(res.ai_warning)}</p>`:''}${aiCandidates||'<p class="helper">Δεν προέκυψε επαρκώς σχετική καταχώριση από την περιγραφή. Δοκίμασε την αναζήτηση ονόματος.</p>'}`;
   }
   document.querySelectorAll('[data-choice], [data-ai-choice]').forEach(b=>b.onclick=()=>{closeModal();openItem(b.dataset.choice||b.dataset.aiChoice)});
  }catch(err){handleError(err)}finally{btn.disabled=false;btn.textContent='✦ Αναγνώριση με Gemini →'}
 };
 let t=null;
 $('#photoNameSearch').oninput=ev=>{clearTimeout(t);const q=ev.target.value.trim();t=setTimeout(async()=>{
  if(!q){$('#photoTextResults').innerHTML='';return}
  try{const items=await req('/api/items?'+new URLSearchParams({q}));$('#photoTextResults').innerHTML=items.slice(0,8).map(x=>`<button class="photo-result" data-text-choice="${e(x.sku)}"><span><b>${e(x.name)}</b><small>${e(x.sku)} · ${e(x.category)}</small></span><span>→</span></button>`).join('')||'<p class="helper">Καμία αντιστοίχιση.</p>';document.querySelectorAll('[data-text-choice]').forEach(b=>b.onclick=()=>{closeModal();openItem(b.dataset.textChoice)})}catch(err){handleError(err)}
  },200)};
}
function parseScan(value){
 const raw=value.trim();let path=raw;
 try{if(/^https?:\/\//i.test(raw))path=new URL(raw).pathname}catch(_){throw new Error('Το QR URL δεν είναι έγκυρο.')}
 const item=path.match(/(?:^|\/)i\/(AR-\d+)\/?$/i)||path.match(/^(AR-\d+)$/i);
 if(item){closeScan();openItem(item[1].toUpperCase());return}
 const loc=path.match(/(?:^|\/)l\/(C\d{2}-S\d{2})\/?$/i)||path.match(/^(C\d{2}-S\d{2})$/i);
 if(loc){closeScan();state.filters.location=loc[1].toUpperCase();state.filters.q='';state.filters.category='';state.filters.unknown=false;setView('inventory');notify('Φιλτράρισμα θέσης: '+loc[1]);return}
 throw new Error('Δεν αναγνωρίστηκε QR της αποθήκης.');
}
async function startScan(){
 $('#scanOverlay').classList.remove('hidden');$('#scanOverlay').setAttribute('aria-hidden','false');
 $('#scannerHint').textContent='Σκάναρε το QR μέσα στο πλαίσιο.';
 if(!navigator.mediaDevices?.getUserMedia || !window.BarcodeDetector){
  $('#scannerHint').textContent='Η ενσωματωμένη κάμερα δεν υποστηρίζεται σε αυτό το περιβάλλον. Άνοιξε το QR με την κανονική κάμερα του κινητού ή γράψε τον κωδικό παρακάτω.';
  return;
 }
 try{
  const supported=await BarcodeDetector.getSupportedFormats();
  if(!supported.includes('qr_code'))throw new Error('Το QR δεν υποστηρίζεται εδώ.');
  state.scanStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
  const video=$('#cameraVideo');video.srcObject=state.scanStream;await video.play();
  state.scanActive=true;const detector=new BarcodeDetector({formats:['qr_code']});
  const loop=async()=>{
   if(!state.scanActive)return;
   try{const codes=await detector.detect(video);if(codes.length){parseScan(codes[0].rawValue);return}}catch(err){if(state.scanActive)console.debug(err)}
   if(state.scanActive)setTimeout(loop,250);
  };loop();
 }catch(err){$('#scannerHint').textContent='Δεν είναι διαθέσιμη η κάμερα. Στο τοπικό HTTP μπορεί να μπλοκάρεται· χρησιμοποίησε την κανονική κάμερα του κινητού για το QR, ή εισήγαγε τον κωδικό.';console.debug(err)}
}
function closeScan(){state.scanActive=false;if(state.scanStream){state.scanStream.getTracks().forEach(t=>t.stop());state.scanStream=null}$('#cameraVideo').srcObject=null;$('#scanOverlay').classList.add('hidden');$('#scanOverlay').setAttribute('aria-hidden','true')}
async function boot(){
 try{state.auth=await req('/api/auth/me');}catch(_){location.replace('/login');return;}
 if(!state.auth.authenticated){location.replace('/login');return;}
 $('#accountName').textContent=state.auth.display_name;
 $('#accountRole').textContent={admin:'Διαχειριστής',member:'Μέλος εργαστηρίου',viewer:'Μόνο προβολή'}[state.auth.role];
 if(state.auth.role==='admin')$('#usersNav').hidden=false;
 if(state.auth.role==='viewer')document.body.classList.add('view-only');
 const doLogout=async()=>{try{await req('/api/auth/logout','POST',{})}catch(_){ }location.replace('/login')};
 $('#logoutButton').onclick=doLogout;$('#logoutTopButton').onclick=doLogout;
 $('#changeMyPassword').onclick=showPasswordChange;
 $('#nav').addEventListener('click',ev=>{const link=ev.target.closest('[data-view]');if(link)setView(link.dataset.view)});
 $('#addItemBtn').onclick=showNewItem;$('#photoSearchBtn').onclick=showPhotoSearch;$('#scanBtn').onclick=startScan;$('#stopScanBtn').onclick=closeScan;
 $('#manualQrBtn').onclick=()=>{try{parseScan($('#manualQr').value)}catch(err){handleError(err)}};
 $('#manualQr').onkeydown=ev=>{if(ev.key==='Enter')$('#manualQrBtn').click()};
 $('#drawerOverlay').addEventListener('click',ev=>{if(ev.target.id==='drawerOverlay')closeDrawer()});
 $('#modalOverlay').addEventListener('click',ev=>{if(ev.target.id==='modalOverlay')closeModal()});
 document.addEventListener('keydown',ev=>{if(ev.key==='Escape'){closeDrawer();closeModal();closeScan()}});
 try{
  await Promise.all([refreshLocations(),refreshStats()]);setView('find');
  const route=decodeURIComponent(location.pathname);
  const item=route.match(/^\/i\/(AR-\d+)$/i);
  const loc=route.match(/^\/l\/(C\d{2}-S\d{2})$/i);
  if(item)openItem(item[1].toUpperCase());
  if(loc){state.filters.location=loc[1].toUpperCase();setView('inventory')}
 }catch(err){$('#content').innerHTML='<div class="banner warn">Αδυναμία σύνδεσης με τον τοπικό server. Έλεγξε ότι εκτελείται το server.py.</div>';handleError(err)}
}
window.addEventListener('DOMContentLoaded',boot);

function showPasswordChange(){
 showModal('Αλλαγή προσωπικού κωδικού',`<div class="field"><label>Τρέχων κωδικός</label><input type="password" name="old" class="input" autocomplete="current-password" required></div><div class="field"><label>Νέος κωδικός (12+ χαρακτήρες)</label><input type="password" name="fresh" class="input" minlength="12" autocomplete="new-password" required></div>`,async f=>{
  await req('/api/auth/password','POST',{current_password:f.get('old'),new_password:f.get('fresh')});location.replace('/login');
 });
}
async function showUsers(){
 if(state.auth?.role!=='admin')return;
 try{
  const data=await req('/api/auth/users');if(state.view!=='users')return;
  $('#content').innerHTML=`<section class="panel"><div class="panel-header"><div><h2>Λογαριασμοί εργαστηρίου</h2><p>Μη χρησιμοποιείς κωδικούς WordPress. Δημιούργησε ξεχωριστούς λογαριασμούς.</p></div><button class="btn btn-primary" id="createUserBtn">+ Νέος χρήστης</button></div>
  <div class="table-scroll"><table><thead><tr><th>Όνομα</th><th>Username</th><th>Ρόλος</th><th>Κατάσταση</th><th>Διαχείριση</th></tr></thead><tbody>${data.users.map(u=>`<tr><td>${e(u.display_name)}</td><td>${e(u.username)}</td><td>${e({admin:'Διαχειριστής',member:'Μέλος',viewer:'Μόνο προβολή'}[u.role])}</td><td>${u.active?'Ενεργός':'Ανενεργός'}</td><td><button class="btn btn-outline" data-edit-user="${u.id}">Επεξεργασία</button></td></tr>`).join('')}</tbody></table></div></section>`;
  $('#createUserBtn').onclick=()=>showModal('Δημιουργία χρήστη',`<div class="field"><label>Username (λατινικά)</label><input name="username" class="input" required minlength="3" maxlength="40"></div><div class="field"><label>Όνομα εμφάνισης</label><input name="display_name" class="input" required></div><div class="field"><label>Ρόλος</label><select name="role" class="select"><option value="member">Μέλος εργαστηρίου</option><option value="viewer">Μόνο προβολή</option><option value="admin">Διαχειριστής</option></select></div><div class="field"><label>Προσωρινός κωδικός (12+ χαρακτήρες)</label><input name="password" type="password" minlength="12" class="input" required autocomplete="new-password"></div>`,async f=>{await req('/api/auth/users','POST',Object.fromEntries(f.entries()));notify('Ο λογαριασμός δημιουργήθηκε.');showUsers()});
  $('#content').querySelectorAll('[data-edit-user]').forEach(b=>b.onclick=()=>{
   const u=data.users.find(x=>x.id===Number(b.dataset.editUser));
   showModal('Διαχείριση: '+u.username,`<div class="field"><label>Ρόλος</label><select name="role" class="select">${[['admin','Διαχειριστής'],['member','Μέλος εργαστηρίου'],['viewer','Μόνο προβολή']].map(([v,t])=>`<option value="${v}" ${u.role===v?'selected':''}>${t}</option>`).join('')}</select></div><div class="field"><label>Κατάσταση</label><select name="active" class="select"><option value="1" ${u.active?'selected':''}>Ενεργός</option><option value="0" ${!u.active?'selected':''}>Ανενεργός</option></select></div><div class="field"><label>Νέος κωδικός (άφησέ τον κενό αν δεν αλλάζει)</label><input name="password" type="password" class="input" minlength="12" autocomplete="new-password"></div><div class="banner">Η αλλαγή ρόλου ή κωδικού αποσυνδέει τις υπάρχουσες συνεδρίες του χρήστη.</div>`,async f=>{
    const request={role:f.get('role'),active:f.get('active')==='1'};if(f.get('password'))request.password=f.get('password');
    await req('/api/auth/users/'+u.id,'POST',request);notify('Ο χρήστης ενημερώθηκε.');showUsers();
   });
  });
 }catch(err){handleError(err)}
}
