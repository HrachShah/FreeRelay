"use client"

import * as React from "react"
import { TrendingUp, DollarSign, Zap, ShieldCheck, ArrowDown, ArrowUp, Cpu } from "lucide-react"
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

const chartData = [
  { day: "Mon", actual: 45, baseline: 65, savings: 20 },
  { day: "Tue", actual: 52, baseline: 80, savings: 28 },
  { day: "Wed", actual: 48, baseline: 75, savings: 27 },
  { day: "Thu", actual: 61, baseline: 95, savings: 34 },
  { day: "Fri", actual: 55, baseline: 85, savings: 30 },
  { day: "Sat", actual: 40, baseline: 60, savings: 20 },
  { day: "Sun", actual: 38, baseline: 55, savings: 17 },
]

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

  React.useEffect(() => {
    fetch("http://localhost:8000/v1/hello")
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.message || "Connected"))
      .catch((err) => setBackendStatus("Disconnected (Backend not running)"))
  }, [])

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight">Savings Dashboard</h1>
          <p className="text-lg text-muted-foreground">
            Transparency into your LLM optimizations and ROI.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border bg-background px-4 py-2 text-sm font-semibold shadow-sm">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
          </span>
          Gateway: {backendStatus}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card className="relative overflow-hidden border-2 border-blue-100 shadow-md">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Total Spend</CardTitle>
            <DollarSign className="h-5 w-5 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-blue-900">$10,482.10</div>
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
            <div className="text-3xl font-bold text-green-900">$4,128.50</div>
            <div className="mt-1 flex items-center text-sm font-medium text-green-600">
              <ArrowUp className="mr-1 h-4 w-4" />
              <span>24.5% extra ROI</span>
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
            <div className="text-3xl font-bold text-purple-900">124.5M</div>
            <div className="mt-1 flex items-center text-sm font-medium text-purple-600">
              <TrendingUp className="mr-1 h-4 w-4" />
              <span>+12% volume</span>
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
            <div className="flex items-center gap-2 font-bold text-lg">
              Saving $172.40 daily average
            </div>
            <div className="leading-none text-muted-foreground font-medium">
              FreeRelay is currently reducing your LLM API costs by ~38% compared to direct calls.
            </div>
          </CardFooter>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Savings over Time</CardTitle>
            <CardDescription>
              Cumulative value generated by model routing.
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
                <div className="text-sm font-medium text-muted-foreground">Weekly Target</div>
                <div className="text-sm font-bold text-green-600">84% achieved</div>
             </div>
             <div className="h-2 w-full rounded-full bg-secondary">
                <div className="h-full w-[84%] rounded-full bg-green-500" />
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
                  {[
                     { name: "GPT-4o", optimized: "45%", savings: "$840" },
                     { name: "Claude 3.5 Sonnet", optimized: "32%", savings: "$520" },
                     { name: "Llama 3 70B", optimized: "18%", savings: "$210" },
                  ].map((model) => (
                     <div key={model.name} className="flex items-center justify-between">
                        <div className="flex flex-col">
                           <span className="font-bold">{model.name}</span>
                           <span className="text-xs text-muted-foreground">{model.optimized} of traffic</span>
                        </div>
                        <div className="font-mono text-green-600 font-bold">{model.savings}</div>
                     </div>
                  ))}
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
                     { name: "Rate Limit (429)", count: 24, resolution: "Retry Success" },
                     { name: "Timeout", count: 12, resolution: "Failover to Llama 3" },
                     { name: "Model Error (500)", count: 5, resolution: "Failover to GPT-4o-mini" },
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
               <div className="text-5xl font-black">$18,450.00</div>
               <p className="mt-2 text-blue-100 text-sm font-medium italic">"The most transparent ROI in AI."</p>
            </CardContent>
            <CardFooter className="bg-blue-700/50 justify-center">
               <button className="text-sm font-bold uppercase tracking-widest hover:underline">View Detailed ROI Report</button>
            </CardFooter>
         </Card>
      </div>
    </div>
  )
}
