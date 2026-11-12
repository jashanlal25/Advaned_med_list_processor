/* Fresh uses New Format's row data, order payload, WhatsApp message and PDF exporter.
   Keep search/quantities/theme available when the downloaded file is offline. */
var offerStorage = {
  getItem: function(key){ try { return localStorage.getItem(key); } catch(e){ return null; } },
  setItem: function(key, value){ try { localStorage.setItem(key, value); } catch(e){} },
  removeItem: function(key){ try { localStorage.removeItem(key); } catch(e){} }
};
(function(){
  var rows = Array.from(elBody.querySelectorAll('tr.item-row'));
  var draft = {};
  var timestamp = Number(offerStorage.getItem(LS_KEY_QTY + ':ts'));
  if (timestamp && Date.now() - timestamp > OFFLINE_META.qtyExpireHours * 3600000) {
    offerStorage.removeItem(LS_KEY_QTY);
    offerStorage.removeItem(LS_KEY_QTY + ':ts');
  }
  try { draft = JSON.parse(offerStorage.getItem(LS_KEY_QTY) || '{}') || {}; } catch(e){}

  var entries = rows.map(function(row){
    return {row:row, input:row.querySelector('.qty-input'), qty:0,
      unitNet:toNum(row.dataset.tp) * (1 - toNum(row.dataset.disc) / 100) + toNum(row.dataset.tax)};
  });
  var selectedCount = 0, netTotal = 0, saveTimer;
  function renderTotals(){
    elTotalAll.textContent = String(rows.length);
    elTotalSel.textContent = String(selectedCount);
    elNetTotal.textContent = fmt2(netTotal);
    if (typeof syncPanelData === 'function') syncPanelData();
  }
  function recalc(){
    selectedCount = 0; netTotal = 0;
    entries.forEach(function(entry){
      entry.qty = Math.max(0, parseInt(entry.input.value, 10) || 0);
      if (entry.qty) selectedCount++;
      netTotal += entry.qty * entry.unitNet;
    });
    renderTotals();
  }
  function saveDraft(){
    clearTimeout(saveTimer); saveTimer = null;
    offerStorage.setItem(LS_KEY_QTY, JSON.stringify(draft));
    offerStorage.setItem(LS_KEY_QTY + ':ts', String(Date.now()));
  }
  window.addEventListener('pagehide', function(){ if (saveTimer) saveDraft(); });
  document.addEventListener('visibilitychange', function(){ if (document.hidden && saveTimer) saveDraft(); });
  entries.forEach(function(entry){
    var row = entry.row, input = entry.input;
    if (draft[row.dataset.id]) input.value = draft[row.dataset.id];
    input.addEventListener('input', function(){
      var qty = Math.max(0, Math.min(5000, parseInt(input.value, 10) || 0));
      input.value = qty || '';
      if (qty) draft[row.dataset.id] = qty;
      else delete draft[row.dataset.id];
      selectedCount += Number(qty > 0) - Number(entry.qty > 0);
      netTotal += (qty - entry.qty) * entry.unitNet;
      entry.qty = qty;
      renderTotals();
      clearTimeout(saveTimer);
      saveTimer = setTimeout(saveDraft, 150);
    });
  });
  live.addEventListener('input', function(){
    var query = live.value.toLowerCase().trim();
    rows.forEach(function(row){
      row.hidden = !((row.dataset.name + ' ' + row.dataset.code).toLowerCase().includes(query));
    });
    elBody.querySelectorAll('.company-head').forEach(function(head){
      var next = head.nextElementSibling, visible = false;
      while (next && !next.classList.contains('company-head')) {
        if (next.classList.contains('item-row') && !next.hidden) visible = true;
        next = next.nextElementSibling;
      }
      head.hidden = !visible;
    });
  });
  document.getElementById('resetBtn').addEventListener('click', function(){
    if (!confirm('Reset all quantities?')) return;
    clearTimeout(saveTimer); saveTimer = null;
    draft = {};
    rows.forEach(function(row){ row.querySelector('.qty-input').value = ''; });
    offerStorage.removeItem(LS_KEY_QTY);
    offerStorage.removeItem(LS_KEY_QTY + ':ts');
    recalc();
  });
  var themeButton = document.getElementById('themeBtn');
  function theme(value){
    document.documentElement.dataset.theme = value;
    themeButton.textContent = value === 'light' ? '☀️ Light' : '🌙 Dark';
    themeButton.setAttribute('aria-pressed', String(value === 'light'));
    offerStorage.setItem('anas.theme', value);
  }
  theme(offerStorage.getItem('anas.theme') === 'dark' ? 'dark' : 'light');
  themeButton.addEventListener('click', function(){
    theme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light');
  });
  recalc();

  // In-page preview works on mobile and inside Make HTML without a popup.
  document.addEventListener('DOMContentLoaded', function(){
  window.addEventListener('load', function(){
    ['previewBtn', 'previewBtnP'].forEach(function(id){
      var old = document.getElementById(id), button = old.cloneNode(true);
      old.replaceWith(button);
      button.addEventListener('click', function(){
        var payload = buildOrderPayload();
        if (!payload) return;
        var dialog = document.createElement('dialog');
        dialog.className = 'fresh-order-preview';
        var body = '<div class="fresh-preview-head"><h2>Order Preview</h2><span class="fresh-preview-business">' + escapeHtml(payload.shopTitle) + '</span></div><p>Customer: ' + escapeHtml(payload.customerName) +
          ' · List: ' + escapeHtml(String(payload.offerId)) + '</p><div class="fresh-preview-scroll"><table>' +
          '<thead><tr><th>Code</th><th>Item</th><th>Qty</th><th>Disc</th><th class="fresh-bonus">Bonus</th><th>TP</th><th>Tax</th><th>Net</th></tr></thead><tbody>';
        payload.items.forEach(function(it){
          body += '<tr><td class="fresh-code">' + escapeHtml(it.code) + '</td><td class="fresh-item">' + escapeHtml(toTitleCase(it.name)) + '</td><td>' + it.qty + '</td><td>' +
            fmt2(it.disc) + '%' + escapeHtml(it.discSuffix) + '</td><td class="fresh-bonus">' + escapeHtml(it.bonus) + '</td><td>' +
            fmt2(it.tp) + '</td><td>' + fmt2(it.tax) + '</td><td>' + fmt2(it.lineNet) + '</td></tr>';
        });
        dialog.innerHTML = body + '</tbody></table></div><div class="fresh-preview-summary">' +
          '<div class="fresh-preview-count"><span>Selected items</span><strong>' + payload.totalItems + '</strong></div>' +
          '<div class="fresh-preview-total"><span>Net total</span><strong>' + fmt2(payload.netTotal) + '</strong></div></div>' +
          '<div class="fresh-preview-actions"><button type="button" class="btn fresh-preview-pdf" data-pdf>📄 PDF Order</button>' +
          '<button type="button" class="btn fresh-preview-close" data-close>Close</button></div>';
        dialog.querySelector('[data-pdf]').onclick = function(){ window.localPdf(); };
        var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        dialog.querySelector('[data-close]').onclick = function(){
          if (!dialog.animate || reduceMotion) { dialog.close(); return; }
          this.disabled = true;
          dialog.animate([{opacity:1,transform:'translateY(0)'},{opacity:0,transform:'translateY(4px)'}],
                         {duration:90,easing:'ease-out',fill:'forwards'}).finished.then(function(){ dialog.close(); });
        };
        var savedOverflow = document.documentElement.style.overflow;
        var savedScrollX = window.scrollX, savedScrollY = window.scrollY;
        dialog.addEventListener('close', function(){
          window.freshPreviewOpen = false;
          document.documentElement.style.overflow = savedOverflow;
          dialog.remove();
          button.focus({preventScroll:true});
          window.scrollTo(savedScrollX, savedScrollY);
        });
        document.body.appendChild(dialog);
        if (typeof closeOrderPanel === 'function') closeOrderPanel();
        dialog.showModal();
        window.freshPreviewOpen = true;
        document.documentElement.style.overflow = 'hidden';
        if (dialog.animate && !reduceMotion) {
          dialog.animate([{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'translateY(0)'}],
                         {duration:130,easing:'ease-out'});
        }
      });
    });
  });
  });
})();
