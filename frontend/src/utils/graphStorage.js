/**
 * IndexedDB Storage Utility for Large Graph Data
 *
 * Provides fallback storage for graphs that exceed sessionStorage quota (5MB).
 * IndexedDB supports 50MB-unlimited depending on browser, making it ideal for
 * mega repos with 10K+ nodes.
 *
 * Usage:
 *   await graphStorage.save(repoId, graphData)  // Save graph
 *   const data = await graphStorage.load(repoId) // Load graph (returns null if not found)
 *   await graphStorage.clear(repoId)             // Clear after use
 */

const DB_NAME = 'visdep_graph_cache';
const DB_VERSION = 1;
const STORE_NAME = 'graphs';

/**
 * Open IndexedDB connection
 * @returns {Promise<IDBDatabase>}
 */
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => {
      console.warn('IndexedDB open error:', request.error);
      reject(request.error);
    };

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'repo_id' });
      }
    };
  });
}

/**
 * Save graph data to IndexedDB
 * @param {string} repoId - Repository ID
 * @param {object} graphData - Graph data (nodes, edges)
 * @returns {Promise<boolean>} - Success status
 */
async function save(repoId, graphData) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);

      const record = {
        repo_id: repoId,
        data: graphData,
        timestamp: Date.now()
      };

      const request = store.put(record);

      request.onsuccess = () => {
        resolve(true);
      };

      request.onerror = () => {
        console.warn('IndexedDB save error:', request.error);
        reject(request.error);
      };

      transaction.oncomplete = () => {
        db.close();
      };
    });
  } catch (err) {
    console.warn('IndexedDB save failed:', err.message);
    return false;
  }
}

/**
 * Load graph data from IndexedDB
 * @param {string} repoId - Repository ID
 * @returns {Promise<object|null>} - Graph data or null if not found/expired
 */
async function load(repoId) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([STORE_NAME], 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.get(repoId);

      request.onsuccess = () => {
        const record = request.result;
        if (record) {
          // Check freshness (5 minute expiry, same as sessionStorage logic)
          const isFresh = Date.now() - record.timestamp < 5 * 60 * 1000;
          if (isFresh && record.data) {
            resolve(record.data);
          } else {
            resolve(null);
          }
        } else {
          resolve(null);
        }
      };

      request.onerror = () => {
        console.warn('IndexedDB load error:', request.error);
        resolve(null); // Return null on error, don't reject
      };

      transaction.oncomplete = () => {
        db.close();
      };
    });
  } catch (err) {
    console.warn('IndexedDB load failed:', err.message);
    return null;
  }
}

/**
 * Clear graph data from IndexedDB
 * @param {string} repoId - Repository ID
 * @returns {Promise<boolean>} - Success status
 */
async function clear(repoId) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.delete(repoId);

      request.onsuccess = () => {
        resolve(true);
      };

      request.onerror = () => {
        console.warn('IndexedDB clear error:', request.error);
        resolve(false);
      };

      transaction.oncomplete = () => {
        db.close();
      };
    });
  } catch (err) {
    console.warn('IndexedDB clear failed:', err.message);
    return false;
  }
}

/**
 * Check if IndexedDB is available in the browser
 * @returns {boolean}
 */
function isAvailable() {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch {
    return false;
  }
}

const graphStorage = {
  save,
  load,
  clear,
  isAvailable
};

export default graphStorage;
