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

const MonitorMap = ({ setActiveView }) => {
    const [data, setData] = useState(null);
    const [loadError, setLoadError] = useState(null);
    const [lastRefresh, setLastRefresh] = useState(null);
    const mapElRef = useRef(null);
    const mapRef = useRef(null);
    const layerRef = useRef(null);

    const fetchData = async () => {
        try {
            const res = await fetch('/admin/monitor/map');
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
        fetchData();
        const t = setInterval(fetchData, 60000); // live-ish: mirrors the server 30s cache
        return () => clearInterval(t);
    }, []);

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
