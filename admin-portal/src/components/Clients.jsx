import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Building2, Plus, Pencil, Trash2, Save, X } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const emptyForm = { name: '', contact_email: '', notes: '' };

// Institution (client) management — platform super-admins only. Client
// admins never see this page: the nav button is hidden and the API
// endpoints return 403 for anyone with a client_id on their account.
const Clients = () => {
    const { showNotification, showDialog } = useNotification();
    const [clients, setClients] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [form, setForm] = useState(emptyForm);
    const [saving, setSaving] = useState(false);
    const [editing, setEditing] = useState(null);   // client id being edited
    const [editForm, setEditForm] = useState(emptyForm);

    const isPlatformAdmin = (() => {
        try { return !localStorage.getItem('adminClientId'); } catch (e) { return false; }
    })();

    const load = useCallback(async () => {
        try {
            const res = await fetch('/admin/clients');
            if (!res.ok) { setClients([]); return; }
            const data = await res.json();
            setClients(data.clients || []);
        } catch (e) { /* offline — keep stale list */ }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { if (isPlatformAdmin) load(); }, [isPlatformAdmin, load]);

    if (!isPlatformAdmin) {
        return (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-6 text-center">
                <p className="text-xs text-gray-400">Institution management is restricted to platform administrators.</p>
            </motion.div>
        );
    }

    const create = async () => {
        if (!form.name.trim()) { showNotification('Institution name is required.', 'warning'); return; }
        setSaving(true);
        try {
            const res = await fetch('/admin/clients', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...form, contact_email: form.contact_email || null, notes: form.notes || null }),
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok || res.status === 201) {
                showNotification(`Institution "${data.name}" created.`, 'success');
                setForm(emptyForm);
                setShowCreate(false);
                load();
            } else {
                showNotification(data.detail || 'Create failed.', 'error');
            }
        } catch (e) { showNotification('Network error.', 'error'); }
        finally { setSaving(false); }
    };

    const startEdit = (c) => {
        setEditing(c.id);
        setEditForm({ name: c.name, contact_email: c.contact_email || '', notes: c.notes || '' });
    };

    const saveEdit = async () => {
        if (!editForm.name.trim()) { showNotification('Name must not be empty.', 'warning'); return; }
        try {
            const res = await fetch(`/admin/clients/${editing}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...editForm, contact_email: editForm.contact_email || null, notes: editForm.notes || null }),
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                showNotification('Institution updated.', 'success');
                setEditing(null);
                load();
            } else {
                showNotification(data.detail || 'Update failed.', 'error');
            }
        } catch (e) { showNotification('Network error.', 'error'); }
    };

    const remove = async (c) => {
        const ok = await showDialog({
            title: 'Delete Institution',
            message: `Delete "${c.name}"? This cannot be undone.`,
            input: false,
            danger: true
        });
        if (ok === null) return;
        try {
            const res = await fetch(`/admin/clients/${c.id}`, { method: 'DELETE' });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                showNotification(`Institution "${c.name}" deleted.`, 'success');
                load();
            } else {
                showNotification(data.detail || 'Delete failed.', 'error');
            }
        } catch (e) { showNotification('Network error.', 'error'); }
    };

    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-sm font-black uppercase tracking-widest flex items-center space-x-2">
                        <Building2 className="w-4 h-4" /><span>Institutions</span>
                    </h2>
                    <p className="text-[10px] text-gray-500">The organizations that hire you to monitor elections. Each sees only its own people and data.</p>
                </div>
                <button onClick={() => setShowCreate(v => !v)}
                    className="flex items-center space-x-1 bg-brand text-white px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest">
                    <Plus className="w-3.5 h-3.5" /><span>New</span>
                </button>
            </div>

            {showCreate && (
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 space-y-2">
                    <p className="text-[10px] font-black uppercase tracking-widest text-gray-500">Create institution</p>
                    <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                        placeholder="e.g. European Union Election Observation Mission"
                        className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent" />
                    <input value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })}
                        placeholder="Contact email (optional)"
                        className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent" />
                    <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                        placeholder="Notes — contract ref, focal person, etc. (optional)" rows={2}
                        className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent" />
                    <button onClick={create} disabled={saving}
                        className="w-full bg-brand text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest disabled:opacity-50">
                        {saving ? 'Creating…' : 'Create institution'}
                    </button>
                </div>
            )}

            {loading && <div className="text-center py-10 text-xs text-gray-400">Loading…</div>}
            {!loading && clients.length === 0 && (
                <div className="text-center py-10 text-xs text-gray-400">No institutions yet.</div>
            )}

            {clients.map(c => (
                <div key={c.id} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
                    {editing === c.id ? (
                        <div className="space-y-2">
                            <input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })}
                                className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent font-bold" />
                            <input value={editForm.contact_email} onChange={e => setEditForm({ ...editForm, contact_email: e.target.value })}
                                placeholder="Contact email"
                                className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent" />
                            <textarea value={editForm.notes} onChange={e => setEditForm({ ...editForm, notes: e.target.value })}
                                placeholder="Notes" rows={2}
                                className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent" />
                            <div className="flex space-x-3">
                                <button onClick={saveEdit}
                                    className="flex items-center space-x-1 text-[10px] font-black uppercase tracking-widest text-brand">
                                    <Save className="w-3 h-3" /><span>Save</span>
                                </button>
                                <button onClick={() => setEditing(null)}
                                    className="flex items-center space-x-1 text-[10px] font-black uppercase tracking-widest text-gray-400">
                                    <X className="w-3 h-3" /><span>Cancel</span>
                                </button>
                            </div>
                        </div>
                    ) : (
                        <>
                            <div className="flex items-start justify-between">
                                <div>
                                    <span className="font-bold text-sm">{c.name}</span>
                                    <p className="text-[10px] text-gray-400">
                                        {c.contact_email ? `${c.contact_email} · ` : ''}created {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                                    </p>
                                    {c.notes && <p className="text-[10px] text-gray-500 mt-1">{c.notes}</p>}
                                </div>
                                <div className="flex space-x-3">
                                    <button onClick={() => startEdit(c)}
                                        className="text-[10px] font-black uppercase tracking-widest text-brand flex items-center space-x-1">
                                        <Pencil className="w-3 h-3" /><span>Edit</span>
                                    </button>
                                    <button onClick={() => remove(c)}
                                        className="text-[10px] font-black uppercase tracking-widest text-red-500 flex items-center space-x-1">
                                        <Trash2 className="w-3 h-3" /><span>Delete</span>
                                    </button>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-2 mt-3 text-center">
                                <div className="bg-gray-50 dark:bg-gray-800/60 rounded-lg py-2">
                                    <div className="text-sm font-black">{c.elections ?? 0}</div>
                                    <div className="text-[9px] uppercase tracking-widest text-gray-400">Elections</div>
                                </div>
                                <div className="bg-gray-50 dark:bg-gray-800/60 rounded-lg py-2">
                                    <div className="text-sm font-black">{c.agents ?? 0}</div>
                                    <div className="text-[9px] uppercase tracking-widest text-gray-400">Agents</div>
                                </div>
                            </div>
                        </>
                    )}
                </div>
            ))}
        </motion.div>
    );
};

export default Clients;
