"use client"

import React, { useCallback, useEffect, useRef, useState } from "react"
import { RequireAuth } from "@/components/auth/require-auth"
import {
  Sparkles,
  RefreshCw,
  Tag,
  Wrench,
  User,
  Bot,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Plus,
  Pencil,
  Trash2,
  Upload,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { useI18n } from "@/components/i18n/use-i18n"
import {
  getSkills,
  getSkill,
  createSkill,
  updateSkill,
  deleteSkill,
  toggleSkill,
  refreshSkills,
  type SkillInfo,
  type SkillDetail,
} from "@/lib/api-client"

const sourceColors: Record<string, "default" | "secondary" | "outline" | "success"> = {
  bundled: "success",
  user: "secondary",
  workspace: "default",
  extra: "outline",
}

export default function SkillsPage() {
  const { t } = useI18n()
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetail>>({})
  const [detailLoading, setDetailLoading] = useState<string | null>(null)

  // Create / Edit dialog state
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingSkill, setEditingSkill] = useState<string | null>(null)
  const [formName, setFormName] = useState("")
  const [formDesc, setFormDesc] = useState("")
  const [formTags, setFormTags] = useState("")
  const [formContent, setFormContent] = useState("")
  const [formError, setFormError] = useState<string | null>(null)
  const [formSaving, setFormSaving] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchSkills = useCallback(async () => {
    setLoading(true)
    const res = await getSkills()
    if (res.data) {
      setSkills(res.data.skills || [])
      setError(null)
    } else {
      setError(res.error)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchSkills()
  }, [fetchSkills])

  const handleRefresh = async () => {
    await refreshSkills()
    setSkillDetails({})
    fetchSkills()
  }

  const handleToggle = async (name: string, currentEnabled: boolean) => {
    const newEnabled = !currentEnabled
    setSkills((prev) =>
      prev.map((s) => (s.name === name ? { ...s, enabled: newEnabled } : s)),
    )
    await toggleSkill(name, newEnabled)
  }

  const handleExpand = async (name: string) => {
    if (expanded === name) {
      setExpanded(null)
      return
    }
    setExpanded(name)
    if (!skillDetails[name]) {
      setDetailLoading(name)
      const res = await getSkill(name)
      if (res.data) {
        setSkillDetails((prev) => ({ ...prev, [name]: res.data! }))
      }
      setDetailLoading(null)
    }
  }

  const openCreateDialog = () => {
    setEditingSkill(null)
    setFormName("")
    setFormDesc("")
    setFormTags("")
    setFormContent("")
    setFormError(null)
    setDialogOpen(true)
  }

  const openEditDialog = async (name: string) => {
    setFormError(null)
    setFormSaving(false)

    let detail = skillDetails[name]
    if (!detail) {
      const res = await getSkill(name)
      if (res.data) {
        detail = res.data
        setSkillDetails((prev) => ({ ...prev, [name]: res.data! }))
      }
    }
    if (!detail) return

    setEditingSkill(name)
    setFormName(name)
    setFormDesc(detail.description || "")
    setFormTags((detail as SkillDetail).requires_env ? "" : (detail.tags || []).join(", "))
    setFormContent(detail.content || "")
    setDialogOpen(true)
  }

  const handleFileImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      if (!text) return

      // Try to extract name from frontmatter or filename
      if (!formName) {
        const nameMatch = text.match(/^name:\s*(.+)$/m)
        if (nameMatch) {
          setFormName(nameMatch[1].trim())
        } else {
          const baseName = file.name.replace(/\.md$/i, "").replace(/\s+/g, "-").toLowerCase()
          setFormName(baseName)
        }
      }

      // Extract description from frontmatter
      if (!formDesc) {
        const descMatch = text.match(/^description:\s*(.+)$/m)
        if (descMatch) setFormDesc(descMatch[1].trim())
      }

      // Extract tags from frontmatter
      if (!formTags) {
        const tagsMatch = text.match(/^tags:\s*\[(.+)\]$/m)
        if (tagsMatch) setFormTags(tagsMatch[1].trim())
      }

      // Extract body content (after frontmatter)
      let body = text
      if (text.startsWith("---")) {
        const parts = text.split("---")
        if (parts.length >= 3) {
          body = parts.slice(2).join("---").trim()
        }
      }
      setFormContent(body)
    }
    reader.readAsText(file)
    e.target.value = ""
  }

  const handleSave = async () => {
    const name = formName.trim().toLowerCase().replace(/\s+/g, "-")
    if (!name || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(name)) {
      setFormError(t("skills.nameError"))
      return
    }
    if (!formContent.trim()) {
      setFormError(t("skills.contentRequired"))
      return
    }

    setFormSaving(true)
    setFormError(null)

    const tags = formTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)

    if (editingSkill) {
      const res = await updateSkill(editingSkill, {
        description: formDesc,
        tags,
        content: formContent,
      })
      if (res.error) {
        setFormError(res.error)
        setFormSaving(false)
        return
      }
    } else {
      const res = await createSkill({
        name,
        description: formDesc,
        tags,
        content: formContent,
      })
      if (res.error) {
        setFormError(res.error)
        setFormSaving(false)
        return
      }
    }

    setFormSaving(false)
    setDialogOpen(false)
    setSkillDetails({})
    fetchSkills()
  }

  const handleDelete = async (name: string) => {
    if (!window.confirm(t("skills.deleteConfirm"))) return
    await deleteSkill(name)
    setSkillDetails({})
    fetchSkills()
  }

  const sourceLabel = (source: string) => {
    const key = `skills.${source}`
    const fallback = source
    if (key === "skills.bundled") return t("skills.bundled")
    if (key === "skills.user") return t("skills.user")
    if (key === "skills.workspace") return t("skills.workspace")
    if (key === "skills.extra") return t("skills.extra")
    return fallback
  }

  const isEditing = editingSkill !== null

  return (
    <RequireAuth>
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("skills.title")}</h1>
          <p className="text-muted-foreground text-sm mt-1">{t("skills.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          {skills.length > 0 && (
            <span className="text-sm text-muted-foreground">
              {t("skills.count", { count: String(skills.length) })}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="h-4 w-4 mr-1" />
            {t("skills.refresh")}
          </Button>
          <Button size="sm" onClick={openCreateDialog}>
            <Plus className="h-4 w-4 mr-1" />
            {t("skills.createSkill")}
          </Button>
        </div>
      </div>

      {error && (
        <Card className="border-destructive/50">
          <CardContent className="py-4 text-sm text-destructive">{t("skills.apiUnavailable")}</CardContent>
        </Card>
      )}

      {/* Create / Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{isEditing ? t("skills.editTitle") : t("skills.createTitle")}</DialogTitle>
            <DialogDescription>{t("skills.createDesc")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            {/* Name */}
            <div>
              <Label>{t("skills.skillName")}</Label>
              <Input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder={t("skills.skillNamePlaceholder")}
                disabled={isEditing}
                className="font-mono"
              />
            </div>

            {/* Description */}
            <div>
              <Label>{t("skills.skillDesc")}</Label>
              <Input
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                placeholder={t("skills.skillDescPlaceholder")}
              />
            </div>

            {/* Tags */}
            <div>
              <Label>{t("skills.skillTags")}</Label>
              <Input
                value={formTags}
                onChange={(e) => setFormTags(e.target.value)}
                placeholder={t("skills.skillTagsPlaceholder")}
              />
            </div>

            {/* Import button */}
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-4 w-4 mr-1" />
                {t("skills.importFile")}
              </Button>
              <span className="text-xs text-muted-foreground">.md</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.txt,.markdown"
                className="hidden"
                onChange={handleFileImport}
              />
            </div>

            {/* Content */}
            <div>
              <Label>{t("skills.skillContent")}</Label>
              <textarea
                value={formContent}
                onChange={(e) => setFormContent(e.target.value)}
                placeholder={t("skills.skillContentPlaceholder")}
                rows={14}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-y leading-relaxed"
              />
            </div>

            {formError && (
              <p className="text-sm text-destructive">{formError}</p>
            )}

            <Button
              onClick={handleSave}
              className="w-full"
              disabled={formSaving}
            >
              {formSaving
                ? t("common.loading")
                : isEditing
                  ? t("skills.save")
                  : t("skills.create")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Empty state */}
      {!loading && skills.length === 0 && !error && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Sparkles className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p>{t("skills.noSkills")}</p>
            <p className="text-xs mt-2 opacity-70">
              {t("skills.createDesc")}
            </p>
            <Button size="sm" className="mt-4" onClick={openCreateDialog}>
              <Plus className="h-4 w-4 mr-1" />
              {t("skills.createSkill")}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Skill Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        {skills.map((skill) => {
          const isExpanded = expanded === skill.name
          const isEnabled = skill.enabled !== false
          const isUser = skill.source === "user"
          return (
            <Card key={skill.name} className={`overflow-hidden transition-opacity ${isEnabled ? "" : "opacity-50"}`}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-1 flex-1 min-w-0">
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <BookOpen className="h-4 w-4 text-primary shrink-0" />
                      <span className="truncate">{skill.name}</span>
                    </CardTitle>
                    {skill.description && (
                      <p className="text-xs text-muted-foreground leading-relaxed">{skill.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant={sourceColors[skill.source] || "outline"} className="text-xs">
                      {sourceLabel(skill.source)}
                    </Badge>
                    <Switch
                      checked={isEnabled}
                      onCheckedChange={() => handleToggle(skill.name, isEnabled)}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {skill.tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="text-xs">
                      <Tag className="h-2.5 w-2.5 mr-0.5" />
                      {tag}
                    </Badge>
                  ))}
                  {skill.user_invocable && (
                    <Badge variant="secondary" className="text-xs">
                      <User className="h-2.5 w-2.5 mr-0.5" />
                      {t("skills.userInvocable")}
                    </Badge>
                  )}
                  {skill.model_invocable && (
                    <Badge variant="secondary" className="text-xs">
                      <Bot className="h-2.5 w-2.5 mr-0.5" />
                      {t("skills.modelInvocable")}
                    </Badge>
                  )}
                </div>

                {skill.requires_tools.length > 0 && (
                  <div className="flex items-center gap-1 flex-wrap">
                    <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
                    {skill.requires_tools.map((tool) => (
                      <Badge key={tool} variant="outline" className="text-xs font-mono">
                        {tool}
                      </Badge>
                    ))}
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex items-center gap-1 pt-1">
                  <button
                    onClick={() => handleExpand(skill.name)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    {skill.file_path}
                  </button>
                  {isUser && (
                    <div className="ml-auto flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2"
                        onClick={() => openEditDialog(skill.name)}
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2"
                        onClick={() => handleDelete(skill.name)}
                      >
                        <Trash2 className="h-3 w-3 text-destructive" />
                      </Button>
                    </div>
                  )}
                </div>

                {/* Expanded content */}
                {isExpanded && (
                  <div className="mt-2 border-t pt-3">
                    {detailLoading === skill.name ? (
                      <p className="text-xs text-muted-foreground">{t("common.loading")}</p>
                    ) : skillDetails[skill.name]?.content ? (
                      <div className="space-y-2">
                        {skillDetails[skill.name].version && (
                          <div className="flex gap-2 text-xs text-muted-foreground">
                            <span>v{skillDetails[skill.name].version}</span>
                            {skillDetails[skill.name].author && (
                              <span>· {skillDetails[skill.name].author}</span>
                            )}
                          </div>
                        )}
                        <pre className="text-xs bg-muted/50 rounded-md p-3 overflow-auto max-h-64 whitespace-pre-wrap font-mono leading-relaxed">
                          {skillDetails[skill.name].content}
                        </pre>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">{skill.file_path}</p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
    </RequireAuth>
  )
}
