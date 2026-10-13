import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { RefreshCw, ArrowLeft } from 'lucide-react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Status colours — one per operational category, consistent everywhere.
const STATUS = {
    unassigned:   { color: '#9ca3af', label: 'No agent assigned' },
    assigned:     { color: '#3b82f6', label: 'Agent not arrived' },
    on_site:      { color: '#10b981', label: 'Arrived — in perimeter' },
    out_of_fence: { color: '#f97316', label: 'Arrived — outside fence' },
    submitted:    { color: '#a855f7', label: 'Result submitted' },
};

const NIGERIA_BOUNDS = [[4.0, 2.5], [14.2, 14.9]];

const MonitorMap = ({ setActiveView, electionId }) => {
    const [data, setData] = useState(null);
    const [loadError, setLoadError] = useState(null);
    const [lastRefresh, setLastRefresh] = useState(null);
    const mapElRef = useRef(null);
    const mapRef = useRef(null);
    const layerRef = useRef(null);

    // Filter hierarchy mirrors the workforce monitor: Client -> Election ->
    // State -> LGA. The geo dropdowns only offer what is inside the chosen
    // election's scope (server-side filtered via ?election_id=).
    const isPlatformAdmin = (() => {
        try { return !localStorage.getItem('adminClientId'); } catch (e) { return false; }
    })();

    const [clients, setClients] = useState([]);
    const [elections, setElections] = useState([]);
    const [states, setStates] = useState([]);
    const [lgas, setLgas] = useState([]);
    const [filters, setFilters] = useState({
        client_id: '',
        election_id: '',
        state_id: '',
        lga_id: '',
    });
    const filtersRef = useRef(filters);
    filtersRef.current = filters;
    const focusSigRef = useRef('');

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

    const visibleElections = isPlatformAdmin && filters.client_id
        ? elections.filter(e => e.client_id === filters.client_id)
        : elections;

    const geoQuery = (electionIdArg = filters.election_id) =>
        electionIdArg ? `?election_id=${electionIdArg}` : '';

    // Pre-selection from the Elections page ("Live map" button).
    useEffect(() => {
        if (electionId && electionId !== filtersRef.current.election_id) {
            applyFilter('election_id', electionId);
        }
    }, [electionId]);

    // Client admins must always watch a specific election (the backend
    // refuses the nationwide view for them) — default to their first race.
    useEffect(() => {
        if (!isPlatformAdmin && !filtersRef.current.election_id && elections.length > 0) {
            applyFilter('election_id', elections[0].id);
        }
    }, [elections]);

    const applyFilter = (key, value) => {
        setFilters(prev => {
            const next = { ...prev, [key]: value };
            if (key === 'client_id') return { ...next, election_id: '', state_id: '', lga_id: '' };
            if (key === 'election_id') return { ...next, state_id: '', lga_id: '' };
            if (key === 'state_id') return { ...next, lga_id: '' };
            return next;
        });

        if (key === 'client_id') {
            setStates([]); setLgas([]);
        }
        if (key === 'election_id') {
            setLgas([]);
            if (value) {
                fetch(`/admin/geo/states${geoQuery(value)}`)
                    .then(r => (r.ok ? r.json() : []))
                    .then(setStates)
                    .catch(() => setStates([]));
            } else {
                setStates([]);
            }
        }
        if (key === 'state_id') {
            if (value) {
                fetch(`/admin/geo/states/${value}/lgas${geoQuery()}`)
                    .then(r => (r.ok ? r.json() : []))
                    .then(setLgas)
                    .catch(() => setLgas([]));
            } else {
                setLgas([]);
            }
        }
    };

    const fetchData = async () => {
        const f = filtersRef.current;
        try {
            const qs = new URLSearchParams();
            if (f.election_id) qs.append('election_id', f.election_id);
            if (f.state_id) qs.append('state_id', f.state_id);
            if (f.lga_id) qs.append('lga_id', f.lga_id);
            const res = await fetch(`/admin/monitor/map?${qs.toString()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const d = await res.json();
            setData(d);
            setLastRefresh(new Date());
            setLoadError(null);
        } catch (e) {
            setLoadError(e.message);
        }
    };

    useEffect(() => {
        setData(null);
        fetchData();
        const t = setInterval(fetchData, 60000); // live-ish: mirrors the server 30s cache
        return () => clearInterval(t);
    }, [filters.election_id, filters.state_id, filters.lga_id]);

    useEffect(() => {
        if (!mapElRef.current || mapRef.current) return;
        const map = L.map(mapElRef.current, { minZoom: 6 });
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);
        map.fitBounds(NIGERIA_BOUNDS);
        layerRef.current = L.layerGroup().addTo(map);

        // Legend
        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = () => {
            const div = L.DomUtil.create('div', 'info legend');
            div.style.cssText = 'background:rgba(255,255,255,.92);padding:10px 12px;border-radius:10px;font:12px/1.5 sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.2)';
            div.innerHTML = '<b>Operational status</b><br>' + Object.entries(STATUS).map(([k, v]) =>
                `<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:${v.color};margin-right:6px"></span>${v.label}`
            ).join('<br>');
            return div;
        };
        legend.addTo(map);
        mapRef.current = map;
        return () => { map.remove(); mapRef.current = null; };
    }, []);

    useEffect(() => {
        if (!data || !layerRef.current) return;
        layerRef.current.clearLayers();

        data.unassigned_clusters.forEach(c => {
            const r = Math.min(6 + Math.sqrt(c.count) * 0.55, 26);
            L.circleMarker([c.lat, c.lng], {
                radius: r, color: STATUS.unassigned.color,
                fillColor: STATUS.unassigned.color, fillOpacity: 0.45, weight: 1
            }).addTo(layerRef.current).bindPopup(
                `<b>${c.lga}</b> LGA, ${c.state}<br/>${c.count} polling unit${c.count === 1 ? '' : 's'} without an agent`
            );
        });

        data.markers.forEach(m => {
            const s = STATUS[m.status] || STATUS.assigned;
            L.circleMarker([m.lat, m.lng], {
                radius: 7, color: s.color, fillColor: s.color, fillOpacity: 0.85, weight: 1.5
            }).addTo(layerRef.current).bindPopup(
                `<b>${m.pu_code}</b> — ${m.name || ''}<br/>Status: <b>${s.label}</b>`
            );
        });

        // Re-frame the view only when the geo FOCUS changes (not on every
        // 60s data refresh) so we never fight the user's own pan/zoom.
        const f = filtersRef.current;
        const sig = `${f.election_id}|${f.state_id}|${f.lga_id}`;
        if (sig !== focusSigRef.current) {
            focusSigRef.current = sig;
            const pts = [
                ...data.unassigned_clusters.map(c => [c.lat, c.lng]),
                ...data.markers.map(m => [m.lat, m.lng]),
            ];
            if ((f.state_id || f.lga_id) && pts.length > 0) {
                mapRef.current.fitBounds(pts);
            } else {
                mapRef.current.fitBounds(NIGERIA_BOUNDS);
            }
        }
    }, [data]);

    const c = data?.counters || {};

    return (
        <div className="space-y-4 animate-in slide-in-from-right duration-500">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center space-x-3">
                    {setActiveView && (
                        <button onClick={() => setActiveView('workforce')}
                            className="p-2 rounded-xl bg-gray-100 dark:bg-gray-800 text-gray-500 hover:text-brand transition-colors" title="Back to monitoring">
                            <ArrowLeft className="w-5 h-5" />
                        </button>
                    )}
                    <div>
                        <h3 className="font-bold text-gray-900 dark:text-white">Live Operational Map</h3>
                        <p className="text-[10px] text-gray-400 font-bold uppercase">
                            {lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()}` : 'Loading…'}
                        </p>
                    </div>
                </div>
                <button onClick={fetchData}
                    className="px-4 py-2 bg-brand/10 text-brand text-sm font-bold rounded-lg hover:bg-brand/20 transition-colors flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Filter hierarchy: client -> election -> state -> lga */}
            <div className="bg-white dark:bg-gray-950 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-sm p-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {isPlatformAdmin && (
                        <select
                            value={filters.client_id}
                            onChange={(e) => applyFilter('client_id', e.target.value)}
                            className="px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand"
                        >
                            <option value="">All Clients</option>
                            {clients.map(cl => <option key={cl.id} value={cl.id}>{cl.name}</option>)}
                        </select>
                    )}
                    <select
                        value={filters.election_id}
                        onChange={(e) => applyFilter('election_id', e.target.value)}
                        className="px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand"
                    >
                        {isPlatformAdmin
                            ? <option value="">Nationwide (all elections)</option>
                            : <option value="">Select election</option>}
                        {visibleElections.map(el => <option key={el.id} value={el.id}>{el.name} ({el.code})</option>)}
                    </select>
                    <select
                        value={filters.state_id}
                        onChange={(e) => applyFilter('state_id', e.target.value)}
                        disabled={!filters.election_id}
                        className="px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
                    >
                        <option value="">{filters.election_id ? 'All States' : 'Pick an election first'}</option>
                        {states.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    <select
                        value={filters.lga_id}
                        onChange={(e) => applyFilter('lga_id', e.target.value)}
                        disabled={!filters.state_id}
                        className="px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
                    >
                        <option value="">All LGAs</option>
                        {lgas.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </select>
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                {Object.entries(STATUS).map(([k, v]) => (
                    <div key={k} className="bg-white dark:bg-gray-950 border border-gray-100 dark:border-gray-800 rounded-xl p-3 text-center">
                        <p className="text-lg font-black" style={{ color: v.color }}>{c[k]?.toLocaleString() ?? '—'}</p>
                        <p className="text-[9px] font-bold uppercase text-gray-400 leading-tight">{v.label}</p>
                    </div>
                ))}
                {(c.no_coordinates > 0) && (
                    <div className="col-span-2 md:col-span-6 text-[10px] text-gray-400 font-bold uppercase">
                        {c.no_coordinates?.toLocaleString()} polling units have no published INEC coordinates and are not shown on the map.
                    </div>
                )}
            </div>

            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                className="bg-white dark:bg-gray-950 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-xl overflow-hidden">
                {loadError ? (
                    <div className="p-12 text-center text-sm text-red-500">Failed to load map data: {loadError}</div>
                ) : (
                    <div ref={mapElRef} className="h-[60vh] w-full z-0" />
                )}
            </motion.div>
        </div>
    );
};

export default MonitorMap;
