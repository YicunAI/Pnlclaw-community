"use client"

import { Button } from "@/components/ui/button"
import { useI18n } from "@/components/i18n/use-i18n"
import {
  CheckCircle2,
  Download,
  Loader2,
  Play,
  Rocket,
  Save,
  Square,
  XCircle,
  Zap,
} from "lucide-react"

export interface StudioToolbarProps {
  onSave: () => void
  onValidate: () => void
  onRunBacktest: () => void
  onDeploy: () => void
  onStopDeployment?: () => void
  onExport: () => void
  backtestRunning: boolean
  deploying?: boolean
  isDeployed?: boolean
  validationResult: { valid: boolean; errors: string[] } | null
}

export function StudioToolbar({
  onSave,
  onValidate,
  onRunBacktest,
  onDeploy,
  onStopDeployment,
  onExport,
  backtestRunning,
  deploying,
  isDeployed,
  validationResult,
}: StudioToolbarProps) {
  const { t } = useI18n()

  return (
    <div className="flex items-center gap-1.5">
      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onSave}>
        <Save className="h-3.5 w-3.5 mr-1" /> {t("strategies.studio.save")}
      </Button>
      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onValidate}>
        {validationResult?.valid === true ? (
          <CheckCircle2 className="h-3.5 w-3.5 mr-1 text-emerald-400" />
        ) : validationResult?.valid === false ? (
          <XCircle className="h-3.5 w-3.5 mr-1 text-red-400" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
        )}
        {t("strategies.studio.validate")}
      </Button>
      <Button size="sm" className="h-7 text-xs" onClick={onRunBacktest} disabled={backtestRunning}>
        {backtestRunning ? (
          <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
        ) : (
          <Play className="h-3.5 w-3.5 mr-1" />
        )}
        {t("strategies.studio.runBacktest")}
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="h-7 text-xs opacity-50 cursor-not-allowed"
        disabled
        title="Coming in v0.2"
      >
        <Zap className="h-3.5 w-3.5 mr-1" /> {t("strategies.studio.optimize")}
      </Button>
      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onDeploy} disabled={deploying || isDeployed}>
        {deploying ? (
          <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
        ) : (
          <Rocket className="h-3.5 w-3.5 mr-1" />
        )}
        {deploying ? t("strategies.studio.deploying") : t("strategies.studio.deploy")}
      </Button>
      {isDeployed && onStopDeployment && (
        <Button variant="destructive" size="sm" className="h-7 text-xs" onClick={onStopDeployment}>
          <Square className="h-3 w-3 mr-1" /> {t("strategies.studio.stopDeployment")}
        </Button>
      )}
      <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onExport}>
        <Download className="h-3.5 w-3.5 mr-1" /> {t("strategies.studio.export")}
      </Button>
    </div>
  )
}
