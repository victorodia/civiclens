import Dexie from 'dexie';

export const db = new Dexie('CivicLensDB');

db.version(1).stores({
    drafts: '++id, puCode, status, createdAt', // Offline drafts before sync
    settings: 'key', // Local settings like device fingerprint
});

/**
 * Save a result draft locally
 */
export const saveDraft = async (resultData) => {
    return await db.drafts.add({
        ...resultData,
        status: 'pending',
        createdAt: new Date().toISOString(),
    });
};

/**
 * Get all pending drafts
 */
export const getPendingDrafts = async () => {
    return await db.drafts.where('status').equals('pending').toArray();
};

/**
 * Clear a specific draft after successful sync
 */
export const deleteDraft = async (id) => {
    return await db.drafts.delete(id);
};

/**
 * Factory Reset: Purge all local storage for the agent portal
 */
export const clearAllData = async () => {
    await db.drafts.clear();
    await db.settings.clear();
};


