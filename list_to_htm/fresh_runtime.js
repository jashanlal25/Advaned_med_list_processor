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

  function recalc(){
    var count = 0, net = 0;
    rows.forEach(function(row){
      var qty = parseInt(row.querySelector('.qty-input').value, 10) || 0;
      if (qty <= 0) return;
      count++;
      net += qty * toNum(row.dataset.tp) * (1 - toNum(row.dataset.disc) / 100) + qty * toNum(row.dataset.tax);
    });
    elTotalAll.textContent = String(rows.length);
    elTotalSel.textContent = String(count);
    elNetTotal.textContent = fmt2(net);
    if (typeof syncPanelData === 'function') syncPanelData();
  }
  rows.forEach(function(row){
    var input = row.querySelector('.qty-input');
    if (draft[row.dataset.id]) input.value = draft[row.dataset.id];
    input.addEventListener('input', function(){
      var qty = Math.max(0, Math.min(5000, parseInt(input.value, 10) || 0));
      input.value = qty || '';
      if (qty) draft[row.dataset.id] = qty;
      else delete draft[row.dataset.id];
      offerStorage.setItem(LS_KEY_QTY, JSON.stringify(draft));
      offerStorage.setItem(LS_KEY_QTY + ':ts', String(Date.now()));
      recalc();
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
        var body = '<h2>Order Preview</h2><p>Customer: ' + escapeHtml(payload.customerName) +
          ' · List: ' + escapeHtml(String(payload.offerId)) + '</p><div class="fresh-preview-scroll"><table>' +
          '<thead><tr><th>Item</th><th>Qty</th><th>Disc</th><th>Bonus</th><th>TP</th><th>Tax</th><th>Net</th></tr></thead><tbody>';
        payload.items.forEach(function(it){
          body += '<tr><td>' + escapeHtml(toTitleCase(it.name)) + '</td><td>' + it.qty + '</td><td>' +
            fmt2(it.disc) + '%' + escapeHtml(it.discSuffix) + '</td><td>' + escapeHtml(it.bonus) + '</td><td>' +
            fmt2(it.tp) + '</td><td>' + fmt2(it.tax) + '</td><td>' + fmt2(it.lineNet) + '</td></tr>';
        });
        dialog.innerHTML = body + '</tbody></table></div><p>Items: ' + payload.totalItems + ' · Net: ' +
          fmt2(payload.netTotal) + '</p><button type="button" class="btn" data-pdf>PDF Order</button> ' +
          '<button type="button" class="btn" data-close>Close</button>';
        dialog.querySelector('[data-pdf]').onclick = function(){ window.localPdf(); };
        dialog.querySelector('[data-close]').onclick = function(){ dialog.close(); };
        dialog.addEventListener('close', function(){ dialog.remove(); });
        document.body.appendChild(dialog);
        dialog.showModal();
      });
    });
  });
  });
})();
