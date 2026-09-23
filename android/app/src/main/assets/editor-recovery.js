// Bundled only in the APK. Never loaded by the website or PWA.
(() => {
    if (location.pathname !== '/make_html' || window.top !== window) return;
    const KEY = 'medlist.native.editor.v1';
    const incoming = /[?&](sharedid|mkid)=/.test(location.search) || !!localStorage.getItem('transferredContent');
    let ready = false, restoring = false, lastOutput, lastLogo;
    const byId = id => document.getElementById(id);
    const db = new Promise((resolve, reject) => {
        const request = indexedDB.open('medlist-native-editor', 1);
        request.onupgradeneeded = () => request.result.createObjectStore('draft');
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
    // Do not leave a rejected promise unhandled before the first save.
    db.catch(() => {});
    let warned = false;
    function warn() {
        if (!warned) { warned = true; alert('MedList could not save this draft on your device. Keep the app open and download your work. Check available storage.'); }
    }
    function snapshot() {
        const fields = {};
        document.querySelectorAll('.container input[id], .container select[id], .container textarea[id]').forEach(el => {
            if (el.type !== 'file' && el.id !== 'editorTextarea') fields[el.id] = {value: el.value, checked: el.checked};
        });
        let text = byId('editorTextarea').value;
        // Preserve the value still being typed, even before Enter/blur commits it.
        const input = document.querySelector('.inline-edit-input');
        if (input) {
            const cell = input.closest('td'), row = input.closest('tr');
            const match = cell && (cell.getAttribute('onclick') || '').match(/editCellInline\(this,'(\w+)'\)/);
            if (row && match) {
                const item = {...row.dataset}, lines = text.split('\n'), index = Number(item.lineIndex);
                let value = input.value.trim();
                if (match[1] === 'value' && value && !value.includes('%') && !/net/i.test(value)) value += '%';
                if (match[1] !== 'name' || value) item[match[1]] = value;
                if (Number.isInteger(index) && index >= 0 && index < lines.length) {
                    lines[index] = (item.extended === '1' || item.bonus || item.tp)
                        ? `${item.name}----- ${item.value}|${item.tp || ''}|${item.bonus || ''}|${item.tax || ''}`
                        : `${item.name}----- ${item.value}`;
                    text = lines.join('\n');
                }
            }
        }
        return {version: 1, at: Date.now(), text, fields,
            active: byId('editorSection').style.display === 'block',
            tab: byId('editorTextarea').style.display === 'block' ? 'edit' : 'preview',
            sort: typeof currentPreviewSort !== 'undefined' ? currentPreviewSort : 'alpha',
            scroll: window.scrollY, tableScroll: byId('previewContent').scrollTop,
            result: byId('result').style.display === 'block' && !!window._generatedHTML};
    }
    function save() {
        if (!ready || restoring || !byId('editorTextarea')) return Promise.resolve();
        const state = snapshot();
        let localSaved = false;
        // Synchronous core checkpoint survives immediate background/process death.
        try { localStorage.setItem(KEY, JSON.stringify(state)); localSaved = true; } catch (_) {}
        const output = window._generatedHTML || null;
        const logo = byId('logoInput').files[0] || null;
        return db.then(database => new Promise((resolve, reject) => {
            const tx = database.transaction('draft', 'readwrite');
            const store = tx.objectStore('draft');
            store.put(state, 'core');
            if (output !== lastOutput) store.put(output, 'output');
            if (logo !== lastLogo) store.put(logo, 'logo');
            tx.oncomplete = () => { lastOutput = output; lastLogo = logo; resolve(); };
            tx.onerror = tx.onabort = () => reject(tx.error);
        })).catch(() => { if (!localSaved || output || logo) warn(); });
    }
    window.__medlistSaveDraft = save;
    function wrap(name, before = false) {
        const original = window[name];
        if (typeof original !== 'function') return;
        window[name] = function(...args) {
            if (before) return save().then(() => original.apply(this, args));
            const value = original.apply(this, args);
            if (value && typeof value.then === 'function') return value.then(result => save().then(() => result));
            save();
            return value;
        };
    }
    document.addEventListener('DOMContentLoaded', () => {
        if (!byId('editorTextarea')) return;
        // The web page's temporary-session loader can overwrite an incoming file.
        // Native recovery below is durable and has no 20-minute expiration.
        window.loadSessionContent = () => {};
        ['showEditor', 'updateItemCount', 'saveCellEdit', 'deleteRow', 'undoLastDelete',
         'selectListType', 'selectOutputFormat', 'showTab', 'toggleRawEdit',
         'sortAlphabetically', 'sortByRate', 'generateHTML'].forEach(name => wrap(name));
        const reset = window.uploadNew;
        window.uploadNew = function(...args) {
            window._generatedHTML = null;
            const value = reset.apply(this, args); save(); return value;
        };
        const start = window.startMarkdown;
        window.startMarkdown = function(...args) {
            window._generatedHTML = null;
            const value = start.apply(this, args); save(); return value;
        };
        // Commit output and draft before Android opens another Activity.
        ['downloadGenerated', 'shareHTML'].forEach(name => wrap(name, true));
        document.addEventListener('input', save);
        document.addEventListener('change', save);
        document.addEventListener('visibilitychange', () => { if (document.hidden) save(); });
        window.addEventListener('pagehide', save);
        window.addEventListener('blur', save);
        let scrollTimer;
        window.addEventListener('scroll', () => { clearTimeout(scrollTimer); scrollTimer = setTimeout(save, 150); }, {passive:true});
        byId('previewContent').addEventListener('scroll', save, {passive:true});
    });
    document.addEventListener('DOMContentLoaded', () => setTimeout(async () => {
        if (!byId('editorTextarea')) return;
        let local = null, stored = {};
        try { local = JSON.parse(localStorage.getItem(KEY)); } catch (_) {}
        try {
            stored = await db.then(database => new Promise((resolve, reject) => {
                const tx = database.transaction('draft');
                const values = {};
                ['core', 'output', 'logo'].forEach(key => {
                    const request = tx.objectStore('draft').get(key);
                    request.onsuccess = () => { values[key] = request.result; };
                });
                tx.oncomplete = () => resolve(values);
                tx.onerror = () => reject(tx.error);
            }));
        } catch (_) {}
        const state = local && (!stored.core || local.at >= stored.core.at) ? local : stored.core;
        // An explicitly imported/shared document takes precedence over an older draft.
        if (!incoming && !byId('editorTextarea').value && state && state.version === 1) {
            restoring = true;
            try {
                for (const [id, field] of Object.entries(state.fields || {})) {
                    const el = byId(id);
                    if (el && el.type !== 'file') { el.value = field.value; el.checked = field.checked; }
                }
                byId('editorTextarea').value = state.text;
                if (typeof currentPreviewSort !== 'undefined') currentPreviewSort = state.sort;
                selectListType(byId('list_type').value);
                selectOutputFormat(byId('output_format').value);
                if (state.active) { showEditor(); showTab(state.tab); updateItemCount(); }
                if (stored.logo) {
                    const transfer = new DataTransfer(); transfer.items.add(stored.logo);
                    byId('logoInput').files = transfer.files; refreshLogoState();
                }
                window._generatedHTML = stored.output || null;
                if (state.result && stored.output) {
                    byId('result').style.display = 'block';
                    byId('resultMessage').textContent = 'Generated HTML restored. You can download or share it again.';
                    byId('resultButtonsOld').style.display = stored.output.old ? 'flex' : 'none';
                    byId('resultButtonsNew').style.display = stored.output.new ? 'flex' : 'none';
                }
                requestAnimationFrame(() => requestAnimationFrame(() => {
                    byId('previewContent').scrollTop = state.tableScroll || 0;
                    window.scrollTo(0, state.scroll || 0);
                }));
            } finally { restoring = false; }
        }
        ready = true;
        save();
    }, 0));
})();
