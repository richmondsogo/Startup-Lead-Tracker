import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold tracking-wide transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-blue-600/20 text-blue-300 border-blue-500/30",
        secondary:
          "border-transparent bg-slate-800 text-slate-300 border-slate-700/50",
        destructive:
          "border-transparent bg-rose-500/15 text-rose-300 border-rose-500/30",
        outline: "text-slate-300 border-slate-700/60 bg-slate-900/40",
        highScore:
          "border-emerald-500/30 bg-emerald-500/15 text-emerald-300 font-bold",
        midScore:
          "border-amber-500/30 bg-amber-500/15 text-amber-300 font-bold",
        lowScore:
          "border-slate-600/30 bg-slate-800/60 text-slate-400 font-medium",
        intern:
          "border-emerald-500/30 bg-emerald-500/20 text-emerald-300 font-bold",
        senior:
          "border-rose-500/30 bg-rose-500/15 text-rose-300 font-medium",
        contract:
          "border-blue-500/30 bg-blue-500/15 text-blue-300 font-medium",
        purple:
          "border-purple-500/30 bg-purple-500/15 text-purple-300 font-medium",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
