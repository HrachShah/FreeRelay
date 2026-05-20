"use client"

import * as React from "react"
import { Copy, Key, MoreHorizontal, Plus, Trash2 } from "lucide-react"

import {
  Button
} from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"

const initialKeys = [
  {
    id: "1",
    name: "Production API Key",
    key: "fr_live_....................4a2b",
    created: "2024-04-10",
    lastUsed: "2 minutes ago",
    status: "Active",
  },
  {
    id: "2",
    name: "Development Key",
    key: "fr_test_....................8e1f",
    created: "2024-04-12",
    lastUsed: "Yesterday",
    status: "Active",
  },
]

export default function ApiKeysPage() {
  const [keys, setKeys] = React.useState(initialKeys)
  const [newKeyName, setNewKeyName] = React.useState("")

  const addKey = () => {
    if (!newKeyName) return
    const newKey = {
      id: crypto.randomUUID(),
      name: newKeyName,
      key: `fr_live_${crypto.randomUUID().replace(/-/g, '').slice(0, 20)}`,
      created: new Date().toISOString().split('T')[0],
      lastUsed: "Never",
      status: "Active",
    }
    setKeys([...keys, newKey])
    setNewKeyName("")
  }

  const deleteKey = (id: string) => {
    setKeys(keys.filter(k => k.id !== id))
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-4xl font-extrabold tracking-tight">API Keys</h1>
        <p className="text-lg text-muted-foreground">
          Manage your FreeRelay access tokens. Use these keys to authenticate your LLM requests.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Create New Key</CardTitle>
          <CardDescription>
            Give your key a descriptive name to identify where it's used.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-4 sm:flex-row">
            <Input 
              placeholder="e.g. Production Backend" 
              className="max-w-md"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
            />
            <Button onClick={addKey} className="sm:w-auto">
              <Plus className="mr-2 h-4 w-4" /> Create Key
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your Keys</CardTitle>
          <CardDescription>
            Active keys that can be used to access the FreeRelay Gateway.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>API Key</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last Used</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-semibold">{key.name}</TableCell>
                  <TableCell>
                    <code className="relative rounded bg-muted px-[0.3rem] py-[0.2rem] font-mono text-sm">
                      {key.key}
                    </code>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                      {key.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{key.created}</TableCell>
                  <TableCell>{key.lastUsed}</TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" className="h-8 w-8 p-0">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Actions</DropdownMenuLabel>
                        <DropdownMenuItem onClick={() => navigator.clipboard.writeText(key.key)}>
                          <Copy className="mr-2 h-4 w-4" /> Copy Key
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => deleteKey(key.id)} className="text-destructive">
                          <Trash2 className="mr-2 h-4 w-4" /> Revoke Key
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      
      <div className="rounded-lg border bg-amber-50 p-4 text-amber-800 border-amber-200">
        <div className="flex items-center gap-2 font-bold mb-1">
          <Key className="h-4 w-4" /> Security Note
        </div>
        <p className="text-sm">
          Keep your API keys secure. Never share them publicly or include them in client-side code. 
          If a key is compromised, revoke it immediately and generate a new one.
        </p>
      </div>
    </div>
  )
}
