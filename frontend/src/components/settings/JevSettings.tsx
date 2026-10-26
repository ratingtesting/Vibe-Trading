"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowUp,
  ArrowDown,
  Loader2,
  CheckCircle,
  AlertCircle,
  Zap,
  Shield,
  Play,
  Plus,
  Settings as SettingsIcon,
  Trash2,
  X,
} from "lucide-react";
import { jevApi, type JevProvider, type JevProviderStatus } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface ProviderRowProps {
  provider: JevProviderStatus;
  index: number;
  onMoveUp: (name: string) => void;
  onMoveDown: (name: string) => void;
  onToggleEnabled: (name: string, enabled: boolean) => void;
  onEdit: (provider: JevProviderStatus) => void;
  onUpdateApiKeyEnv: (name: string, apiKeyEnv: string) => void;
  onDelete: (name: string) => void;
}

function ProviderRow({
  provider,
  index,
  onMoveUp,
  onMoveDown,
  onToggleEnabled,
  onEdit,
  onUpdateApiKeyEnv,
  onDelete,
}: ProviderRowProps) {
  const { t } = useTranslation();
  const [apiKeyEnv, setApiKeyEnv] = useState(provider.api_key_env || "");
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await jevApi.testProvider(provider.name);
      if (result.success) {
        toast.success(`${provider.label}: ${t("jev.testPassed")}`, {
          description: `${t("jev.choice")}: ${result.choice}, ${t("jev.confidence")}: ${(result.confidence ?? 0).toFixed(2)}`,
        });
      } else {
        toast.error(`${provider.label}: ${t("jev.testFailed")}`, {
          description: result.error,
        });
      }
    } catch (error) {
      toast.error(`${provider.label}: ${t("jev.testFailed")}`, {
        description: error instanceof Error ? error.message : t("jev.unknownError"),
      });
    } finally {
      setTesting(false);
    }
  };

  const handleToggleEnabled = () => {
    onToggleEnabled(provider.name, !provider.enabled);
  };

  const handleApiKeyEnvChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setApiKeyEnv(value);
    onUpdateApiKeyEnv(provider.name, value);
  };

  const handleDelete = () => {
    onDelete(provider.name);
  };

  const tierBadge = provider.tier === "free" ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
      <Zap className="h-3 w-3" />
      {t("jev.tierFree")}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300">
      <Shield className="h-3 w-3" />
      {t("jev.tierPaid")}
    </span>
  );

  const statusBadge = provider.quarantined ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
      <AlertCircle className="h-3 w-3" />
      {t("jev.quarantined")} ({provider.quarantine_remaining_s}s)
    </span>
  ) : provider.enabled ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
      <CheckCircle className="h-3 w-3" />
      {t("jev.active")}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300">
      {t("jev.disabled")}
    </span>
  );

  const lastTest = provider.last_test;
  const lastTestDisplay = lastTest ? (
    lastTest.success ? (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
        <CheckCircle className="h-3 w-3" />
        OK {lastTest.latency_ms}ms
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
        <AlertCircle className="h-3 w-3" />
        {t("jev.failed")}
      </span>
    )
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300">
      {t("jev.notTested")}
    </span>
  );

  return (
    <tr className="border-b border-border/50 hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-sm font-mono">#{index + 1}</span>
          <div className="flex flex-col">
            <span className="font-medium text-sm">{provider.label}</span>
            <span className="text-xs text-muted-foreground font-mono">{provider.name}</span>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-mono break-all">{provider.base_url}</span>
          <span className="text-xs text-muted-foreground font-mono break-all">{provider.model}</span>
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {provider.transport === "decisions" ? t("jev.transportDecisions") : t("jev.transportSystemone")}
          </span>
        </div>
      </td>
      <td className="px-4 py-3 text-center">{tierBadge}</td>
      <td className="px-4 py-3 text-center">{statusBadge}</td>
      <td className="px-4 py-3 text-center">
        <label className="inline-flex items-center justify-center">
          <input
            type="checkbox"
            checked={provider.enabled && !provider.quarantined}
            onChange={handleToggleEnabled}
            disabled={provider.quarantined}
            className="sr-only peer"
          />
          <div className={cn(
            "relative w-10 h-6 rounded-full transition-colors",
            provider.enabled && !provider.quarantined
              ? "bg-primary"
              : "bg-muted"
          )}>
            <div className={cn(
              "absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform",
              provider.enabled && !provider.quarantined
                ? "translate-x-5"
                : "translate-x-0"
            )} />
          </div>
        </label>
      </td>
      <td className="px-4 py-3">
        <input
          type="text"
          value={apiKeyEnv}
          onChange={handleApiKeyEnvChange}
          placeholder={t("jev.apiKeyEnvName")}
          className="w-full max-w-xs px-2 py-1 text-xs rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          title={t("jev.apiKeyEnvTitle")}
        />
      </td>
      <td className="px-4 py-3 text-center">{lastTestDisplay}</td>
      <td className="px-4 py-3 text-center">
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => onMoveUp(provider.name)}
            disabled={index === 0}
            className="p-1.5 rounded hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
            title={t("jev.moveUp")}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
          <button
            onClick={() => onMoveDown(provider.name)}
            className="p-1.5 rounded hover:bg-muted"
            title={t("jev.moveDown")}
          >
            <ArrowDown className="h-4 w-4" />
          </button>
          <button
            onClick={handleTest}
            disabled={testing || provider.quarantined}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 dark:bg-blue-900/40 dark:text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed"
            title={t("jev.testProvider")}
          >
            {testing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {t("jev.testShort")}
          </button>
          <button
            onClick={() => onEdit(provider)}
            className="p-1.5 rounded hover:bg-muted"
            title={t("jev.editProviderTitle")}
          >
            <SettingsIcon className="h-4 w-4" />
          </button>
          <button
            onClick={handleDelete}
            className="p-1.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400"
            title={t("jev.deleteProvider")}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}

const EMPTY_FORM = {
  name: "",
  label: "",
  base_url: "",
  model: "",
  api_key_env: "",
  tier: "free" as "free" | "paid",
  transport: "systemone" as "systemone" | "decisions",
};

function AddProviderForm({
  form,
  setForm,
  onSubmit,
  onCancel,
  isEdit,
}: {
  form: typeof EMPTY_FORM;
  setForm: (f: typeof EMPTY_FORM) => void;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
  isEdit: boolean;
}) {
  const { t } = useTranslation();
  const field =
    "w-full mt-1 px-3 py-2 text-sm rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <form
        onSubmit={onSubmit}
        className="bg-card border border-border rounded-lg p-6 w-full max-w-md space-y-4"
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">{isEdit ? t("jev.editProvider") : t("jev.addProvider")}</h3>
          <button type="button" onClick={onCancel} className="p-1 rounded hover:bg-muted" title="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <label className="block">
          <span className="text-xs text-muted-foreground">{t("jev.formName")}</span>
          <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            className={field} placeholder="my-provider" />
        </label>
        <label className="block">
          <span className="text-xs text-muted-foreground">{t("jev.formLabel")}</span>
          <input required value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
            className={field} placeholder="My Provider (Free)" />
        </label>
        <label className="block">
          <span className="text-xs text-muted-foreground">{t("jev.formBaseUrl")}</span>
          <input required value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            className={field}
            placeholder={
              form.transport === "decisions"
                ? "https://openrouter.ai/api"
                : "http://127.0.0.1:8933/v1"
            }
            title={t("jev.baseUrlHint")} />
          <span className="text-[11px] text-muted-foreground">{t("jev.baseUrlHint")}</span>
        </label>
        <label className="block">
          <span className="text-xs text-muted-foreground">{t("jev.formModel")}</span>
          <input required value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}
            className={field} placeholder="provider/model-name" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs text-muted-foreground">{t("jev.formTier")}</span>
            <select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value as "free" | "paid" })}
              className={field}>
              <option value="free">{t("jev.tierFree")}</option>
              <option value="paid">{t("jev.tierPaid")}</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-muted-foreground">{t("jev.apiKeyEnvName")}</span>
            <input value={form.api_key_env} onChange={(e) => setForm({ ...form, api_key_env: e.target.value })}
              className={field} placeholder="MY_API_KEY" />
          </label>
        </div>
        <label className="block">
          <span className="text-xs text-muted-foreground">{t("jev.formTransport")}</span>
          <select
            value={form.transport}
            onChange={(e) => setForm({ ...form, transport: e.target.value as "systemone" | "decisions" })}
            className={field}
          >
            <option value="systemone">{t("jev.transportSystemone")}</option>
            <option value="decisions">{t("jev.transportDecisions")}</option>
          </select>
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel}
            className="px-4 py-2 rounded-md border border-border text-sm hover:bg-muted">
            {t("jev.cancel")}
          </button>
          <button type="submit"
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90">
            {t("jev.save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function JevSettings() {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<JevProviderStatus[]>([]);
  const [fallbackOrder, setFallbackOrder] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<JevProviderStatus | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const loadStatus = async () => {
    try {
      const status = await jevApi.getStatus();
      setProviders(status.providers);
      setFallbackOrder(status.fallback_order);
    } catch (error) {
      toast.error(t("jev.loadFailed"), {
        description: error instanceof Error ? error.message : t("jev.unknownError"),
      });
    } finally {
      setLoading(false);
    }
  };

  // The backend validates that the fallback order lists every provider
  // exactly once, so disabled providers are appended in their current order.
  const fullOrder = (desired: string[]) => {
    const known = providers.map(p => p.name);
    const rest = known.filter(name => !desired.includes(name));
    return [...desired, ...rest];
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleMoveUp = async (name: string) => {
    const idx = fallbackOrder.indexOf(name);
    if (idx <= 0) return;
    const newOrder = [...fallbackOrder];
    [newOrder[idx - 1], newOrder[idx]] = [newOrder[idx], newOrder[idx - 1]];
    setFallbackOrder(newOrder);
    try {
      await jevApi.updateOrder(fullOrder(newOrder));
      toast.success(t("jev.orderUpdated"));
    } catch (error) {
      setFallbackOrder(fallbackOrder); // revert
      toast.error(t("jev.orderFailed"), {
        description: error instanceof Error ? error.message : t("jev.unknownError"),
      });
    }
  };

  const handleMoveDown = async (name: string) => {
    const idx = fallbackOrder.indexOf(name);
    if (idx >= fallbackOrder.length - 1) return;
    const newOrder = [...fallbackOrder];
    [newOrder[idx], newOrder[idx + 1]] = [newOrder[idx + 1], newOrder[idx]];
    setFallbackOrder(newOrder);
    try {
      await jevApi.updateOrder(fullOrder(newOrder));
      toast.success(t("jev.orderUpdated"));
    } catch (error) {
      setFallbackOrder(fallbackOrder); // revert
      toast.error(t("jev.orderFailed"), {
        description: error instanceof Error ? error.message : t("jev.unknownError"),
      });
    }
  };

  const handleToggleEnabled = async (name: string, enabled: boolean) => {
    const provider = providers.find(p => p.name === name);
    if (!provider) return;
    setProviders(prev => prev.map(p => p.name === name ? { ...p, enabled } : p));
    try {
      await jevApi.upsertProvider({ name: provider.name, enabled });
      toast.success(`${provider.label}: ${enabled ? t("jev.enabled") : t("jev.disabled")}`);
    } catch (error) {
      setProviders(prev => prev.map(p => p.name === name ? { ...p, enabled: !enabled } : p));
      toast.error(t("jev.providerUpdateFailed"), {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  };

  const handleUpdateApiKeyEnv = async (name: string, apiKeyEnv: string) => {
    const provider = providers.find(p => p.name === name);
    if (!provider) return;
    try {
      await jevApi.upsertProvider({ name: provider.name, api_key_env: apiKeyEnv });
    } catch (error) {
      toast.error(t("jev.apiKeyEnvFailed"), {
        description: error instanceof Error ? error.message : t("jev.unknownError"),
      });
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await jevApi.deleteProvider(name);
      setProviders(prev => prev.filter(p => p.name !== name));
      setFallbackOrder(prev => prev.filter(n => n !== name));
      toast.success(t("jev.providerDeleted"));
    } catch (error) {
      toast.error(t("jev.providerDeleteFailed"), {
        description: error instanceof Error ? error.message : t("jev.unknownError"),
      });
    }
  };

  // Удаление необратимо: спрашиваем в самой странице, а не системным диалогом.
  const [pendingDelete, setPendingDelete] = useState<JevProviderStatus | null>(null);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    await handleDelete(target.name);
  };

  const handleEdit = (provider: JevProviderStatus) => {
    setEditing(provider);
    setForm({
      name: provider.name,
      label: provider.label,
      base_url: provider.base_url,
      model: provider.model,
      api_key_env: provider.api_key_env || "",
      tier: provider.tier as "free" | "paid",
      transport: provider.transport,
    });
    setShowAdd(true);
  };

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.label.trim() || !form.base_url.trim() || !form.model.trim()) return;
    const name = editing ? editing.name : form.name.trim();
    const newProvider: JevProvider = {
      name,
      label: form.label.trim(),
      base_url: form.base_url.trim(),
      model: form.model.trim(),
      api_key_env: form.api_key_env.trim(),
      tier: form.tier,
      transport: form.transport,
      enabled: editing ? editing.enabled : true,
      order: editing ? (editing.order ?? providers.length) : providers.length,
    };

    try {
      await jevApi.upsertProvider(newProvider);
      toast.success(editing ? t("jev.providerUpdated") : t("jev.providerAdded"));
      setShowAdd(false);
      setForm(EMPTY_FORM);
      loadStatus();
    } catch (error) {
      toast.error(t("jev.providerAddFailed"), {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin mr-2" />
        {t("jev.loading")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t("jev.title")}</h1>
          <p className="text-muted-foreground">
            {t("jev.subtitle")}
          </p>
        </div>
        <button
          onClick={() => { setForm(EMPTY_FORM); setEditing(null); setShowAdd(true); }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          {t("jev.addProvider")}
        </button>
      </div>

      {showAdd && (
        <AddProviderForm
          form={form}
          setForm={setForm}
          onSubmit={handleAddSubmit}
          onCancel={() => { setShowAdd(false); setEditing(null); }}
          isEdit={!!editing}
        />
      )}

      {pendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-card border border-border rounded-lg p-6 w-full max-w-sm space-y-4">
            <h3 className="text-lg font-semibold">{t("jev.deleteProvider")}</h3>
            <p className="text-sm text-muted-foreground">
              {t("jev.deleteConfirm", { label: pendingDelete.label })}
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setPendingDelete(null)}
                className="px-4 py-2 rounded-md border border-border text-sm hover:bg-muted"
              >
                {t("jev.cancel")}
              </button>
              <button
                onClick={confirmDelete}
                className="px-4 py-2 rounded-md bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90"
              >
                {t("jev.deleteProvider")}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colProvider")}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colEndpoint")}
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colTier")}
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colStatus")}
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colEnabled")}
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colApiKeyEnv")}
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colLastTest")}
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t("jev.colActions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {providers.map((provider, index) => (
                <ProviderRow
                  key={provider.name}
                  provider={provider}
                  index={index}
                  onMoveUp={handleMoveUp}
                  onMoveDown={handleMoveDown}
                  onToggleEnabled={handleToggleEnabled}
                  onEdit={handleEdit}
                  onUpdateApiKeyEnv={handleUpdateApiKeyEnv}
                  onDelete={(name) => {
                    const target = providers.find(p => p.name === name);
                    if (target) setPendingDelete(target);
                  }}
                />
              ))}
              {providers.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                    {t("jev.noProviders")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <h3 className="text-sm font-medium mb-3">{t("jev.fallbackOrder")}</h3>
        <div className="flex flex-wrap gap-2">
          {fallbackOrder.map((name, index) => {
            const provider = providers.find(p => p.name === name);
            return (
              <span
                key={name}
                className={cn(
                  "inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium border",
                  provider?.tier === "free"
                    ? "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800"
                    : "bg-purple-100 text-purple-800 border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800"
                )}
              >
                <span className="font-mono">{index + 1}.</span>
                {provider?.label || name}
              </span>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          {t("jev.fallbackHint")}
        </p>
      </div>
    </div>
  );
}