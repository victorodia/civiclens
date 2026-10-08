import React, { useState, useEffect } from 'react';
import { Shield, Plus, Trash2, CheckCircle2, Save, X, AlertTriangle } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const AVAILABLE_PERMISSIONS = [
    { id: 'view_live_telemetry', label: 'View Live Telemetry', desc: 'Can see incoming results in real-time' },
    { id: 'view_historical_data', label: 'View Historical Data', desc: 'Can access past election archives' },
    { id: 'approve_results', label: 'Approve Results', desc: 'Can mark results as mathematically verified' },
    { id: 'flag_results', label: 'Flag Results', desc: 'Can dispute or flag a result for review' },
    { id: 'delete_results', label: 'Delete Results', desc: 'Can hard-delete an uploaded result' },
    { id: 'export_data', label: 'Export Data', desc: 'Can download CSV/PDF reports' },
    { id: 'provision_agents', label: 'Provision Agents', desc: 'Can create or edit on-the-ground agent accounts' },
    { id: 'suspend_agents', label: 'Suspend Agents', desc: 'Can block agents from uploading' },
    { id: 'view_agent_locations', label: 'View Agent Locations', desc: 'Can see GPS tracking of agents' },
    { id: 'manage_system_users', label: 'Manage System Users', desc: 'Can create/delete admin portal users' },
    { id: 'manage_roles', label: 'Manage Roles', desc: 'Can create custom RBAC roles' },
    { id: 'modify_election_config', label: 'Modify Election Config', desc: 'Can change geofencing or polling unit data' },
    { id: 'view_audit_logs', label: 'View Audit Logs', desc: 'Can see the immutable action history' },
    { id: 'manage_billing', label: 'Manage Billing', desc: 'Can add funds or view invoices' },
    { id: 'trigger_factory_reset', label: 'Trigger Factory Reset', desc: 'Can wipe all data (Requires Super Admin)' },
    { id: 'manage_api_keys', label: 'Manage API Keys', desc: 'Can generate tokens for 3rd-party integrations' }
];

const RoleManagement = () => {
    const [roles, setRoles] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isFormOpen, setIsFormOpen] = useState(false);
    const { showNotification } = useNotification();

    const [formData, setFormData] = useState({
        name: '',
        permissions: []
    });

    useEffect(() => {
        fetchRoles();
    }, []);

    const fetchRoles = async () => {
        setIsLoading(true);
        try {
            const res = await fetch('/admin/system/roles');
            if (res.ok) {
                const data = await res.json();
                setRoles(data);
            } else {
                showNotification('Failed to fetch roles', 'error');
            }
        } catch (e) {
            showNotification('Network error', 'error');
        } finally {
            setIsLoading(false);
        }
    };

    const handleTogglePermission = (permId) => {
        setFormData(prev => {
            if (prev.permissions.includes(permId)) {
                return { ...prev, permissions: prev.permissions.filter(p => p !== permId) };
            } else {
                return { ...prev, permissions: [...prev.permissions, permId] };
            }
        });
    };

    const handleCreateRole = async (e) => {
        e.preventDefault();
        
        if (!formData.name.trim() || formData.permissions.length === 0) {
            showNotification('Role name and at least 1 permission required', 'error');
            return;
        }

        try {
            const res = await fetch('/admin/system/roles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: formData.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_'),
                    permissions: formData.permissions
                })
            });

            if (res.ok) {
                showNotification('Role created successfully', 'success');
                setIsFormOpen(false);
                setFormData({ name: '', permissions: [] });
                fetchRoles();
            } else {
                const data = await res.json();
                showNotification(data.detail || 'Failed to create role', 'error');
            }
        } catch (err) {
            showNotification('Network error', 'error');
        }
    };

    const handleDeleteRole = async (roleName) => {
        if (roleName === 'admin') {
            showNotification('Cannot delete root admin role', 'error');
            return;
        }
        
        // Use standard browser confirm for simplicity since this is an admin tool,
        // but normally we'd use the custom modal.
        if (window.confirm(`Are you sure you want to delete the role '${roleName}'? Users with this role might lose access.`)) {
            try {
                const res = await fetch(`/admin/system/roles/${roleName}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    showNotification('Role deleted successfully', 'success');
                    fetchRoles();
                } else {
                    const data = await res.json();
                    showNotification(data.detail || 'Failed to delete role', 'error');
                }
            } catch (err) {
                showNotification('Network error', 'error');
            }
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-black text-gray-900 dark:text-white uppercase tracking-wider">Role Matrix</h2>
                    <p className="text-xs font-bold text-gray-400 mt-1 uppercase tracking-widest">Custom access control configurations</p>
                </div>
                {!isFormOpen && (
                    <button 
                        onClick={() => setIsFormOpen(true)}
                        className="flex items-center space-x-2 px-4 py-3 bg-brand text-white rounded-xl hover:bg-brand-dark transition-colors shadow-lg shadow-brand/20"
                    >
                        <Plus className="w-4 h-4" />
                        <span className="text-[10px] font-black uppercase tracking-widest">Create Role</span>
                    </button>
                )}
            </div>

            {isFormOpen && (
                <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-3xl p-6 shadow-xl mb-8 animate-in fade-in slide-in-from-top-4 duration-300">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center space-x-3 text-brand">
                            <Shield className="w-5 h-5" />
                            <h3 className="text-sm font-black uppercase tracking-wider text-gray-900 dark:text-white">New Role Definition</h3>
                        </div>
                        <button onClick={() => setIsFormOpen(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    <form onSubmit={handleCreateRole}>
                        <div className="mb-6">
                            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Role Identifier</label>
                            <input 
                                type="text" 
                                value={formData.name}
                                onChange={e => setFormData({ ...formData, name: e.target.value })}
                                className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:border-brand transition-colors text-sm font-bold placeholder:font-medium"
                                placeholder="e.g. state_coordinator"
                                required
                            />
                            <p className="text-[10px] font-medium text-amber-500 mt-2">Only letters, numbers, and underscores allowed.</p>
                        </div>

                        <div className="mb-8">
                            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4">Micro-Permissions</label>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {AVAILABLE_PERMISSIONS.map(perm => (
                                    <div 
                                        key={perm.id}
                                        onClick={() => handleTogglePermission(perm.id)}
                                        className={`p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                                            formData.permissions.includes(perm.id) 
                                                ? 'bg-brand/10 border-brand shadow-sm' 
                                                : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 hover:border-brand/50'
                                        }`}
                                    >
                                        <div className="flex items-start justify-between">
                                            <div className="pr-2">
                                                <h4 className={`text-[10px] font-black uppercase tracking-wider mb-1 ${formData.permissions.includes(perm.id) ? 'text-brand' : 'text-gray-700 dark:text-gray-300'}`}>
                                                    {perm.label}
                                                </h4>
                                                <p className="text-[9px] font-medium text-gray-500 leading-relaxed">{perm.desc}</p>
                                            </div>
                                            <div className={`mt-0.5 rounded-full ${formData.permissions.includes(perm.id) ? 'text-brand' : 'text-gray-200 dark:text-gray-700'}`}>
                                                <CheckCircle2 className="w-4 h-4" />
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="flex justify-end border-t border-gray-100 dark:border-gray-800 pt-6">
                            <button 
                                type="submit"
                                className="flex items-center space-x-2 px-6 py-3 bg-gray-900 dark:bg-white text-white dark:text-gray-900 rounded-xl hover:bg-gray-800 dark:hover:bg-gray-100 transition-colors shadow-lg"
                            >
                                <Save className="w-4 h-4" />
                                <span className="text-[10px] font-black uppercase tracking-widest">Save Role</span>
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div className="grid grid-cols-1 gap-4">
                {isLoading ? (
                    <div className="flex justify-center p-8"><div className="animate-spin w-6 h-6 border-2 border-brand border-t-transparent rounded-full"></div></div>
                ) : (
                    roles.map(role => (
                        <div key={role.name} className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-2xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm hover:shadow-md transition-all">
                            <div className="flex-shrink-0">
                                <div className="flex items-center space-x-3 mb-1">
                                    <div className="p-2 bg-brand/10 text-brand rounded-lg">
                                        <Shield className="w-4 h-4" />
                                    </div>
                                    <h3 className="text-sm font-black text-gray-900 dark:text-white uppercase tracking-wider">{role.name}</h3>
                                </div>
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest ml-11">{role.permissions.length} Permissions Active</p>
                            </div>

                            <div className="flex-1 flex flex-wrap gap-1.5 md:px-6">
                                {role.permissions.map(perm => (
                                    <span key={perm} className="px-2 py-1 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 text-[9px] font-bold uppercase tracking-wider rounded-md border border-gray-200 dark:border-gray-700">
                                        {perm}
                                    </span>
                                ))}
                            </div>

                            <div className="flex-shrink-0 flex items-center justify-end">
                                {role.name !== 'admin' && (
                                    <button 
                                        onClick={() => handleDeleteRole(role.name)}
                                        className="p-2 text-red-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                                        title="Delete Role"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                )}
                                {role.name === 'admin' && (
                                    <div className="px-3 py-1 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg text-[9px] font-black uppercase tracking-widest flex items-center space-x-1">
                                        <AlertTriangle className="w-3 h-3" />
                                        <span>Immutable</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};

export default RoleManagement;
