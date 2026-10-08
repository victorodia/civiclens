import React, { useState, useEffect } from 'react';
import { Users, Plus, Shield, RefreshCw, Mail, Lock, UserCircle, Trash2, Power, AlertTriangle } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const SystemUsers = () => {
    const { showNotification } = useNotification();
    const [users, setUsers] = useState([]);
    const [roles, setRoles] = useState([]);
    const [confirmAction, setConfirmAction] = useState(null);
    const [adminEmail, setAdminEmail] = useState('');
    const [adminPassword, setAdminPassword] = useState('');
    const [adminMfa, setAdminMfa] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({
        email: '',
        full_name: '',
        password: '',
        role: 'analyst'
    });
    const [isSubmitting, setIsSubmitting] = useState(false);

    const requestDelete = (user) => {
        setConfirmAction({
            type: 'delete',
            user: user,
            title: 'Delete System User',
            message: `Enter your admin credentials to confirm deletion of ${user.full_name}.`
        });
    };

    const requestToggle = (user) => {
        setConfirmAction({
            type: 'toggle',
            user: user,
            title: user.is_active ? 'Suspend User' : 'Reactivate User',
            message: `Enter your admin credentials to confirm ${user.is_active ? 'suspension' : 'reactivation'} of ${user.full_name}.`
        });
    };

    const handleRoleChange = (userId, newRole) => {
        const user = users.find(u => u.id === userId);
        setConfirmAction({
            type: 'role',
            user: user,
            newRole: newRole,
            title: 'Update User Role',
            message: `Enter your admin credentials to change ${user.full_name}'s role to ${newRole.toUpperCase()}.`
        });
    };

    const executeConfirm = async () => {
        if (!confirmAction) return;
        if (!adminEmail || !adminPassword) {
            showNotification("Email and password are required.", "error");
            return;
        }

        const { type, user, newRole } = confirmAction;
        
        const headers = {
            'Content-Type': 'application/json',
            'X-Admin-Email': adminEmail,
            'X-Admin-Password': adminPassword,
            'X-Admin-Mfa': adminMfa || ''
        };

        try {
            let res;
            if (type === 'delete') {
                res = await fetch(`/admin/system/users/${user.id}`, { method: 'DELETE', headers });
            } else if (type === 'toggle') {
                res = await fetch(`/admin/system/users/${user.id}`, {
                    method: 'PATCH',
                    headers,
                    body: JSON.stringify({ is_active: !user.is_active })
                });
            } else if (type === 'role') {
                res = await fetch(`/admin/system/users/${user.id}`, {
                    method: 'PATCH',
                    headers,
                    body: JSON.stringify({ role: newRole })
                });
            }

            if (res.ok) {
                showNotification(`Action completed successfully.`, "success");
                setConfirmAction(null);
                setAdminPassword('');
                setAdminMfa('');
                fetchUsers();
        fetchRoles();
            } else {
                const err = await res.json();
                showNotification(err.detail || "Authorization failed", "error");
            }
        } catch (error) {
            showNotification("Network error", "error");
        }
    };

    useEffect(() => {
        fetchUsers();
        fetchRoles();
    }, []);

    
    const fetchRoles = async () => {
        try {
            const res = await fetch('/admin/system/roles');
            if (res.ok) {
                const data = await res.json();
                setRoles(data);
            }
        } catch (error) {
            console.error("Failed to fetch roles", error);
        }
    };

    const fetchUsers = async () => {
        setIsLoading(true);
        try {
            const res = await fetch('/admin/system/users');
            if (res.ok) {
                const data = await res.json();
                setUsers(data);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            const res = await fetch('/admin/system/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
            const data = await res.json();
            if (res.ok) {
                showNotification('System user created successfully', 'success');
                setShowForm(false);
                setFormData({ email: '', full_name: '', password: '', role: 'analyst' });
                fetchUsers();
        fetchRoles();
            } else {
                showNotification(data.detail || 'Failed to create user', 'error');
            }
        } catch (e) {
            showNotification('Network error', 'error');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500 mt-6">
            <div className="bg-white dark:bg-gray-900 p-6 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-xl">
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center space-x-3">
                        <div className="bg-brand/10 p-2 rounded-xl">
                            <Shield className="w-5 h-5 text-brand" />
                        </div>
                        <div>
                            <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tight">System Access Management</h3>
                            <p className="text-[10px] text-gray-500 font-bold uppercase">Manage roles for Admin and Situation Room staff</p>
                        </div>
                    </div>
                    <button
                        onClick={() => setShowForm(!showForm)}
                        className="bg-brand hover:bg-teal-700 text-white px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider flex items-center space-x-2 transition-colors"
                    >
                        <Plus className="w-4 h-4" />
                        <span>New User</span>
                    </button>
                </div>

                {showForm && (
                    <form onSubmit={handleSubmit} className="mb-8 p-5 bg-gray-50 dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 space-y-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Full Name</label>
                                <div className="relative">
                                    <UserCircle className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                                    <input type="text" value={formData.full_name} onChange={(e) => setFormData({...formData, full_name: e.target.value})} required className="w-full pl-9 pr-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-sm font-bold outline-none focus:ring-2 focus:ring-brand" />
                                </div>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Email Address</label>
                                <div className="relative">
                                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                                    <input type="email" value={formData.email} onChange={(e) => setFormData({...formData, email: e.target.value})} required className="w-full pl-9 pr-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-sm font-bold outline-none focus:ring-2 focus:ring-brand" />
                                </div>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Initial Password</label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                                    <input type="text" value={formData.password} onChange={(e) => setFormData({...formData, password: e.target.value})} required className="w-full pl-9 pr-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-sm font-bold outline-none focus:ring-2 focus:ring-brand" />
                                </div>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Access Role</label>
                                <select value={formData.role} onChange={(e) => setFormData({...formData, role: e.target.value})} className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:border-brand transition-colors text-sm font-bold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                                                {roles.map(r => (
                                                    <option key={r.name} value={r.name}>{r.name.toUpperCase()}</option>
                                                ))}
</select>
                            </div>
                        </div>
                        <div className="flex justify-end pt-2">
                            <button type="submit" disabled={isSubmitting} className="bg-gray-900 dark:bg-white text-white dark:text-black px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center space-x-2">
                                {isSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <span>Create User Profile</span>}
                            </button>
                        </div>
                    </form>
                )}

                {isLoading ? (
                    <div className="flex justify-center p-8"><RefreshCw className="w-6 h-6 animate-spin text-brand" /></div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="border-b border-gray-100 dark:border-gray-800 text-[10px] uppercase tracking-wider text-gray-400 font-black">
                                    <th className="py-3 px-4">User</th>
                                    <th className="py-3 px-4">Role</th>
                                    <th className="py-3 px-4">Status</th>
                                    <th className="py-3 px-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="text-sm font-medium">
                                {users.map((user) => (
                                    <tr key={user.id} className="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/50 dark:hover:bg-gray-800/20 transition-colors">
                                        <td className="py-3 px-4">
                                            <div className="font-bold text-gray-900 dark:text-white">{user.full_name}</div>
                                            <div className="text-xs text-gray-500">{user.email}</div>
                                        </td>
                                        <td className="py-3 px-4">
                                            
                                            <select 
                                                value={user.role} 
                                                onChange={(e) => handleRoleChange(user.id, e.target.value)}
                                                className={`px-2 py-1 rounded-md text-[10px] uppercase tracking-wider font-bold outline-none cursor-pointer bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`}
                                            >
                                                {roles.map(r => (
                                                    <option key={r.name} value={r.name}>{r.name.toUpperCase()}</option>
                                                ))}
                                            </select>

                                        </td>
                                        <td className="py-3 px-4">
                                            <div className="flex items-center space-x-2">
                                                <div className={`w-2 h-2 rounded-full ${user.is_active ? 'bg-green-500' : 'bg-red-500'}`}></div>
                                                <span className="text-xs text-gray-600 dark:text-gray-400">{user.is_active ? 'Active' : 'Suspended'}</span>
                                            </div>
                                        </td>
                                        <td className="py-3 px-4 text-right">
                                            <div className="flex items-center justify-end space-x-3">
                                                <button onClick={() => requestToggle(user)} title={user.is_active ? "Suspend User" : "Reactivate User"} className={`transition-colors ${user.is_active ? 'text-amber-500 hover:text-amber-600' : 'text-green-500 hover:text-green-600'}`}>
                                                    <Power className="w-4 h-4" />
                                                </button>
                                                <button onClick={() => requestDelete(user)} title="Delete User" className="text-red-500 hover:text-red-600 transition-colors">
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                                {users.length === 0 && (
                                    <tr><td colSpan="3" className="py-6 text-center text-gray-500 text-xs font-bold uppercase tracking-widest">No additional system users found</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Custom Confirmation Modal */}
            {confirmAction && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/40 dark:bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-6 rounded-3xl shadow-2xl max-w-sm w-full animate-in zoom-in-95 duration-200">
                        <div className="flex items-center space-x-3 mb-4">
                            <div className={`p-3 rounded-xl ${confirmAction.type === 'delete' ? 'bg-red-50 dark:bg-red-900/20 text-red-500' : 'bg-amber-50 dark:bg-amber-900/20 text-amber-500'}`}>
                                <AlertTriangle className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="text-sm font-black text-gray-900 dark:text-white uppercase tracking-wider">{confirmAction.title}</h3>
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Action Required</p>
                            </div>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-6 leading-relaxed">
                            {confirmAction.message}
                        </p>
                        
                        <div className="space-y-4 mb-6">
                            <div className="space-y-1">
                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Admin Email</label>
                                <input type="email" value={adminEmail} onChange={e => setAdminEmail(e.target.value)} className="w-full px-3 py-2 text-sm font-bold bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:border-brand transition-colors" placeholder="admin@civiclens.io" />
                            </div>
                            <div className="space-y-1">
                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Admin Password</label>
                                <input type="password" value={adminPassword} onChange={e => setAdminPassword(e.target.value)} className="w-full px-3 py-2 text-sm font-bold bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:border-brand transition-colors" placeholder="••••••••••" />
                            </div>
                            <div className="space-y-1">
                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">MFA Token (If Enabled)</label>
                                <input type="text" value={adminMfa} onChange={e => setAdminMfa(e.target.value)} maxLength="6" className="w-full px-3 py-2 text-sm font-black tracking-widest bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:border-brand transition-colors text-brand placeholder:text-gray-400 placeholder:tracking-normal" placeholder="000000" />
                            </div>
                        </div>

                        <div className="flex space-x-3">
                            <button 
                                onClick={() => { setConfirmAction(null); setAdminPassword(''); setAdminMfa(''); }} 
                                className="flex-1 py-3 px-4 rounded-xl text-xs font-black uppercase tracking-widest bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                            >
                                Cancel
                            </button>
                            <button 
                                onClick={executeConfirm}
                                className={`flex-1 py-3 px-4 rounded-xl text-xs font-black uppercase tracking-widest text-white transition-colors ${confirmAction.type === 'delete' ? 'bg-red-500 hover:bg-red-600 shadow-lg shadow-red-500/20' : 'bg-brand hover:bg-brand-dark shadow-lg shadow-brand/20'}`}
                            >
                                Verify & Proceed
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default SystemUsers;
