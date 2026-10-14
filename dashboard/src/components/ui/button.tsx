import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:pointer-events-none disabled:opacity-50 cursor-pointer active:scale-[0.98]",
  {
    variants: {
      variant: {
        default:
          "bg-blue-600 text-white shadow-sm hover:bg-blue-500 shadow-blue-500/20",
        destructive:
          "bg-rose-600 text-white shadow-xs hover:bg-rose-500",
        outline:
          "border border-slate-700/80 bg-slate-900/60 text-slate-200 hover:bg-slate-800/80 hover:text-white hover:border-slate-600",
        secondary:
          "bg-slate-800 text-slate-100 shadow-xs hover:bg-slate-700/90",
        ghost: "hover:bg-slate-800/70 hover:text-slate-100 text-slate-300",
        link: "text-blue-400 underline-offset-4 hover:underline",
        success: "bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-500/20 shadow-sm",
        amber: "bg-amber-600 text-white hover:bg-amber-500 shadow-amber-500/20 shadow-sm",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-lg px-8 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
