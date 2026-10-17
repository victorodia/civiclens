import React, { useState, useEffect, useCallback } from 'react';
import { Search, RefreshCw, Download, ShieldCheck, ShieldAlert, ChevronLeft, ChevronRight, Lock } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

// The immutable audit trail: every security-relevant action in the system,
// hash-chained so any tampering breaks the chain. Platform admins see every
// tenant; client admins are server-side forced to their own institution.
const ACTION_PREFIXES = [
    ['', 'All actions'],
    ['LOGIN', 'Logins'],
    ['AUTH_DENIED', 'Access denials'],
    ['MFA', 'MFA events'],
    ['CHECKIN', 'Check-ins / geofence'],
    ['RESULT', 'Result submissions'],
    ['MUSTER', 'Muster gates'],
    ['EVIDENCE', 'Evidence uploads'],
    ['AGENT', 'Agent lifecycle'],
    ['USER', 'User management'],
    ['CLIENT', 'Clients'],
    ['ELECTION', 'Elections'],
    ['PARTY', 'Parties'],
    ['FACTORY_RESET', 'Factory resets'],
];

const PAGE_SIZE = 50;

const AuditLogs = () => {
    const { showNotification } = useNotification();
    const [rows, setRows] = useState([]);
    const [total, setTotal] = useState(0);
    const [scope, setScope] = useState(null);
    const [chainTip, setChainTip] = useState(null);
    const [verify, setVerify] = useState(null);   // {valid, rows_checked, note}
    const [isLoading, setIsLoading] = useState(true);
    const [isVerifying, setIsVerifying] = useState(false);
    const [offset, setOffset] = useState(0);

    const isPlatformAdmin = (() => {
        try { return !localStorage.getItem('adminClientId'); } catch (e) { return false; }
    })();

    const [clients, setClients] = useState([]);
    const [elections, setElections] = useState([]);
    const [filters, setFilters] = useState({
        action: '', from: '', to: '', election_id: '', tenant_id: '',
    });

    useEffect(() => {
        (async () => {
            try {
                const [cRes, eRes] = await Promise.all([
                    isPlatformAdmin ? fetch('/admin/clients') : Promise.resolve(null),
                    fetch('/admin/elections'),
                ]);
                if (cRes && cRes.ok) setClients((await cRes.json()).clients || []);
                if (eRes.ok) setElections((await eRes.json()).elections || []);
            } catch (e) { console.error(e); }
        })();
    }, []);

    const buildQuery = useCallback((extra = {}) => {
        const q = new URLSearchParams();
        const f = { ...filters, ...extra };
        if (f.action) q.append('action', f.action);
        if (f.from) q.append('from', new Date(f.from).toISOString());
        if (f.to) q.append('to', new Date(f.to).toISOString());
        if (f.election_id) q.append('election_id', f.election_id);
        if (f.tenant_id && isPlatformAdmin) q.append('tenant_id', f.tenant_id);
        return q;
    }, [filters, isPlatformAdmin]);

    const fetchLogs = useCallback(async (off = offset) => {
        setIsLoading(true);
        try {
            const q = buildQuery();
            q.append('limit', String(PAGE_SIZE));
            q.append('offset', String(off));
            const res = await fetch(`/admin/audit-logs?${q.toString()}`);
            if (res.ok) {
                const data = await res.json();
                setRows(data.rows || []);
                setTotal(data.total || 0);
                setScope(data.scope);
                setChainTip(data.chain_tip || null);
            } else {
                showNotification('Could not load audit logs', 'error');
            }
        } catch (e) {
            showNotification('Network error loading audit logs', 'error');
        } finally {
            setIsLoading(false);
        }
    }, [buildQuery, offset, showNotification]);

    const runVerify = useCallback(async () => {
        setIsVerifying(true);
        try {
            // Scope is decided server-side from the caller's account; the
            // verify endpoint takes no filters.
            const res = await fetch('/admin/audit-logs/verify');
            if (res.ok) setVerify(await res.json());
            else showNotification('Chain verification failed to run', 'error');
        } catch (e) {
            showNotification('Network error verifying chain', 'error');
        } finally {
            setIsVerifying(false);
        }
    }, [buildQuery, showNotification]);

    useEffect(() => { fetchLogs(0); setOffset(0); }, [buildQuery]);
    useEffect(() => { runVerify(); }, [runVerify]);

    const exportCsv = async () => {
        try {
            const q = buildQuery();
            q.append('limit', '50000');
            const res = await fetch(`/admin/audit-logs/export?${q.toString()}`);
            if (!res.ok) { showNotification('Export failed', 'error'); return; }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `civiclens-audit-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            showNotification('Network error during export', 'error');
        }
    };

    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const page = Math.floor(offset / PAGE_SIZE) + 1;
    const fmtAt = (iso) => {
        if (!iso) return '—';
        const d = new Date(iso);
        return isNaN(d) ? iso : d.toLocaleString();
    };

    return (
        <div className="p-4 max-w-6xl mx-auto space-y-4 pb-24">
            <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                    <h1 className="text-lg font-black uppercase tracking-widest">Audit Log</h1>
                    <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
                        Immutable, hash-chained record{scope === 'platform' ? ' — full platform view' : ' — your institution only'}
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => fetchLogs(0)}
                        className="flex items-center gap-1 px-3 py-2 text-[10px] font-black uppercase tracking-widest border border-gray-300 rounded hover:bg-gray-100">
                        <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} /> Refresh
                    </button>
                    <button onClick={exportCsv}
                        className="flex items-center gap-1 px-3 py-2 text-[10px] font-black uppercase tracking-widest bg-brand text-white rounded hover:opacity-90">
                        <Download className="w-3.5 h-3.5" /> Export CSV
                    </button>
                </div>
            </div>

            {/* Chain integrity banner */}
            <div className={`rounded border p-3 flex items-start gap-2 ${verify && verify.valid
                ? 'bg-green-50 border-green-300 text-green-800'
                : 'bg-red-50 border-red-300 text-red-800'}`}>
                {verify && verify.valid
                    ? <ShieldCheck className="w-5 h-5 shrink-0 mt-0.5" />
                    : <ShieldAlert className="w-5 h-5 shrink-0 mt-0.5" />}
                <div className="text-xs">
                    {verify === null ? 'Checking chain integrity…' : verify.valid ? (
                        <>
                            <span className="font-black uppercase tracking-wider">Chain intact.</span>{' '}
                            {verify.rows_checked ?? verify.checked ?? total} row(s) re-hashed and matched
                            {verify.scope === 'tenant' && (
                                <> — <span className="font-bold">content check only</span> (rows are verified individually; cross-tenant linkage is sealed from your scope)</>
                            )}
                            {chainTip && <> · tip <code className="text-[10px]">{chainTip.slice(0, 16)}…</code></>}
                        </>
                    ) : (
                        <>
                            <span className="font-black uppercase tracking-wider">TAMPER DETECTED.</span>{' '}
                            The recomputed hash does not match the stored hash at sequence{' '}
                            <span className="font-black">{verify.first_break_seq}</span>. The log may have been altered — treat all records after that point as untrusted.
                        </>
                    )}
                </div>
                <button onClick={runVerify} disabled={isVerifying}
                    className="ml-auto text-[10px] font-black uppercase tracking-widest underline shrink-0">
                    {isVerifying ? 'Verifying…' : 'Re-verify'}
                </button>
            </div>

            {/* Filters */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                <select value={filters.action} onChange={e => setFilters({ ...filters, action: e.target.value })}
                    className="col-span-2 md:col-span-1 border border-gray-300 rounded px-2 py-2 text-xs font-bold uppercase">
                    {ACTION_PREFIXES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <input type="datetime-local" value={filters.from} title="From"
                    onChange={e => setFilters({ ...filters, from: e.target.value })}
                    className="border border-gray-300 rounded px-2 py-2 text-xs" />
                <input type="datetime-local" value={filters.to} title="To"
                    onChange={e => setFilters({ ...filters, to: e.target.value })}
                    className="border border-gray-300 rounded px-2 py-2 text-xs" />
                <select value={filters.election_id} onChange={e => setFilters({ ...filters, election_id: e.target.value })}
                    className="border border-gray-300 rounded px-2 py-2 text-xs font-bold">
                    <option value="">All elections</option>
                    {elections.map(el => <option key={el.id} value={el.id}>{el.name}</option>)}
                </select>
                {isPlatformAdmin && (
                    <select value={filters.tenant_id} onChange={e => setFilters({ ...filters, tenant_id: e.target.value })}
                        className="border border-gray-300 rounded px-2 py-2 text-xs font-bold">
                        <option value="">All institutions</option>
                        {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                )}
                <div className="col-span-2 md:col-span-1 flex items-center text-[10px] text-gray-500 font-bold uppercase">
                    <Search className="w-3.5 h-3.5 mr-1" /> {total} event{total === 1 ? '' : 's'}
                </div>
            </div>

            {/* Table */}
            <div className="overflow-x-auto border border-gray-200 rounded">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="bg-gray-50 text-left text-[9px] font-black uppercase tracking-widest text-gray-500">
                            <th className="p-2">Seq</th>
                            <th className="p-2">When</th>
                            <th className="p-2">Who</th>
                            <th className="p-2">Action</th>
                            <th className="p-2">Target</th>
                            {isPlatformAdmin && <th className="p-2">Institution</th>}
                            <th className="p-2">Details</th>
                            <th className="p-2">IP</th>
                        </tr>
                    </thead>
                    <tbody>
                        {isLoading && rows.length === 0 && (
                            <tr><td colSpan={8} className="p-8 text-center text-gray-400 font-bold uppercase text-[10px]">Loading…</td></tr>
                        )}
                        {!isLoading && rows.length === 0 && (
                            <tr><td colSpan={8} className="p-8 text-center text-gray-400 font-bold uppercase text-[10px]">No events match these filters</td></tr>
                        )}
                        {rows.map(r => (
                            <tr key={r.seq} className="border-t border-gray-100 hover:bg-gray-50 align-top">
                                <td className="p-2 font-mono text-[10px] text-gray-400">{r.seq}</td>
                                <td className="p-2 whitespace-nowrap">{fmtAt(r.at)}</td>
                                <td className="p-2">
                                    <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-black uppercase mr-1 ${r.actor_role === 'agent' ? 'bg-blue-100 text-blue-700' : r.actor_role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
                                        {r.actor_role || '?'}
                                    </span>
                                    <span className="font-mono text-[10px] break-all">{r.actor_id?.slice(0, 8)}…</span>
                                </td>
                                <td className="p-2">
                                    <span className={`font-black uppercase text-[10px] tracking-wide ${r.action?.includes('REJECT') || r.action?.includes('DENIED') || r.action?.includes('DELETE') ? 'text-red-600' : r.action?.includes('SUCCESS') || r.action?.includes('PROVISIONED') || r.action?.includes('UPLOADED') ? 'text-green-700' : 'text-gray-700'}`}>
                                        {r.action}
                                    </span>
                                </td>
                                <td className="p-2 text-gray-600">{r.target_type || '—'}<span className="font-mono text-[10px] block break-all">{r.target_id?.slice(0, 12)}</span></td>
                                {isPlatformAdmin && (
                                    <td className="p-2 text-gray-500 max-w-[140px] truncate">
                                        {r.tenant_id ? (clients.find(c => c.id === r.tenant_id)?.name || r.tenant_id.slice(0, 8) + '…') : <span className="flex items-center gap-1 text-[10px] uppercase font-bold"><Lock className="w-3 h-3" /> platform</span>}
                                    </td>
                                )}
                                <td className="p-2 text-gray-600 max-w-[280px] break-words">{r.details || '—'}</td>
                                <td className="p-2 font-mono text-[10px] text-gray-400">{r.ip_address || '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between">
                <button disabled={offset === 0} onClick={() => { const o = Math.max(0, offset - PAGE_SIZE); setOffset(o); fetchLogs(o); }}
                    className="flex items-center gap-1 px-3 py-2 text-[10px] font-black uppercase tracking-widest border border-gray-300 rounded disabled:opacity-40">
                    <ChevronLeft className="w-3.5 h-3.5" /> Newer
                </button>
                <span className="text-[10px] font-bold uppercase text-gray-500">Page {page} of {pages}</span>
                <button disabled={offset + PAGE_SIZE >= total} onClick={() => { const o = offset + PAGE_SIZE; setOffset(o); fetchLogs(o); }}
                    className="flex items-center gap-1 px-3 py-2 text-[10px] font-black uppercase tracking-widest border border-gray-300 rounded disabled:opacity-40">
                    Older <ChevronRight className="w-3.5 h-3.5" />
                </button>
            </div>
        </div>
    );
};

export default AuditLogs;
