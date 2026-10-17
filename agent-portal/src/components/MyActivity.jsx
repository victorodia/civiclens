import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, ChevronLeft, ChevronRight, Activity } from 'lucide-react';

// The agent's own audit trail — every event the system recorded against
// THIS account (logins, check-ins, uploads, submissions, rejections).
// The server enforces actor_id == me, so this can never leak anyone else.
const PAGE_SIZE = 25;

const MyActivity = () => {
    const [rows, setRows] = useState([]);
    const [total, setTotal] = useState(0);
    const [offset, setOffset] = useState(0);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchTrail = useCallback(async (off = 0) => {
        setIsLoading(true);
        setError(null);
        try {
            const token = localStorage.getItem('cl_access_token');
            const res = await fetch(`/audit-logs/me?limit=${PAGE_SIZE}&offset=${off}`, {
                headers: {
                    'X-Device-Fingerprint': 'MOCKED_PHONE_ID',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
                },
            });
            if (res.status === 401 || res.status === 403) {
                setError('Session expired — sign out and back in to view your activity.');
                setRows([]); setTotal(0);
                return;
            }
            if (!res.ok) { setError('Could not load your activity. Pull to retry.'); return; }
            const data = await res.json();
            setRows(data.rows || []);
            setTotal(data.total || 0);
        } catch (e) {
            setError('No connection. Your activity will load when you are back online.');
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { fetchTrail(0); setOffset(0); }, [fetchTrail]);

    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const page = Math.floor(offset / PAGE_SIZE) + 1;
    const fmtAt = (iso) => {
        if (!iso) return '';
        const d = new Date(iso);
        return isNaN(d) ? iso : d.toLocaleString();
    };
    const tone = (a) =>
        /REJECT|DENIED|FAIL/.test(a) ? 'text-red-600 bg-red-50 border-red-200'
        : /SUCCESS|UPLOADED|COMMITTED|CHECKIN|INITIALIZED|VERIFIED/.test(a) ? 'text-green-700 bg-green-50 border-green-200'
        : 'text-gray-600 bg-gray-50 border-gray-200';

    return (
        <div className="bg-white dark:bg-gray-900 rounded-3xl shadow-xl border border-gray-100 dark:border-gray-800 p-6">
            <div className="mb-4 flex items-start justify-between">
                <div>
                    <h2 className="text-xl font-black text-gray-900 dark:text-white uppercase tracking-tight">My Activity</h2>
                    <p className="text-xs text-gray-400 font-bold uppercase tracking-wider">
                        Your recorded actions on this system
                    </p>
                </div>
                <button onClick={() => fetchTrail(offset)} title="Refresh"
                    className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                    <RefreshCw className={`w-4 h-4 text-gray-400 ${isLoading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {error && (
                <div className="mb-4 text-xs font-bold text-red-600 bg-red-50 border border-red-200 rounded-xl p-3">{error}</div>
            )}

            {!error && isLoading && rows.length === 0 && (
                <p className="text-center text-gray-400 text-[10px] font-black uppercase tracking-widest py-10">Loading…</p>
            )}
            {!error && !isLoading && rows.length === 0 && (
                <div className="text-center py-10">
                    <Activity className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                    <p className="text-gray-400 text-[10px] font-black uppercase tracking-widest">
                        No recorded activity yet
                    </p>
                </div>
            )}

            <div className="space-y-2">
                {rows.map(r => (
                    <div key={r.seq} className="border border-gray-100 dark:border-gray-800 rounded-xl p-3">
                        <div className="flex items-center justify-between gap-2">
                            <span className={`inline-block px-2 py-0.5 rounded border text-[9px] font-black uppercase tracking-wide ${tone(r.action)}`}>
                                {r.action}
                            </span>
                            <span className="text-[10px] text-gray-400 font-bold whitespace-nowrap">{fmtAt(r.at)}</span>
                        </div>
                        {r.details && (
                            <p className="mt-1.5 text-xs text-gray-600 dark:text-gray-300 break-words">{r.details}</p>
                        )}
                    </div>
                ))}
            </div>

            {pages > 1 && (
                <div className="mt-4 flex items-center justify-between">
                    <button disabled={offset === 0} onClick={() => { const o = Math.max(0, offset - PAGE_SIZE); setOffset(o); fetchTrail(o); }}
                        className="flex items-center gap-1 px-3 py-2 text-[10px] font-black uppercase tracking-widest border border-gray-200 dark:border-gray-700 rounded-lg disabled:opacity-40">
                        <ChevronLeft className="w-3.5 h-3.5" /> Newer
                    </button>
                    <span className="text-[10px] font-bold uppercase text-gray-400">{page} / {pages}</span>
                    <button disabled={offset + PAGE_SIZE >= total} onClick={() => { const o = offset + PAGE_SIZE; setOffset(o); fetchTrail(o); }}
                        className="flex items-center gap-1 px-3 py-2 text-[10px] font-black uppercase tracking-widest border border-gray-200 dark:border-gray-700 rounded-lg disabled:opacity-40">
                        Older <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                </div>
            )}
        </div>
    );
};

export default MyActivity;
