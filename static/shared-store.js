/* shared-store.js — IndexedDB persistence for the medicine-list app.
 *
 * One object store 'files' holds records:
 *   { id, filename, type, ext, size, blob, source ('shared'|'manual'), created }
 *
 * The Index 3-file batch = records with batch_slot 0..2 in store meta 'index_batch'.
 * Shared documents NEVER go to Cache Storage — IndexedDB only.
 */
(function (global) {
    'use strict';

    const DB_NAME = 'medlist-shared';
    const DB_VERSION = 1;
    const FILES_STORE = 'files';
    const META_STORE = 'meta';
    const INDEX_BATCH_KEY = 'index_batch';   // array of record ids, max 3
    const TTL_MS = 24 * 60 * 60 * 1000;      // 24h cleanup for orphans

    let _dbPromise = null;

    function openDB() {
        if (_dbPromise) return _dbPromise;
        _dbPromise = new Promise(function (resolve, reject) {
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function (e) {
                const db = e.target.result;
                if (!db.objectStoreNames.contains(FILES_STORE)) {
                    db.createObjectStore(FILES_STORE, { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains(META_STORE)) {
                    db.createObjectStore(META_STORE);
                }
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
        return _dbPromise;
    }

    function tx(storeName, mode, fn) {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                const t = db.transaction(storeName, mode);
                const store = t.objectStore(storeName);
                let result;
                try { result = fn(store); } catch (err) { reject(err); return; }
                t.oncomplete = function () { resolve(result && result.__req ? result.__req.result : result); };
                t.onerror = function () { reject(t.error); };
                t.onabort = function () { reject(t.error); };
            });
        });
    }

    function reqToPromise(request) {
        return new Promise(function (resolve, reject) {
            request.onsuccess = function () { resolve(request.result); };
            request.onerror = function () { reject(request.error); };
        });
    }

    // ---------- generic records ----------

    function newId() {
        return (crypto.randomUUID && crypto.randomUUID()) ||
               ('f-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10));
    }

    /** Save a new file record; returns the record (with id). */
    function putFile(filename, type, ext, blob, source) {
        const record = {
            id: newId(),
            filename: filename,
            type: type,
            ext: ext,
            size: blob.size,
            blob: blob,
            source: source || 'shared',
            created: Date.now()
        };
        return tx(FILES_STORE, 'readwrite', function (store) {
            store.put(record);
        }).then(function () { return record; });
    }

    function getFile(id) {
        return openDB().then(function (db) {
            return reqToPromise(db.transaction(FILES_STORE).objectStore(FILES_STORE).get(id));
        });
    }

    function deleteFile(id) {
        return tx(FILES_STORE, 'readwrite', function (store) {
            store.delete(id);
        });
    }

    /** Remove old orphan records not referenced by any batch (TTL). */
    function cleanupOrphans() {
        return Promise.all([
            getIndexBatchIds(),
            tx(FILES_STORE, 'readonly', function (store) {
                const r = store.getAll();
                r.onsuccess = function () {
                    const now = Date.now();
                    r.result.forEach(function (rec) {
                        if (now - rec.created > TTL_MS) {
                            store.delete(rec.id);
                        }
                    });
                };
                return { __req: r };
            })
        ]).then(function () { return true; });
    }

    // ---------- index 3-file batch ----------

    function getMeta(key) {
        return openDB().then(function (db) {
            return reqToPromise(db.transaction(META_STORE).objectStore(META_STORE).get(key));
        });
    }

    function setMeta(key, value) {
        return tx(META_STORE, 'readwrite', function (store) {
            store.put(value, key);
        });
    }

    function getIndexBatchIds() {
        return getMeta(INDEX_BATCH_KEY).then(function (v) {
            return Array.isArray(v) ? v : [];
        });
    }

    /** Append a file id to the Index batch. Rejects if batch already has 3. */
    function appendToIndexBatch(id) {
        return getIndexBatchIds().then(function (ids) {
            if (ids.length >= 3) {
                return { ok: false, reason: 'full', ids: ids };
            }
            if (ids.indexOf(id) === -1) ids.push(id);
            return setMeta(INDEX_BATCH_KEY, ids).then(function () {
                return { ok: true, ids: ids };
            });
        });
    }

    /** Full Index batch records (in slot order). */
    function getIndexBatch() {
        return getIndexBatchIds().then(function (ids) {
            return Promise.all(ids.map(getFile)).then(function (recs) {
                return recs.filter(Boolean);
            });
        });
    }

    /** Remove one id from the batch (record itself is deleted too). */
    function removeFromIndexBatch(id) {
        return getIndexBatchIds().then(function (ids) {
            const remaining = ids.filter(function (x) { return x !== id; });
            return setMeta(INDEX_BATCH_KEY, remaining).then(function () {
                return deleteFile(id).then(function () { return remaining; });
            });
        });
    }

    /** Clear the whole Index batch and delete its records. Central helper. */
    function clearIndexBatch() {
        return getIndexBatchIds().then(function (ids) {
            return Promise.all(ids.map(deleteFile)).then(function () {
                return setMeta(INDEX_BATCH_KEY, []);
            });
        });
    }

    // ---------- conversion helpers ----------

    /** Build a browser File object from a record's blob. */
    function recordToFile(record) {
        const mimeByExt = {
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.htm': 'text/html'
        };
        const type = mimeByExt[record.ext] || record.type || 'application/octet-stream';
        return new File([record.blob], record.filename, { type: type });
    }

    function base64ToBlob(b64, mime) {
        const bin = atob(b64);
        const len = bin.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
        return new Blob([bytes], { type: mime || 'application/octet-stream' });
    }

    function fmtSize(n) {
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
        return (n / (1024 * 1024)).toFixed(1) + ' MB';
    }

    global.SharedStore = {
        putFile: putFile,
        getFile: getFile,
        deleteFile: deleteFile,
        cleanupOrphans: cleanupOrphans,
        appendToIndexBatch: appendToIndexBatch,
        getIndexBatch: getIndexBatch,
        getIndexBatchIds: getIndexBatchIds,
        removeFromIndexBatch: removeFromIndexBatch,
        clearIndexBatch: clearIndexBatch,
        recordToFile: recordToFile,
        base64ToBlob: base64ToBlob,
        fmtSize: fmtSize,
        MAX_BATCH: 3
    };
})(window);
