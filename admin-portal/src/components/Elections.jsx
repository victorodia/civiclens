import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Vote, Plus, MapPin, Save, ChevronDown, ChevronUp } from 'lucide-react';
import { useElection } from '../contexts/ElectionContext';
import { useNotification } from '../contexts/NotificationContext';

const TYPES = ['general', 'presidential', 'gubernatorial', 'senatorial', 'house_of_reps', 'lga'];
const STATUS_STYLE = {
    upcoming: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
    live: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
    closed: 'bg-gray-200 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

const TYPE_LABEL = {
    general: 'General', presidential: 'Presidential', gubernatorial: 'Gubernatorial',
    senatorial: 'Senatorial', house_of_reps: 'House of Reps', lga: 'LGA / Local',
};

function ScopeEditor({ election, onDone }) {
    const { showNotification } = useNotification();
    const [states, setStates] = useState([]);
    const [lgasByState, setLgasByState] = useState({});
    const [checkedLgas, setCheckedLgas] = useState({});
    const [openStates, setOpenStates] = useState({});
    const [saving, setSaving] = useState(false);
    const [elapsed, setElapsed] = useState(0);

    // Elapsed-seconds ticker while a scope save is in flight
    useEffect(() => {
        if (!saving) { setElapsed(0); return; }
        const t = setInterval(() => setElapsed(e => e + 1), 1000);
        return () => clearInterval(t);
    }, [saving]);

    useEffect(() => {
        (async () => {
            try {
                const res = await fetch('/admin/geo/states');
                if (!res.ok) return;
                const data = await res.json();
                setStates(data.states || data || []);
            } catch (e) {}
        })();
    }, []);

    const toggleState = async (st, open) => {
        setOpenStates(prev => ({ ...prev, [st.id]: open }));
        if (open && !lgasByState[st.id]) {
            try {
                const res = await fetch(`/admin/geo/states/${st.id}/lgas`);
                if (!res.ok) return;
                const data = await res.json();
                const lgas = data.lgas || data || [];
                setLgasByState(prev => ({ ...prev, [st.id]: lgas }));
                setCheckedLgas(prev => {
                    const next = { ...prev };
                    // Default: every LGA of an opened state joins the scope
                    lgas.forEach(l => { if (!(l.id in next)) next[l.id] = true; });
                    return next;
                });
            } catch (e) {}
        }
    };

    const allChecked = () => Object.values(checkedLgas).filter(Boolean).length;
    const wholeStates = states.filter(st =>
        (lgasByState[st.id] || []).length > 0 && lgasByState[st.id].every(l => checkedLgas[l.id])
    ).map(st => st.name);

    const save = async () => {
        const lga_ids = Object.entries(checkedLgas).filter(([, v]) => v).map(([k]) => k);
        if (!lga_ids.length) {
            showNotification('Pick at least one LGA.', 'warning');
            return;
        }
        setSaving(true);
        try {
            const res = await fetch(`/admin/elections/${election.id}/scope`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lga_ids }),
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                showNotification(`Scope saved: ${data.pus} polling units.`, 'success');
                onDone && onDone();
            } else {
                showNotification(data.detail || 'Scope save failed.', 'error');
            }
        } catch (e) {
            showNotification('Network error while saving scope.', 'error');
        } finally {
            setSaving(false);
        }
    };

    const phaseText = () => {
        if (elapsed < 8) return 'Resolving polling units…';
        if (elapsed < 60) return 'Rewriting election scope — the biggest step…';
        return 'Finalizing — almost done…';
    };

    return (
        <div className="mt-3 border border-gray-200 dark:border-gray-700 rounded-xl p-3 bg-gray-50 dark:bg-gray-900/40">
            <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                    Election scope — {allChecked()} LGAs selected
                </p>
                <button onClick={save} disabled={saving}
                    className="flex items-center space-x-1 bg-brand text-white px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest disabled:opacity-50">
                    <Save className="w-3 h-3" /><span>{saving ? 'Saving…' : 'Save scope'}</span>
                </button>
            </div>
            {saving && (
                <div className="mb-3 space-y-1.5" aria-live="polite">
                    <div className="h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden relative">
                        <motion.div
                            className="absolute top-0 bottom-0 w-1/3 rounded-full bg-brand"
                            animate={{ x: ['-110%', '320%'] }}
                            transition={{ repeat: Infinity, duration: 1.4, ease: 'easeInOut' }}
                        />
                    </div>
                    <p className="text-[10px] text-gray-500 font-bold">
                        {phaseText()} <span className="text-gray-400">({elapsed}s)</span> — please keep this page open.
                    </p>
                </div>
            )}
            {wholeStates.length > 0 && (
                <p className="text-[10px] text-gray-500 mb-2">Whole states: {wholeStates.join(', ')}</p>
            )}
            {!saving && allChecked() > 100 && (
                <p className="text-[10px] text-amber-600 dark:text-amber-400 font-bold mb-2">
                    Large scope — saving rewrites tens of thousands of records and can take up to a minute. A progress bar will show while it works.
                </p>
            )}
            <div className="max-h-64 overflow-y-auto space-y-1 pr-1">
                {states.map(st => (
                    <div key={st.id} className="border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900">
                        <button className="w-full flex items-center justify-between px-3 py-2"
                            onClick={() => toggleState(st, !openStates[st.id])}>
                            <span className="text-xs font-bold">{st.name}</span>
                            {openStates[st.id] ? <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-400" />}
                        </button>
                        {openStates[st.id] && (
                            <div className="px-3 pb-2 grid grid-cols-2 gap-1">
                                {(lgasByState[st.id] || []).map(l => (
                                    <label key={l.id} className="flex items-center space-x-2 text-[11px]">
                                        <input type="checkbox" checked={!!checkedLgas[l.id]}
                                            onChange={e => setCheckedLgas(prev => ({ ...prev, [l.id]: e.target.checked }))}
                                            className="accent-brand" />
                                        <span className="truncate">{l.name}</span>
                                    </label>
                                ))}
                                {lgasByState[st.id] && lgasByState[st.id].length > 8 && (
                                    <div className="col-span-2 flex space-x-3 pt-1">
                                        <button className="text-[10px] text-brand font-bold" onClick={() => setCheckedLgas(prev => {
                                            const n = { ...prev }; lgasByState[st.id].forEach(l => n[l.id] = true); return n;
                                        })}>All</button>
                                        <button className="text-[10px] text-gray-400 font-bold" onClick={() => setCheckedLgas(prev => {
                                            const n = { ...prev }; lgasByState[st.id].forEach(l => n[l.id] = false); return n;
                                        })}>None</button>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}

const Elections = ({ setActiveView }) => {
    const { elections, refresh, setActiveElection } = useElection();
    const { showNotification } = useNotification();
    const [showCreate, setShowCreate] = useState(false);
    const [scopeFor, setScopeFor] = useState(null);
    const [form, setForm] = useState({ name: '', code: '', type: 'gubernatorial', party_a_name: '', party_b_name: '', party_c_name: '', client_id: '' });
    const [saving, setSaving] = useState(false);

    // Institution tenancy: platform super-admins (no client_id of their own)
    // must pick which institution an election belongs to. Client admins are
    // locked to their own institution and never see this picker.
    const myClientId = (() => { try { return localStorage.getItem('adminClientId') || ''; } catch (e) { return ''; } })();
    const isPlatformAdmin = !myClientId;
    const [clients, setClients] = useState([]);
    useEffect(() => {
        if (!isPlatformAdmin || !showCreate) return;
        let cancelled = false;
        fetch('/admin/clients')
            .then(r => (r.ok ? r.json() : { clients: [] }))
            .then(d => { if (!cancelled) setClients(d.clients || []); })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [isPlatformAdmin, showCreate]);

    const create = async () => {
        if (!form.name.trim() || !form.code.trim()) {
            showNotification('Name and short code are required.', 'warning');
            return;
        }
        if (isPlatformAdmin && !form.client_id) {
            showNotification('Pick the institution this election belongs to.', 'warning');
            return;
        }
        setSaving(true);
        try {
            const res = await fetch('/admin/elections', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(isPlatformAdmin ? form : { ...form, client_id: undefined }),
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                showNotification(`Election "${data.name}" created. Now set its scope.`, 'success');
                setForm({ name: '', code: '', type: 'gubernatorial', party_a_name: '', party_b_name: '', party_c_name: '', client_id: '' });
                setShowCreate(false);
                await refresh();
                setScopeFor(data.id);
            } else {
                showNotification(data.detail || 'Create failed.', 'error');
            }
        } catch (e) {
            showNotification('Network error.', 'error');
        } finally {
            setSaving(false);
        }
    };

    const setStatus = async (e, status) => {
        try {
            const res = await fetch(`/admin/elections/${e.id}/status`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            if (res.ok) { showNotification(`${e.name} is now ${status}.`, 'success'); refresh(); }
            else showNotification('Status change failed.', 'error');
        } catch (e2) { showNotification('Network error.', 'error'); }
    };

    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-sm font-black uppercase tracking-widest flex items-center space-x-2">
                        <Vote className="w-4 h-4" /><span>Elections</span>
                    </h2>
                    <p className="text-[10px] text-gray-500">Run several races at once — each with its own scope, agents and results.</p>
                </div>
                <button onClick={() => setShowCreate(v => !v)}
                    className="flex items-center space-x-1 bg-brand text-white px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest">
                    <Plus className="w-3.5 h-3.5" /><span>New</span>
                </button>
            </div>

            {showCreate && (
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 space-y-2">
                    <p className="text-[10px] font-black uppercase tracking-widest text-gray-500">Create election</p>
                    <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Taraba State Governorship 2027"
                        className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent" />
                    <div className="grid grid-cols-2 gap-2">
                        <input value={form.code} onChange={e => setForm({ ...form, code: e.target.value.toUpperCase() })}
                            placeholder="Short code (TAR-GOV-27)" maxLength={30}
                            className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent font-mono" />
                        <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}
                            className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent">
                            {TYPES.map(t => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
                        </select>
                    </div>
                    {isPlatformAdmin && (
                        <select value={form.client_id} onChange={e => setForm({ ...form, client_id: e.target.value })}
                            className="w-full text-xs px-3 py-2 rounded-lg border border-brand/50 dark:border-gray-700 bg-transparent font-bold">
                            <option value="">— Institution this election belongs to —</option>
                            {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                        </select>
                    )}
                    <div className="grid grid-cols-3 gap-2">
                        {['party_a_name', 'party_b_name', 'party_c_name'].map(k => (
                            <input key={k} value={form[k]} onChange={e => setForm({ ...form, [k]: e.target.value })}
                                placeholder={k === 'party_a_name' ? 'Party A' : k === 'party_b_name' ? 'Party B' : 'Party C'}
                                className="w-full text-xs px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-transparent" />
                        ))}
                    </div>
                    <p className="text-[10px] text-gray-400">The short code is signed into every result this election reports — it can never be confused with another race.</p>
                    <button onClick={create} disabled={saving}
                        className="w-full bg-brand text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest disabled:opacity-50">
                        {saving ? 'Creating…' : 'Create election'}
                    </button>
                </div>
            )}

            {elections.length === 0 && (
                <div className="text-center py-10 text-xs text-gray-400">No elections yet.</div>
            )}

            {elections.map(e => (
                <div key={e.id} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
                    <div className="flex items-start justify-between">
                        <div>
                            <div className="flex items-center space-x-2">
                                <span className="font-bold text-sm">{e.name}</span>
                                <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${STATUS_STYLE[e.status] || STATUS_STYLE.upcoming}`}>{e.status}</span>
                            </div>
                            <p className="text-[10px] text-gray-400 font-mono">{e.code} · {TYPE_LABEL[e.type] || e.type}</p>
                            {isPlatformAdmin && e.client_name && (
                                <p className="text-[9px] text-brand/80 dark:text-brand font-bold uppercase tracking-widest">🏛 {e.client_name}</p>
                            )}
                        </div>
                        <select value={e.status} onChange={ev => setStatus(e, ev.target.value)}
                            className="text-[10px] bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-2 py-1">
                            <option value="upcoming">Upcoming</option>
                            <option value="live">Live</option>
                            <option value="closed">Closed</option>
                        </select>
                    </div>

                    <div className="grid grid-cols-3 gap-2 mt-3 text-center">
                        <div className="bg-gray-50 dark:bg-gray-800/60 rounded-lg py-2">
                            <div className="text-sm font-black">{e.pus ?? 0}</div>
                            <div className="text-[9px] uppercase tracking-widest text-gray-400">PUs in scope</div>
                        </div>
                        <div className="bg-gray-50 dark:bg-gray-800/60 rounded-lg py-2">
                            <div className="text-sm font-black">{e.agents ?? 0}</div>
                            <div className="text-[9px] uppercase tracking-widest text-gray-400">Agents</div>
                        </div>
                        <div className="bg-gray-50 dark:bg-gray-800/60 rounded-lg py-2">
                            <div className="text-sm font-black">{e.submitted ?? 0}</div>
                            <div className="text-[9px] uppercase tracking-widest text-gray-400">Submitted</div>
                        </div>
                    </div>

                    <div className="flex space-x-4 mt-3">
                        <button className="text-[10px] font-black uppercase tracking-widest text-brand"
                            onClick={() => setScopeFor(scopeFor === e.id ? null : e.id)}>
                            {scopeFor === e.id ? 'Close scope editor' : (e.pus ? 'Edit scope' : 'Set scope')}
                        </button>
                        <button className="text-[10px] font-black uppercase tracking-widest text-brand flex items-center space-x-1"
                            onClick={() => { setActiveElection(e.id); setActiveView && setActiveView('livemap'); }}>
                            <MapPin className="w-3 h-3" /><span>Live map</span>
                        </button>
                    </div>

                    {scopeFor === e.id && <ScopeEditor election={e} onDone={refresh} />}
                </div>
            ))}
        </motion.div>
    );
};

export default Elections;
