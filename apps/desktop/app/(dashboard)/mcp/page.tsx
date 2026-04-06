"use client"

import React, { useCallback, useEffect, useState } from "react"
import { RequireAuth } from "@/components/auth/require-auth"
import {
  Plug,
  RefreshCw,
  Trash2,
  CheckCircle2,
  XCircle,
  Plus,
  Wrench,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
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
  getMcpServers,
  addMcpServer,
  removeMcpServer,
  refreshMcpServer,
  type McpServerInfo,
} from "@/lib/api-client"

export default function McpPage() {
  const { t } = useI18n()
  const [servers, setServers] = useState<McpServerInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  // Add server form state
  const [newName, setNewName] = useState("")
  const [newCommand, setNewCommand] = useState("")
  const [newArgs, setNewArgs] = useState("")
  const [newUrl, setNewUrl] = useState("")
  const [newTransport, setNewTransport] = useState("stdio")
  const [newRiskLevel, setNewRiskLevel] = useState("restricted")

  const fetchServers = useCallback(async () => {
    setLoading(true)
    const res = await getMcpServers()
    if (res.data) {
      setServers(res.data.servers || [])
      setError(null)
    } else {
      setError(res.error)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchServers()
  }, [fetchServers])

  const handleAdd = async () => {
    if (!newName) return
    const config: Record<string, unknown> = {
      transport: newTransport,
      risk_level: newRiskLevel,
    }
    if (newTransport === "stdio") {
      config.command = newCommand
      config.args = newArgs.split(/\s+/).filter(Boolean)
    } else {
      config.url = newUrl
    }
    await addMcpServer(newName, config as never)
    setDialogOpen(false)
    setNewName("")
    setNewCommand("")
    setNewArgs("")
    setNewUrl("")
    fetchServers()
  }

  const handleRemove = async (name: string) => {
    await removeMcpServer(name)
    fetchServers()
  }

  const handleRefresh = async (name: string) => {
    await refreshMcpServer(name)
    fetchServers()
  }

  return (
    <RequireAuth>
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("mcp.title")}</h1>
          <p className="text-muted-foreground text-sm mt-1">{t("mcp.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchServers}>
            <RefreshCw className="h-4 w-4 mr-1" />
            {t("mcp.refresh")}
          </Button>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-1" />
                {t("mcp.addServer")}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t("mcp.addTitle")}</DialogTitle>
                <DialogDescription>{t("mcp.addDesc")}</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 mt-2">
                <div>
                  <Label>{t("mcp.serverName")}</Label>
                  <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="my-server" />
                </div>
                <div>
                  <Label>{t("mcp.transport")}</Label>
                  <div className="flex gap-2 mt-1">
                    <Button variant={newTransport === "stdio" ? "default" : "outline"} size="sm" onClick={() => setNewTransport("stdio")}>stdio</Button>
                    <Button variant={newTransport === "sse" ? "default" : "outline"} size="sm" onClick={() => setNewTransport("sse")}>SSE</Button>
                  </div>
                </div>
                {newTransport === "stdio" ? (
                  <>
                    <div>
                      <Label>{t("mcp.command")}</Label>
                      <Input value={newCommand} onChange={(e) => setNewCommand(e.target.value)} placeholder="npx" />
                    </div>
                    <div>
                      <Label>{t("mcp.args")}</Label>
                      <Input value={newArgs} onChange={(e) => setNewArgs(e.target.value)} placeholder="-y @modelcontextprotocol/server-filesystem /path" />
                    </div>
                  </>
                ) : (
                  <div>
                    <Label>{t("mcp.url")}</Label>
                    <Input value={newUrl} onChange={(e) => setNewUrl(e.target.value)} placeholder="http://localhost:3001/sse" />
                  </div>
                )}
                <div>
                  <Label>{t("mcp.riskLevel")}</Label>
                  <div className="flex gap-2 mt-1">
                    {["safe", "restricted", "dangerous"].map((level) => (
                      <Button key={level} variant={newRiskLevel === level ? "default" : "outline"} size="sm" onClick={() => setNewRiskLevel(level)}>
                        {level}
                      </Button>
                    ))}
                  </div>
                </div>
                <Button onClick={handleAdd} className="w-full">{t("mcp.addServer")}</Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {error && (
        <Card className="border-destructive/50">
          <CardContent className="py-4 text-sm text-destructive">{t("mcp.apiUnavailable")}</CardContent>
        </Card>
      )}

      {!loading && servers.length === 0 && !error && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Plug className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p>{t("mcp.noServers")}</p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-4">
        {servers.map((server) => (
          <Card key={server.name}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CardTitle className="text-base font-medium">{server.name}</CardTitle>
                  <Badge variant={server.connected ? "success" : "destructive"} className="text-xs">
                    {server.connected ? (
                      <><CheckCircle2 className="h-3 w-3 mr-1" />{t("mcp.connected")}</>
                    ) : (
                      <><XCircle className="h-3 w-3 mr-1" />{t("mcp.disconnected")}</>
                    )}
                  </Badge>
                  <Badge variant="outline" className="text-xs">{server.transport}</Badge>
                  <Badge variant="secondary" className="text-xs">
                    {server.tool_count} {t("mcp.tools")}
                  </Badge>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => handleRefresh(server.name)}>
                    <RefreshCw className="h-3.5 w-3.5" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleRemove(server.name)}>
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              </div>
              {server.error && <p className="text-xs text-destructive mt-1">{server.error}</p>}
            </CardHeader>
            {server.tools.length > 0 && (
              <>
                <Separator />
                <CardContent className="pt-3">
                  <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <Wrench className="h-3 w-3" /> {t("mcp.toolList")}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {server.tools.map((tool) => (
                      <Badge key={tool.tool_name} variant="outline" className="text-xs font-mono">
                        {tool.tool_name}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </>
            )}
          </Card>
        ))}
      </div>
    </div>
    </RequireAuth>
  )
}
