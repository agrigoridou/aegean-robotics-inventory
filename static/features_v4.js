/* Aegean Robotics v4 – dedicated workflows built on same SQLite API */
const v4Note=`<p class="v4-hint">Τα δεδομένα προέρχονται από τις εγγραφές του αποθέματος. Η φυσική παρουσία και οι ποσότητες επαληθεύονται μόνο με καταμέτρηση.</p>`;
async function showAudit(){
 const places=state.locations.filter(x=>x.id!=='C99-S00');
 $('#content').innerHTML=`<section class="panel"><div class="panel-header"><div><h2 class="panel-title">◉ AI απογραφή με φωτογραφία</h2><p class="panel-caption">Φωτογράφισε ένα ράφι και σύγκρινε τις ορατές ενδείξεις με τις καταχωρίσεις.</p></div></div><div class="v4-pad">
 <div class="banner warn"><b>Απαραίτητος φυσικός έλεγχος:</b> Το Gemini μπορεί να μπερδέψει αισθητήρες, να μη δει κρυμμένα τεμάχια και να μετρήσει λάθος. Καμία φωτογραφία δεν αλλάζει το απόθεμα αυτομάτως.</div>
 <div class="field"><label>Επιλογή πραγματικού ραφιού</label><select class="select" id="auditLocation">${optionList(places,'','Διάλεξε θέση')}</select></div>
 <label class="photo-drop">📷 Φωτογραφία ραφιού (έως 5 MB)<input type="file" id="auditPhoto" accept="image/jpeg,image/png,image/webp" capture="environment"></label><div id="auditPreview"></div>
 <button class="btn btn-primary" id="runAudit">✦ Ανάλυση φωτογραφίας με Gemini</button><div id="auditOutput"></div>
 </div></section><section class="panel v4-section"><div class="panel-header"><h2 class="panel-title">Προηγούμενες φωτογραφικές απογραφές</h2></div><div class="v4-pad" id="auditHistory">Φόρτωση…</div></section>`;
 let image=null;
 $('#auditPhoto').onchange=async ev=>{try{image=await photoData(ev.target.files?.[0]);$('#auditPreview').innerHTML=`<img class="query-photo" src="${image}" alt="Φωτογραφία ραφιού">`}catch(err){handleError(err)}};
 $('#runAudit').onclick=async()=>{
   if(!$('#auditLocation').value||!image){notify('Επίλεξε πρώτα ράφι και φωτογραφία.',true);return}
   let button=$('#runAudit');button.disabled=true;button.textContent='Το Gemini εξετάζει το ράφι…';
   try{const data=await req('/api/audit/shelf','POST',{location_id:$('#auditLocation').value,image});renderAuditResult(data);await renderAuditHistory()}
   catch(err){handleError(err);$('#auditOutput').innerHTML=`<div class="banner warn">${e(err.message)}</div>`}
   finally{button.disabled=false;button.textContent='✦ Ανάλυση φωτογραφίας με Gemini'}
 };
 await renderAuditHistory();
}
function renderAuditResult(r){
 const obs=r.observations||[];
 $('#auditOutput').innerHTML=`<div class="v4-audit-result"><h3>Απογραφή #${fmt(r.id)} · ${e(r.location_id)}</h3><p>${e(r.summary)}</p><p class="helper">${e(r.warning)}</p>
 ${r.ambiguities?.length?`<div class="banner warn">Αβεβαιότητες: ${r.ambiguities.map(e).join(' · ')}</div>`:''}
 ${obs.length?obs.map((x,i)=>`<div class="v4-audit-row" data-auditrow="${i}"><div><b>${e(x.name)}</b><small>${e(x.sku)} · Βεβαιότητα AI: ${e(x.confidence)} · Καταγεγραμμένα σε αυτό το ράφι: ${x.recorded_quantity}${x.quantity_unknown?' (άγνωστο υπόλοιπο)':''}</small><small>${e(x.reason)}</small><small>Ορατά τεμάχια (εκτίμηση AI): ${x.visible_count==null?'άγνωστα':fmt(x.visible_count)} — όχι απαραίτητα συνολικό απόθεμα.</small></div>
 <div class="v4-verify"><label>Πραγματική μέτρηση <input class="input" data-count="${i}" type="number" min="0" step="1" placeholder="Μέτρησα…"></label><button class="btn btn-outline" data-confirm="${i}">✓ Επιβεβαίωση</button></div></div>`).join(''):'<div class="banner">Δεν αναγνωρίστηκε με επαρκή βεβαιότητα κάποια καταχώριση. Μπορείς να απογράψεις χειροκίνητα από την Αποθήκη.</div>'}
 <div class="v4-hint">Η απογραφή με COUNT ενημερώνει την ποσότητα του συγκεκριμένου SKU στη συγκεκριμένη θέση μόνο — δεν αλλάζει άλλες θέσεις.</div></div>`;
 $('#auditOutput').querySelectorAll('[data-confirm]').forEach(btn=>btn.onclick=async()=>{
    const i=Number(btn.dataset.confirm),x=obs[i],field=$(`[data-count="${i}"]`),value=field.value;
    if(!/^\d+$/.test(value)){notify('Πληκτρολόγησε πρώτα τη φυσική καταμέτρηση.',true);return}
    if(!window.confirm(`Επιβεβαίωση: μέτρησες πραγματικά ${value} τεμάχια του ${x.name} στο ${r.location_id};`))return;
    btn.disabled=true;
    try{await req('/api/audit/confirm','POST',{audit_id:r.id,sku:x.sku,quantity:Number(value)});btn.textContent='✓ Αποθηκεύτηκε';notify('Η φυσική καταμέτρηση καταχωρίστηκε.');await Promise.all([refreshLocations(),refreshStats()]);await renderAuditHistory()}
    catch(err){handleError(err);btn.disabled=false}
 });
}
async function renderAuditHistory(){
 try{const history=await req('/api/audits');const target=$('#auditHistory');if(!target)return;
 target.innerHTML=history.length?history.map(a=>`<div class="v4-audit-history"><img src="${e(a.photo_url)}" alt="Ράφι" loading="lazy"><div><b>Απογραφή #${a.id} · ${e(locLabel(a.location_id))}</b><small>${e(new Date(a.created_at).toLocaleString('el-GR'))} · ${e(a.model)}</small><small>${(a.report.observations||[]).length} προτάσεις · ${a.confirmed.length} καταχωρισμένες μετρήσεις</small></div></div>`).join(''):'<p class="helper">Καμία απογραφή με φωτογραφία ακόμη.</p>';
 }catch(err){handleError(err)}
}
async function showLoans(){
 try{const rows=await req('/api/loans');const overdue=rows.filter(x=>x.overdue);
 $('#content').innerHTML=`<section class="panel"><div class="panel-header"><div><h2 class="panel-title">⇄ Δανεισμός εξοπλισμού</h2><p class="panel-caption">Όλες οι ενεργές αφαιρέσεις, με υπεύθυνο, project και ημερομηνία επιστροφής.</p></div><button class="btn btn-outline" id="loansExcel">↓ Excel</button></div>
 <div class="v4-pad"><div class="v4-metrics"><div><b>${rows.length}</b><small>Ανοιχτοί δανεισμοί</small></div><div><b>${rows.reduce((s,x)=>s+x.quantity_open,0)}</b><small>Τεμάχια εκτός αποθήκης</small></div><div><b>${overdue.length}</b><small>Εκπρόθεσμοι</small></div></div>
 ${rows.length?rows.map(x=>`<article class="v4-loan ${x.overdue?'v4-overdue':''}"><div><b>${e(x.name)}</b><small>${e(x.sku)} · ${fmt(x.quantity_open)} τμχ. · ${e(x.location_id||'Άγνωστη αρχική θέση')}</small><p>👤 ${e(x.holder)} · ${x.project?'Project: '+e(x.project):'Χωρίς project'}${x.due_date?' · Έως '+e(x.due_date):''}</p>${x.overdue?'<span class="v4-status danger">Εκπρόθεσμο</span>':''}</div><div class="v4-actions"><button class="btn btn-outline" data-editloan="${x.id}">Επεξεργασία</button><button class="btn btn-primary" data-return="${e(x.sku)}">Επιστροφή →</button></div></article>`).join(''):'<div class="find-empty">Δεν υπάρχουν ανοικτοί δανεισμοί.</div>'}
 </div></section>`;
 $('#loansExcel').onclick=()=>location.assign('/export/inventory.xlsx');
 $('#content').querySelectorAll('[data-return]').forEach(b=>b.onclick=async()=>{await openItem(b.dataset.return);fillMovementForm('RETURN',state.selected)});
 $('#content').querySelectorAll('[data-editloan]').forEach(b=>b.onclick=()=>{const r=rows.find(x=>x.id===Number(b.dataset.editloan));
  showModal('Επεξεργασία δανεισμού #'+r.id,`<div class="field"><label>Άτομο/ομάδα</label><input name="holder" class="input" value="${e(r.holder)}" required></div><div class="field"><label>Project</label><input name="project" class="input" value="${e(r.project||'')}"></div><div class="field"><label>Προθεσμία επιστροφής</label><input name="due_date" type="date" class="input" value="${e(r.due_date||'')}"></div>`,async f=>{await req('/api/loan/settings','POST',{id:r.id,...Object.fromEntries(f.entries())});notify('Τα στοιχεία δανεισμού ενημερώθηκαν.')})
 });
 }catch(err){handleError(err)}
}
async function showAlerts(){
 try{const rows=await req('/api/alerts');const types={empty:'Μηδενικό',low:'Κάτω από όριο',forecast:'Πιθανή ανάγκη'};
 $('#content').innerHTML=`<section class="panel"><div class="panel-header"><div><h2 class="panel-title">◬ Έλεγχος αποθεμάτων</h2><p class="panel-caption">Όρια ανά είδος και ενδεικτική πρόβλεψη με βάση τις αφαιρέσεις των τελευταίων 60 ημερών.</p></div><a class="btn btn-primary" href="/export/inventory.xlsx">↓ Export Excel</a></div><div class="v4-pad">
 <div class="banner">Ρύθμισε το όριο και τις ημέρες αναπλήρωσης από κάθε είδος. Η πρόβλεψη ενεργοποιείται μόνο με τουλάχιστον δύο καταγεγραμμένες αφαιρέσεις — δεν επινοεί ιστορικό από το Excel.</div>
 <div class="v4-metrics"><div><b>${rows.filter(x=>x.level==='empty').length}</b><small>Μηδενικά</small></div><div><b>${rows.filter(x=>x.level==='low').length}</b><small>Χαμηλά</small></div><div><b>${rows.filter(x=>x.level==='forecast').length}</b><small>Προβλεπόμενη ανάγκη</small></div></div>
 ${rows.length?`<div class="v4-alert-wrap">${rows.map(x=>`<button class="v4-alert" data-alertsku="${e(x.sku)}"><span class="v4-status ${x.level==='empty'?'danger':'warning'}">${types[x.level]}</span><b>${e(x.name)}</b><small>${e(x.sku)} · Διαθέσιμα ${fmt(x.on_hand)} · Όριο ${fmt(x.reorder_point)} · Αφαιρέσεις 60 ημερών ${fmt(x.out60)}</small><small>Ενδεικτική αναπλήρωση: ${fmt(x.suggested_order)} τμχ. ${x.events60>=2?'(από καταγεγραμμένη ζήτηση)':'(χωρίς αρκετή ιστορική κίνηση)'}</small></button>`).join('')}</div>`:'<div class="find-empty">Δεν υπάρχουν προειδοποιήσεις σύμφωνα με τα δηλωμένα όρια και τις καταγεγραμμένες κινήσεις.</div>'}
 </div></section>`;
 $('#content').querySelectorAll('[data-alertsku]').forEach(b=>b.onclick=()=>openItem(b.dataset.alertsku));
 }catch(err){handleError(err)}
}
async function showAssistant(){
 $('#content').innerHTML=`<section class="find-hero"><div class="find-eyebrow">✦ ΕΡΓΑΣΤΗΡΙΑΚΟΣ ΒΟΗΘΟΣ</div><h2>Ρώτησε την αποθήκη σου</h2><p>Ο βοηθός διαβάζει το πραγματικό inventory. Ακριβείς θέσεις και ποσότητες προέρχονται από τη βάση· για σύνθετες συμβουλές χρησιμοποιεί Gemini.</p>
 <form id="assistantForm" class="find-form"><input id="assistantQuery" class="input" placeholder="π.χ. Τι έχουμε για ρομποτικό βραχίονα;" required maxlength="400"><button class="btn btn-primary">✦ Ρώτησε</button></form>
 <div class="find-samples"><button data-ask="Πού βρίσκεται το Raspberry Pi 4;">Πού είναι το Raspberry Pi 4;</button><button data-ask="Ποια είδη τελειώνουν;">Τι τελειώνει;</button><button data-ask="Τι έχουμε για να φτιάξω ρομποτικό χέρι;">Ρομποτικό χέρι</button></div></section>
 <div id="assistantResults" class="v4-chat"><div class="find-empty">Κάνε μια ερώτηση. Δεν χρειάζεται Gemini για αναζήτηση θέσης και ποσότητας.</div></div>`;
 $('#assistantForm').onsubmit=async ev=>{ev.preventDefault();await askLab()};
 $('#content').querySelectorAll('[data-ask]').forEach(b=>b.onclick=()=>{$('#assistantQuery').value=b.dataset.ask;askLab()});
}
async function askLab(){
 const query=$('#assistantQuery').value.trim();if(!query)return;
 const target=$('#assistantResults');target.innerHTML=`<div class="v4-chat-user">${e(query)}</div><div class="v4-chat-ai">Γίνεται αναζήτηση στο inventory…</div>`;
 try{const res=await req('/api/assistant','POST',{question:query});if(state.view!=='assistant')return;
 target.innerHTML=`<div class="v4-chat-user">${e(query)}</div><article class="v4-chat-ai"><span class="find-eyebrow">${res.mode==='gemini'?'✦ GEMINI + INVENTORY':'◈ ΤΟΠΙΚΟ INVENTORY'}</span><p>${e(res.answer)}</p>${res.warning?`<p class="helper">${e(res.warning)}</p>`:''}
 ${(res.matches||[]).length?`<div class="v4-chat-cards">${res.matches.slice(0,8).map(x=>x.skus?`<div class="v4-chat-item"><b>${e(x.name)}</b><small>${fmt(x.quantity)} τμχ. · ${x.locations.map(l=>e(l.id)).join(', ')}</small><button class="btn btn-outline" data-chatitem="${e(x.skus[0])}">Δες είδος →</button></div>`:`<div class="v4-chat-item"><b>${e(x.name)}</b><small>${e(x.sku)} · ${x.qty??x.on_hand??'—'} διαθέσιμα</small><button class="btn btn-outline" data-chatitem="${e(x.sku)}">Δες είδος →</button></div>`).join('')}</div>`:''}</article>`;
 target.querySelectorAll('[data-chatitem]').forEach(b=>b.onclick=()=>openItem(b.dataset.chatitem));
 }catch(err){target.innerHTML=`<div class="banner warn">${e(err.message)}</div>`;handleError(err)}
}
async function showCabinetTwin(){
 const orig=$('#cabinetDigitalTwin');if(!orig)return;
 const grouped={};state.locations.filter(l=>l.id!=='C99-S00').forEach(l=>(grouped[l.cabinet]??=[]).push(l));
 orig.innerHTML=`<div class="v4-cab-grid">${Object.entries(grouped).sort((a,b)=>+a[0]-+b[0]).map(([cab,positions])=>`<article class="v4-cabinet"><div class="v4-cab-heading"><strong>ΝΤΟΥΛΑΠΑ ${e(cab)}</strong><small>${positions.length} θέσεις · ${fmt(positions.reduce((s,x)=>s+x.units,0))} τεμάχια</small></div><div class="v4-shelf-list">${positions.sort((a,b)=>a.slot-b.slot).map(l=>`<button data-twinshelf="${e(l.id)}" class="v4-shelf"><span>▦ ${e(l.id)}</span><span>${fmt(l.item_types)} είδη · ${fmt(l.units)} τμχ.</span></button>`).join('')}</div></article>`).join('')}</div>`;
 orig.querySelectorAll('[data-twinshelf]').forEach(b=>b.onclick=()=>openTwinShelf(b.dataset.twinshelf));
}
async function openTwinShelf(id){
 try{const d=await req('/api/location/'+id);
 $('#modalOverlay').classList.remove('hidden');$('#modalOverlay').setAttribute('aria-hidden','false');
 $('#modalContent').innerHTML=`<div class="modal-head"><h2>▤ ${e(d.label)}</h2><button class="iconbutton" id="closeTwin">✕</button></div><div class="modal-body">
 ${d.photo_url?`<img class="v4-shelf-photo" src="${e(d.photo_url)}" alt="Φωτογραφία ραφιού">`:'<p class="banner">Δεν έχει προστεθεί φωτογραφία σε αυτή τη θέση. Μπορείς να τη φωτογραφίσεις από τις Ντουλάπες.</p>'}
 <div class="v4-metrics"><div><b>${fmt(d.items.length)}</b><small>Είδη</small></div><div><b>${fmt(d.units)}</b><small>Τεμάχια</small></div><div><b>${d.capacity_units==null?'—':fmt(d.capacity_units)}</b><small>Δηλωμένη χωρητικότητα</small></div></div>
 <div class="section-header">ΠΕΡΙΕΧΟΜΕΝΑ ΘΕΣΗΣ</div><div class="v4-shelf-items">${d.items.length?d.items.map(i=>`<button class="v4-shelf-item" data-sku="${e(i.sku)}"><span>${e(i.name)}<small>${e(i.sku)} · ${e(i.category)}</small></span><b>${fmt(i.quantity)} τμχ.</b></button>`).join(''):'<p class="helper">Δεν υπάρχουν καταγεγραμμένα διαθέσιμα τεμάχια.</p>'}</div>
 <div class="divider"></div><h3>Ρυθμίσεις χωρητικότητας / μεγέθους</h3><p class="helper">Η χωρητικότητα είναι δική σου κατά προσέγγιση καταχώριση σε τεμάχια, όχι πραγματική εκτίμηση όγκου.</p>
 <div class="field"><label>Μέγιστος αριθμός τεμαχίων (προαιρετικό)</label><input class="input" type="number" min="0" id="twinCapacity" value="${d.capacity_units??''}" placeholder="Άγνωστη χωρητικότητα"></div>
 <div class="field"><label>Επιτρεπτά μεγέθη</label><div class="v4-size-checks">${[['small','Μικρά'],['medium','Μεσαία'],['large','Μεγάλα']].map(([v,n])=>`<label><input type="checkbox" value="${v}" data-size-allowed ${d.allowed_sizes.split(',').includes(v)?'checked':''}> ${n}</label>`).join('')}</div></div>
 <button class="btn btn-primary" id="saveTwinShelf">Αποθήκευση ρυθμίσεων</button></div>`;
 $('#closeTwin').onclick=closeModal;
 $('#modalContent').querySelectorAll('[data-sku]').forEach(b=>b.onclick=()=>{closeModal();openItem(b.dataset.sku)});
 $('#saveTwinShelf').onclick=async()=>{const sizes=[...document.querySelectorAll('[data-size-allowed]:checked')].map(x=>x.value);try{await req('/api/location/settings','POST',{location_id:id,capacity_units:$('#twinCapacity').value,allowed_sizes:sizes});notify('Οι ρυθμίσεις ραφιού αποθηκεύτηκαν.');closeModal();await refreshLocations();setView('locations')}catch(err){handleError(err)}};
 }catch(err){handleError(err)}
}
