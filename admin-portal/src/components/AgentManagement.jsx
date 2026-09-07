import React, { useState, useEffect } from 'react';
import { Users, UserPlus, Shield, Key, CheckCircle, Search, RefreshCw, Trash2, Lock, X, Copy, Check, Eye, EyeOff } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNotification } from '../contexts/NotificationContext';

const AgentManagement = () => {
    const { showNotification, showDialog } = useNotification();
    const [agents, setAgents] = useState([]);
    const [isProvisioning, setIsProvisioning] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [newAgentEmail, setNewAgentEmail] = useState('');
    const [provisionedPwd, setProvisionedPwd] = useState(null);
    const [copied, setCopied] = useState(false);

    // Revocation state is now handled by NotificationContext
    const [isRevoking, setIsRevoking] = useState(false);

    const handleCopy = () => {
        if (!provisionedPwd) return;
        navigator.clipboard.writeText(provisionedPwd);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    // Geographic State
    const [states, setStates] = useState([]);
    const [lgas, setLgas] = useState([]);
    const [wards, setWards] = useState([]);
    const [pus, setPus] = useState([]);

    const [selectedState, setSelectedState] = useState('');
    const [selectedLga, setSelectedLga] = useState('');
    const [selectedWard, setSelectedWard] = useState('');
    const [selectedPu, setSelectedPu] = useState('');

    useEffect(() => {
        fetchAgents();
        fetchStates();
    }, []);

    const fetchStates = async () => {
        try {
            const res = await fetch('http://127.0.0.1:8001/admin/geo/states');
            if (res.ok) {
                const data = await res.json();
                setStates(Array.isArray(data) ? data : []);
            }
        } catch (e) {
            console.error(e);
            setStates([]);
        }
    };

    const handleStateChange = async (stateId) => {
        setSelectedState(stateId);
        setSelectedLga(''); setSelectedWard(''); setSelectedPu('');
        setLgas([]); setWards([]); setPus([]);
        if (!stateId) return;
        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/geo/states/${stateId}/lgas`);
            if (res.ok) {
                const data = await res.json();
                setLgas(Array.isArray(data) ? data : []);
            }
        } catch (e) { console.error(e); }
    };

    const handleLgaChange = async (lgaId) => {
        setSelectedLga(lgaId);
        setSelectedWard(''); setSelectedPu('');
        setWards([]); setPus([]);
        if (!lgaId) return;
        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/geo/lgas/${lgaId}/wards`);
            if (res.ok) {
                const data = await res.json();
                setWards(Array.isArray(data) ? data : []);
            }
        } catch (e) { console.error(e); }
    };

    const handleWardChange = async (wardId) => {
        setSelectedWard(wardId);
        setSelectedPu(''); setPus([]);
        if (!wardId) return;
        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/geo/wards/${wardId}/pus`);
            if (res.ok) {
                const data = await res.json();
                setPus(Array.isArray(data) ? data : []);
            }
        } catch (e) { console.error(e); }
    };

    const fetchAgents = async () => {
        try {
            const res = await fetch('http://127.0.0.1:8001/admin/agents');
            if (!res.ok) throw new Error("Failed to load agents list");
            const data = await res.json();
            setAgents(Array.isArray(data) ? data : []);
        } catch (err) {
            console.error("Failed to fetch agents", err);
            setAgents([]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleProvision = async (e) => {
        e.preventDefault();
        if (!selectedPu) return showNotification("Please select a Polling Unit first.", "warning");
        setIsProvisioning(true);
        setProvisionedPwd(null);

        try {
            const response = await fetch('http://127.0.0.1:8001/admin/provision-agents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    emails: [newAgentEmail],
                    polling_unit_id: selectedPu
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data?.detail || 'Provisioning failed');
            }

            if (data?.provisioned && data.provisioned[newAgentEmail]) {
                const tempPwd = data.provisioned[newAgentEmail];
                setProvisionedPwd(tempPwd);

                setAgents(prev => [...prev, {
                    id: Date.now().toString(),
                    name: 'New Agent',
                    email: newAgentEmail,
                    status: 'Pending Reset',
                    device: 'Pending'
                }]);
            } else {
                throw new Error("Credentials issued, but password not returned by server.");
            }
        } catch (err) {
            showNotification("Provisioning Error: " + err.message, "error");
        } finally {
            setIsProvisioning(false);
        }
    };

    const handleRevoke = async (agentId) => {
        const password = await showDialog({
            title: "Revoke Agent Access",
            message: "This action is irreversible. The personnel record will be scrubbed from the registry. Enter Admin Security Key to confirm:"
        });

        if (!password) return;
        setIsRevoking(true);

        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/agents/${agentId}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_password: password })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Revocation failed");

            // Update local state
            setAgents(agents.filter(a => a.id !== agentId));
            showNotification("Agent privileges revoked successfully. Personnel record purged.", "success");
        } catch (err) {
            showNotification("Revocation Error: " + err.message, "error");
        } finally {
            setIsRevoking(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center p-20 space-y-4">
                <RefreshCw className="w-8 h-8 text-brand animate-spin" />
                <p className="text-[10px] font-black uppercase tracking-widest text-gray-400">Synchronizing Workforce...</p>
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-in fade-in duration-500 relative">

            {/* Provisioning Section */}
            <div className="bg-white dark:bg-gray-900 p-6 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-xl">
                <div className="flex items-center space-x-3 mb-6">
                    <div className="bg-brand/10 p-2 rounded-xl">
                        <UserPlus className="w-5 h-5 text-brand" />
                    </div>
                    <div>
                        <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tight">Provision New Agent</h3>
                        <p className="text-[10px] text-gray-500 font-bold uppercase">Centralized Credential Issuance</p>
                    </div>
                </div>

                {!provisionedPwd ? (
                    <form onSubmit={handleProvision} className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                            <select
                                value={selectedState}
                                onChange={(e) => handleStateChange(e.target.value)}
                                className="px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand"
                            >
                                <option value="">Select State</option>
                                {states.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </select>

                            <select
                                value={selectedLga}
                                onChange={(e) => handleLgaChange(e.target.value)}
                                disabled={!selectedState}
                                className="px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
                            >
                                <option value="">Select LGA</option>
                                {lgas.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                            </select>

                            <select
                                value={selectedWard}
                                onChange={(e) => handleWardChange(e.target.value)}
                                disabled={!selectedLga}
                                className="px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
                            >
                                <option value="">Select Ward</option>
                                {wards.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>

                            <select
                                value={selectedPu}
                                onChange={(e) => setSelectedPu(e.target.value)}
                                disabled={!selectedWard}
                                className="px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
                            >
                                <option value="">Select Polling Unit</option>
                                {pus.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
                            </select>
                        </div>

                        <div className="flex space-x-2">
                            <input
                                type="email"
                                value={newAgentEmail}
                                onChange={(e) => setNewAgentEmail(e.target.value)}
                                placeholder="agent@civiclens.io"
                                required
                                className="flex-1 px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-sm outline-none focus:ring-2 focus:ring-brand transition-all"
                            />
                            <button
                                type="submit"
                                disabled={isProvisioning}
                                className="bg-brand text-white px-6 py-3 rounded-xl font-black uppercase tracking-widest text-[10px] shadow-lg shadow-brand/20 active:scale-95 transition-all disabled:opacity-50"
                            >
                                {isProvisioning ? 'Working...' : 'Create Agent'}
                            </button>
                        </div>
                    </form>
                ) : (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="bg-green-50 dark:bg-green-900/10 border border-green-100 dark:border-green-900/30 p-4 rounded-2xl"
                    >
                        <div className="flex items-start space-x-3">
                            <CheckCircle className="w-5 h-5 text-green-600 mt-0.5" />
                            <div className="flex-1">
                                <p className="text-sm font-black text-green-800 dark:text-green-400">Credentials Issued Successfully</p>
                                <p className="text-[10px] text-green-600 font-bold mt-1 uppercase">Share this temporary password with the agent:</p>
                                <div className="mt-3 bg-white dark:bg-gray-900 p-3 rounded-xl border border-green-200 dark:border-green-800 flex justify-between items-center group">
                                    <code className="text-brand font-black tracking-widest">{provisionedPwd}</code>
                                    <div className="flex items-center space-x-2">
                                        <button
                                            onClick={handleCopy}
                                            className="p-1.5 text-gray-400 hover:text-brand transition-colors rounded-lg hover:bg-brand/5"
                                            title="Copy to Clipboard"
                                        >
                                            {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
                                        </button>
                                        <button
                                            onClick={() => { setProvisionedPwd(null); setNewAgentEmail(''); }}
                                            className="text-[10px] font-black text-gray-400 hover:text-brand uppercase px-2 py-1 rounded-lg hover:bg-brand/5"
                                        > Done </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}
            </div>

            {/* Agent List */}
            <div className="bg-white dark:bg-gray-900 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-xl overflow-hidden">
                <div className="p-6 border-b border-gray-50 dark:border-gray-800 flex justify-between items-center">
                    <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tight flex items-center space-x-2">
                        <Users className="w-5 h-5 text-gray-400" />
                        <span>Active Workforce</span>
                    </h3>
                    <span className="bg-gray-100 dark:bg-gray-800 text-gray-500 text-[10px] px-2 py-1 rounded-full font-black">{Array.isArray(agents) ? agents.length : 0} AGENTS</span>
                </div>

                <div className="divide-y divide-gray-50 dark:divide-gray-800">
                    {Array.isArray(agents) && agents.map(agent => (
                        <div key={agent.id} className="p-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors">
                            <div className="flex items-center space-x-3">
                                <div className="w-10 h-10 bg-brand/5 rounded-full flex items-center justify-center">
                                    <Users className="w-5 h-5 text-brand" />
                                </div>
                                <div>
                                    <p className="text-xs font-black text-gray-900 dark:text-white">{agent.email}</p>
                                    <p className="text-[9px] text-gray-400 font-bold uppercase">{agent.status} • {agent.device}</p>
                                </div>
                            </div>
                            <div className="flex space-x-1">
                                <button className="p-2 text-gray-400 hover:text-brand transition-colors"><Shield className="w-4 h-4" /></button>
                                <button className="p-2 text-gray-400 hover:text-amber-500 transition-colors"><RefreshCw className="w-4 h-4" /></button>
                                <button
                                    onClick={() => handleRevoke(agent.id)}
                                    className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                                    title="Revoke Access"
                                >
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                    {(!agents || agents.length === 0) && (
                        <div className="p-12 text-center text-[10px] font-bold text-gray-400 uppercase tracking-widest italic opacity-50">
                            No agents provisioned in this sector.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AgentManagement;


