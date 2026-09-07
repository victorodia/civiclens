import React, { useState, useEffect } from 'react';
import { Settings, CheckCircle, RefreshCw, Edit3, Trash2, AlertTriangle, ShieldAlert } from 'lucide-react';
import { motion } from 'framer-motion';
import { useNotification } from '../contexts/NotificationContext';

const ElectionConfig = () => {
    const { showNotification } = useNotification();
    const [config, setConfig] = useState({
        party_a_name: '',
        party_b_name: '',
        party_c_name: '',
        election_name: ''
    });
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);

    useEffect(() => {
        fetchConfig();
    }, []);

    const fetchConfig = async () => {
        setIsLoading(true);
        try {
            const res = await fetch('http://127.0.0.1:8001/admin/election-config');
            if (res.ok) {
                const data = await res.json();
                setConfig(data);
            }
        } catch (e) {
            console.error('Failed to load election config', e);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSave = async (e) => {
        e.preventDefault();
        setIsSaving(true);
        try {
            const res = await fetch('http://127.0.0.1:8001/admin/election-config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const data = await res.json();
            if (res.ok) {
                showNotification('Party names updated successfully. Changes will reflect in real-time on the agent portal.', 'success');
            } else {
                showNotification(data.detail || 'Update failed.', 'error');
            }
        } catch (e) {
            showNotification('Network error. Could not reach the backend.', 'error');
        } finally {
            setIsSaving(false);
        }
    };

    const handleFactoryReset = async () => {
        const password = await showDialog({
            title: "Nuclear System Reset",
            message: "DANGER: This will purge ALL results and agent accounts. Enter Admin Security Key to confirm:"
        });

        if (!password) return;

        setIsSaving(true);
        try {
            const res = await fetch('http://127.0.0.1:8001/admin/factory-reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_password: password })
            });
            const data = await res.json();
            if (res.ok) {
                showNotification('SYSTEM PURGED. All results and agents have been deleted.', 'success');
                fetchConfig(); // Refresh state
            } else {
                showNotification(data.detail || 'Reset failed.', 'error');
            }
        } catch (e) {
            showNotification('Network error during nuclear operation.', 'error');
        } finally {
            setIsSaving(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center p-20">
                <RefreshCw className="w-8 h-8 animate-spin text-brand" />
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Header */}
            <div className="bg-white dark:bg-gray-900 p-6 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-xl">
                <div className="flex items-center space-x-3 mb-6">
                    <div className="bg-brand/10 p-2 rounded-xl">
                        <Settings className="w-5 h-5 text-brand" />
                    </div>
                    <div>
                        <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tight">Election Configuration</h3>
                        <p className="text-[10px] text-gray-500 font-bold uppercase">Party names — propagated in real-time to all agent portals</p>
                    </div>
                </div>

                <form onSubmit={handleSave} className="space-y-5">
                    {/* Election Name */}
                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Election Name</label>
                        <div className="relative">
                            <Edit3 className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                            <input
                                type="text"
                                value={config.election_name}
                                onChange={(e) => setConfig({ ...config, election_name: e.target.value })}
                                placeholder="e.g. 2027 Presidential Election"
                                required
                                className="w-full pl-11 pr-4 py-3.5 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-sm font-bold outline-none focus:ring-2 focus:ring-brand transition-all"
                            />
                        </div>
                    </div>

                    <div className="border-t border-gray-100 dark:border-gray-800 pt-5">
                        <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-4">Contesting Parties</p>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                            <div className="space-y-1.5">
                                <label className="text-[9px] font-black text-brand uppercase tracking-widest flex items-center space-x-1.5">
                                    <span className="w-5 h-5 bg-brand text-white rounded-full text-[8px] flex items-center justify-center font-black">A</span>
                                    <span>Party A Name</span>
                                </label>
                                <input
                                    type="text"
                                    value={config.party_a_name}
                                    onChange={(e) => setConfig({ ...config, party_a_name: e.target.value })}
                                    placeholder="e.g. APC"
                                    required
                                    className="w-full px-4 py-3.5 rounded-2xl border border-brand/30 bg-brand/5 dark:bg-brand/10 text-sm font-bold outline-none focus:ring-2 focus:ring-brand transition-all"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[9px] font-black text-blue-600 uppercase tracking-widest flex items-center space-x-1.5">
                                    <span className="w-5 h-5 bg-blue-600 text-white rounded-full text-[8px] flex items-center justify-center font-black">B</span>
                                    <span>Party B Name</span>
                                </label>
                                <input
                                    type="text"
                                    value={config.party_b_name}
                                    onChange={(e) => setConfig({ ...config, party_b_name: e.target.value })}
                                    placeholder="e.g. PDP"
                                    required
                                    className="w-full px-4 py-3.5 rounded-2xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[9px] font-black text-green-600 uppercase tracking-widest flex items-center space-x-1.5">
                                    <span className="w-5 h-5 bg-green-600 text-white rounded-full text-[8px] flex items-center justify-center font-black">C</span>
                                    <span>Party C Name</span>
                                </label>
                                <input
                                    type="text"
                                    value={config.party_c_name}
                                    onChange={(e) => setConfig({ ...config, party_c_name: e.target.value })}
                                    placeholder="e.g. LP"
                                    required
                                    className="w-full px-4 py-3.5 rounded-2xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 text-sm font-bold outline-none focus:ring-2 focus:ring-green-500 transition-all"
                                />
                            </div>
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={isSaving}
                        className="w-full bg-brand text-white py-4 rounded-2xl font-black uppercase text-[10px] tracking-widest shadow-lg shadow-brand/20 active:scale-98 transition-all disabled:opacity-50 flex items-center justify-center space-x-2"
                    >
                        {isSaving
                            ? <><RefreshCw className="w-4 h-4 animate-spin" /><span>Saving...</span></>
                            : <><CheckCircle className="w-4 h-4" /><span>Save Configuration</span></>
                        }
                    </button>
                </form>
            </div>

            <div className="bg-white dark:bg-gray-900 p-6 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-xl">
                <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-4">Live Preview — Agent Form Labels</p>
                <div className="grid grid-cols-3 gap-3">
                    {[
                        { label: config.party_a_name || 'Party A', color: 'brand' },
                        { label: config.party_b_name || 'Party B', color: 'blue-600' },
                        { label: config.party_c_name || 'Party C', color: 'green-600' },
                    ].map((p, i) => (
                        <div key={i} className="bg-gray-50 dark:bg-gray-800 p-4 rounded-2xl text-center border border-gray-100 dark:border-gray-700">
                            <p className="text-[10px] font-black text-gray-900 dark:text-white uppercase tracking-wider mb-1">{p.label} Votes</p>
                            <p className="text-lg font-black text-gray-300">—</p>
                        </div>
                    ))}
                </div>
            </div>

            {/* Danger Zone */}
            <div className="bg-red-50 dark:bg-red-950/20 p-6 rounded-3xl border border-red-200 dark:border-red-900/30 shadow-xl overflow-hidden relative group">
                <div className="absolute -right-4 -top-4 opacity-5 group-hover:opacity-10 transition-opacity">
                    <ShieldAlert className="w-32 h-32 text-red-600" />
                </div>

                <div className="flex items-center space-x-3 mb-4">
                    <div className="bg-red-600 p-2 rounded-xl text-white">
                        <AlertTriangle className="w-5 h-5" />
                    </div>
                    <div>
                        <h3 className="font-black text-red-900 dark:text-red-400 uppercase tracking-tight">Administrative Danger Zone</h3>
                        <p className="text-[10px] text-red-600/70 font-bold uppercase">Irreversible System Purgation Controls</p>
                    </div>
                </div>

                <div className="bg-white/50 dark:bg-black/20 p-4 rounded-2xl border border-red-100 dark:border-red-900/40 mb-6">
                    <p className="text-xs text-red-800 dark:text-red-300 leading-relaxed">
                        <span className="font-black uppercase mr-1">Warning:</span>
                        Initiating a **Factory Reset** will permanently delete all uploaded results, evidence photos/videos, and field agent profiles. This action is intended for use **only** between election cycles or when decommissioning a region.
                    </p>
                </div>

                <button
                    onClick={handleFactoryReset}
                    disabled={isSaving}
                    className="w-full sm:w-auto px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white rounded-2xl font-black uppercase text-[10px] tracking-widest shadow-lg shadow-red-900/20 active:scale-95 transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
                >
                    <Trash2 className="w-4 h-4" />
                    <span>Initiate Factory Reset</span>
                </button>
            </div>
        </div>
    );
};

export default ElectionConfig;
