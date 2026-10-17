import React, { useState } from 'react';
import { Trash2, AlertTriangle, ShieldAlert } from 'lucide-react';
import { motion } from 'framer-motion';
import { useNotification } from '../contexts/NotificationContext';
import SystemUsers from './SystemUsers';
import RoleManagement from './RoleManagement';

const ElectionConfig = () => {
    const { showNotification, showDialog } = useNotification();
    const [isSaving, setIsSaving] = useState(false);
    // The factory-reset danger zone is platform-only. Client admins are
    // rejected by the API too, but the control must not even render for them.
    const isPlatformAdmin = (() => {
        try { return !localStorage.getItem('adminClientId'); } catch (e) { return false; }
    })();

    const handleFactoryReset = async () => {
        const password = await showDialog({
            title: "Nuclear System Reset",
            message: "DANGER: This wipes EVERYTHING — all elections, institutions, agents, results, sessions and evidence. Only geo data and platform admin accounts survive. Enter Admin Security Key to confirm:"
        });

        if (!password) return;

        setIsSaving(true);
        try {
            let res = await fetch('/admin/factory-reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_password: password })
            });
            let data = await res.json().catch(() => ({}));

            // Step 2 — if the account has 2FA enabled, the backend challenges
            // for a TOTP code; prompt and retry with both credentials.
            if (res.status === 401 && data.detail === '2FA_CODE_REQUIRED') {
                const code = await showDialog({
                    title: "Two-Factor Authentication",
                    message: "This account has 2FA enabled. Enter the 6-digit code from your authenticator app to authorize the factory reset:"
                });
                if (!code) {
                    showNotification('Factory reset cancelled.', 'error');
                    return;
                }
                res = await fetch('/admin/factory-reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ admin_password: password, totp_code: code.trim() })
                });
                data = await res.json().catch(() => ({}));
            }

            if (res.ok) {
                showNotification('SYSTEM WIPED. All elections, institutions, agents, results and evidence have been deleted.', 'success');
            } else {
                showNotification(data.detail || 'Reset failed.', 'error');
            }
        } catch (e) {
            showNotification('Network error during nuclear operation.', 'error');
        } finally {
            setIsSaving(false);
        }
    };

    return (

        <div className="space-y-6 animate-in fade-in duration-500">
            {/* User Management Module — global roles; platform admins only.
                The API already rejects client admins with 403. */}
            {isPlatformAdmin && <RoleManagement />}
            <div className="h-12"></div>
            <SystemUsers />

            {/* Danger Zone — platform super-admins only */}
            {isPlatformAdmin && (
            <div className="bg-red-50 dark:bg-red-950/20 p-6 rounded-3xl border border-red-200 dark:border-red-900/30 shadow-xl overflow-hidden relative group mt-6">
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
                        Initiating a **Factory Reset** permanently deletes <span className="font-black">every election, institution (client), field agent, uploaded result, evidence photo/video, and field session</span>. Only geographic data (states, LGAs, wards, polling units), platform administrator accounts, and the audit log survive. This action is intended for use **only** between election cycles or when starting completely fresh.
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
            )}
        </div>
    );
};

export default ElectionConfig;
