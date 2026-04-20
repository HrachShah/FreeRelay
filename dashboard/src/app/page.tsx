"use client"

import * as React from "react"
import { TrendingUp, DollarSign, Zap, ShieldCheck, ArrowDown, ArrowUp, Cpu, Calendar, ChevronDown, RefreshCcw } from "lucide-react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts"

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface ModelUsage {
  model: string
  tokens: number
  cost: number
  savings: number
  percentage: number
}

interface DailyTrend {
  day: string
  actual: number
  baseline: number
  savings: number
}

interface AnalyticsData {
  total_spend: number
  total_savings: number
  total_tokens: number
  savings_percentage: number
  top_models: ModelUsage[]
  daily_trends: DailyTrend[]
  projected_monthly_savings: number
}

const chartConfig = {
  actual: {
    label: "Actual Cost",
    color: "hsl(var(--chart-1))",
  },
  baseline: {
    label: "Baseline Cost",
    color: "hsl(var(--chart-2))",
  },
  savings: {
    label: "Savings",
    color: "hsl(var(--chart-3))",
  },
} satisfies ChartConfig

export default function DashboardPage() {
  const [backendStatus, setBackendStatus] = React.useState<string>("Checking...")
  const [data, setData] = React.useState<AnalyticsData | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [days, setDays] = React.useState(7)
  const [refreshKey, setRefreshKey] = React.useState(0)

  React.useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"
    setLoading(true)
    
    // Check health
    fetch(`${apiUrl}/v1/hello`)
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.message || "Connected"))
      .catch((err) => setBackendStatus("Disconnected"))

    // Fetch analytics
    fetch(`${apiUrl}/v1/analytics?days=${days}`)
      .then((res) => {
        if (!res.ok) throw new Error("API error")
        return res.json()
      })
      .then((json) => {
        setData(json)
        setLoading(false)
      })
      .catch((err) => {
        console.error("Failed to fetch analytics:", err)
        setLoading(false)
      })
  }, [days, refreshKey])

  const handleRefresh = () => setRefreshKey(prev => prev + 1)

  const getRangeLabel = (d: number) => {
    if (d === 1) return "Last 24 Hours"
    if (d === 7) return "Last 7 Days"
    if (d === 30) return "Last 30 Days"
    if (d === 90) return "Last 90 Days"
    return `Last ${d} Days`
  }

  if (loading && !data) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-600 border-t-transparent"></div>
          <p className="text-lg font-medium text-muted-foreground">Loading your savings data...</p>
        </div>
      </div>
    )
  }

  const chartData = data?.daily_trends || []
  const hasData = data && data.total_tokens > 0

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight">Savings Dashboard</h1>
          <p className="text-lg text-muted-foreground">
            Transparency into your LLM optimizations and ROI.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button 
            onClick={handleRefresh}
            className="p-2 rounded-lg border bg-background hover:bg-accent transition-colors shadow-sm"
            title="Refresh Data"
          >
            <RefreshCcw className={`h-4 w-4 text-muted-foreground ${loading ? 'animate-spin' : ''}`} />
          </button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-2 rounded-lg border bg-background px-3 py-1.5 text-sm shadow-sm hover:bg-accent transition-colors outline-none">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{getRangeLabel(days)}</span>
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-[160px] bg-background border shadow-lg z-50">
              <DropdownMenuItem className="cursor-pointer" onClick={() => setDays(1)}>Last 24 Hours</DropdownMenuItem>
              <DropdownMenuItem className="cursor-pointer" onClick={() => setDays(7)}>Last 7 Days</DropdownMenuItem>
              <DropdownMenuItem className="cursor-pointer" onClick={() => setDays(30)}>Last 30 Days</DropdownMenuItem>
              <DropdownMenuItem className="cursor-pointer" onClick={() => setDays(90)}>Last 90 Days</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="flex items-center gap-2 rounded-full border bg-background px-4 py-2 text-sm font-semibold shadow-sm">
            <span className="relative flex h-3 w-3">
              {backendStatus === "Connected" || backendStatus.includes("Hello") ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                </>
              ) : (
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
              )}
            </span>
            Gateway: {backendStatus}
          </div>
        </div>
      </div>

      {!hasData && !loading ? (
        <Card className="flex flex-col items-center justify-center py-20 text-center border-dashed">
          <div className="rounded-full bg-blue-50 p-4 mb-4">
            <Zap className="h-10 w-10 text-blue-600" />
          </div>
          <CardTitle className="text-2xl">No usage data yet</CardTitle>
          <CardDescription className="max-w-md mt-2 text-base">
            Start sending requests through the FreeRelay gateway at <code>http://localhost:8001/v1</code> to see your savings here.
          </CardDescription>
        </Card>
      ) : (
        <>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <Card className="relative overflow-hidden border-2 border-blue-100 shadow-md">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Total Spend</CardTitle>
                <DollarSign className="h-5 w-5 text-blue-600" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-blue-900">${data?.total_spend.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                <div className="mt-1 flex items-center text-sm font-medium text-blue-600">
                  <span>Net spend across all providers</span>
                </div>
              </CardContent>
              <div className="absolute bottom-0 left-0 h-1 w-full bg-blue-600" />
            </Card>
            <Card className="relative overflow-hidden border-2 border-green-100 shadow-md">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Total Savings</CardTitle>
                <Zap className="h-5 w-5 text-green-600" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-green-900">${data?.total_savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                <div className="mt-1 flex items-center text-sm font-medium text-green-600">
                  <ArrowUp className="mr-1 h-4 w-4" />
                  <span>{data?.savings_percentage.toFixed(1)}% extra ROI</span>
                </div>
              </CardContent>
              <div className="absolute bottom-0 left-0 h-1 w-full bg-green-600" />
            </Card>
            <Card className="relative overflow-hidden border-2 border-purple-100 shadow-md">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Total Tokens</CardTitle>
                <Cpu className="h-5 w-5 text-purple-600" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-purple-900">{(data?.total_tokens || 0).toLocaleString()}</div>
                <div className="mt-1 flex items-center text-sm font-medium text-purple-600">
                  <TrendingUp className="mr-1 h-4 w-4" />
                  <span>Volume across all models</span>
                </div>
              </CardContent>
              <div className="absolute bottom-0 left-0 h-1 w-full bg-purple-600" />
            </Card>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-7">
            <Card className="lg:col-span-4">
              <CardHeader>
                <CardTitle>Cost Breakdown</CardTitle>
                <CardDescription>
                  Actual spend vs what you would have paid without FreeRelay.
                </CardDescription>
              </CardHeader>
              <CardContent className="px-2 sm:px-6">
                <ChartContainer config={chartConfig} className="h-[350px] w-full">
                  <BarChart data={chartData} margin={{ top: 20, right: 0, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" opacity={0.5} />
                    <XAxis
                      dataKey="day"
                      tickLine={false}
                      tickMargin={10}
                      axisLine={false}
                      tickFormatter={(value) => value.split('-').slice(1).join('/')}
                    />
                    <ChartTooltip
                      cursor={{ fill: 'transparent' }}
                      content={<ChartTooltipContent indicator="line" />}
                    />
                    <Bar dataKey="actual" fill="var(--color-actual)" radius={[4, 4, 0, 0]} barSize={30} />
                    <Bar dataKey="baseline" fill="var(--color-baseline)" radius={[4, 4, 0, 0]} barSize={30} opacity={0.3} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
              <CardFooter className="flex-col items-start gap-2 text-sm">
                <div className="flex items-center gap-2 font-bold text-lg text-green-600">
                  ROI is tracking at {data?.savings_percentage.toFixed(1)}%
                </div>
                <div className="leading-none text-muted-foreground font-medium">
                  FreeRelay is reducing your LLM API costs through intelligent model routing and provider fallback.
                </div>
              </CardFooter>
            </Card>

            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle>Savings over Time</CardTitle>
                <CardDescription>
                  Daily value generated by model routing.
                </CardDescription>
              </CardHeader>
              <CardContent className="px-2">
                <ChartContainer config={chartConfig} className="h-[350px] w-full">
                  <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorSavings" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--color-savings)" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="var(--color-savings)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" opacity={0.3} />
                    <XAxis
                      dataKey="day"
                      tickLine={false}
                      tickMargin={10}
                      axisLine={false}
                      tickFormatter={(value) => value.split('-').slice(1).join('/')}
                    />
                    <ChartTooltip
                      cursor={false}
                      content={<ChartTooltipContent />}
                    />
                    <Area
                      type="monotone"
                      dataKey="savings"
                      stroke="var(--color-savings)"
                      fillOpacity={1}
                      fill="url(#colorSavings)"
                      strokeWidth={3}
                    />
                  </AreaChart>
                </ChartContainer>
              </CardContent>
              <CardFooter className="flex flex-col gap-4">
                <div className="flex w-full items-center justify-between border-t pt-4">
                    <div className="text-sm font-medium text-muted-foreground">Cumulative Savings</div>
                    <div className="text-sm font-bold text-green-600">${data?.total_savings.toFixed(2)}</div>
                </div>
                <div className="h-2 w-full rounded-full bg-secondary">
                    <div className="h-full w-[100%] rounded-full bg-green-500" />
                </div>
              </CardFooter>
            </Card>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Top Optimized Models</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                      {data?.top_models.map((model) => (
                        <div key={model.model} className="flex items-center justify-between">
                            <div className="flex flex-col">
                              <span className="font-bold">{model.model}</span>
                              <span className="text-xs text-muted-foreground">{model.percentage.toFixed(1)}% of traffic</span>
                            </div>
                            <div className="font-mono text-green-600 font-bold">${model.savings.toFixed(2)}</div>
                        </div>
                      ))}
                      {(!data?.top_models || data.top_models.length === 0) && (
                        <div className="text-sm text-muted-foreground italic py-4 text-center">No model data yet.</div>
                      )}
                  </div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Reliability Fallbacks</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                      {[
                        { name: "Rate Limit (429)", count: 2, resolution: "Retry Success" },
                        { name: "Timeout", count: 1, resolution: "Failover to Llama 3" },
                        { name: "Model Error (500)", count: 0, resolution: "Failover to GPT-4o-mini" },
                      ].map((error) => (
                        <div key={error.name} className="flex items-center justify-between">
                            <div className="flex flex-col">
                              <span className="font-bold">{error.name}</span>
                              <span className="text-xs text-muted-foreground">{error.resolution}</span>
                            </div>
                            <div className="bg-secondary px-2 py-1 rounded text-xs font-bold">{error.count}x</div>
                        </div>
                      ))}
                  </div>
                </CardContent>
            </Card>
            <Card className="bg-blue-600 text-white border-none shadow-xl">
                <CardHeader>
                  <CardTitle className="text-lg text-white">Projected Monthly Savings</CardTitle>
                  <CardDescription className="text-blue-100">Based on current usage patterns.</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col items-center justify-center py-6">
                  <div className="text-5xl font-black">${data?.projected_monthly_savings.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                  <p className="mt-2 text-blue-100 text-sm font-medium italic">"The most transparent ROI in AI."</p>
                </CardContent>
                <CardFooter className="bg-blue-700/50 justify-center">
                  <button className="text-sm font-bold uppercase tracking-widest hover:underline">View Detailed ROI Report</button>
                </CardFooter>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
