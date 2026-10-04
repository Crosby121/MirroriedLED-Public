(function (root) {
  'use strict';
  const open = () => new Promise((resolve, reject) => {
    const request = indexedDB.open('mirroriedled_infinity_drafts_v1', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('drafts', { keyPath: 'id' });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error('Your browser could not save the artwork.'));
  });
  async function transaction(mode, action) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('drafts', mode), req = action(tx.objectStore('drafts'));
      tx.oncomplete = () => { db.close(); resolve(req.result); };
      tx.onerror = tx.onabort = () => { db.close(); reject(new Error('Your browser could not save the artwork.')); };
    });
  }
  root.MirrorDraftStore = { put: value => transaction('readwrite', s => s.put(value)), get: id => transaction('readonly', s => s.get(id)), remove: id => transaction('readwrite', s => s.delete(id)) };
})(globalThis);
