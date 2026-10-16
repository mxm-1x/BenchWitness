// Adapted from Opensource UI's MIT-licensed soft-pill-button.tsx.
// https://github.com/bidyut10/opensourceui/blob/main/components/buttons/soft-pill-button.tsx
import { forwardRef, type ComponentPropsWithoutRef, type ReactNode } from 'react'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

type Variant = 'light' | 'dark' | 'primary' | 'secondary' | 'outline' | 'coral' | 'mint' | 'ghost'
type Size = 'xs' | 'sm' | 'md' | 'lg'

type Props = Readonly<
  {
    children: ReactNode
    variant?: Variant
    size?: Size
  } & ComponentPropsWithoutRef<'button'>
>

const sizeClasses: Record<Size, string> = {
  xs: 'h-7 gap-1 rounded-full px-3 text-[11px] font-medium',
  sm: 'h-8.5 gap-1.5 rounded-full px-4 text-xs font-semibold',
  md: 'h-10 gap-2 rounded-full px-5 text-sm font-semibold',
  lg: 'h-11.5 gap-2.5 rounded-full px-6 text-sm font-semibold',
}

const variantClasses: Record<Variant, string> = {
  light: 'bg-white text-[#5B2BE8] hover:bg-[#F6F2FE] active:bg-[#ECE4FD] border border-[#DDD0FA] shadow-[0_1px_2px_rgba(91,43,232,0.06)] active:scale-[0.98]',
  dark: 'bg-[#5B2BE8] text-white hover:bg-[#4C1ED1] active:bg-[#3C17A8] shadow-[0_2px_8px_rgba(91,43,232,0.25)] active:scale-[0.98]',
  primary: 'bg-[#5B2BE8] text-white hover:bg-[#4C1ED1] active:bg-[#3C17A8] shadow-[0_2px_8px_rgba(91,43,232,0.25)] active:scale-[0.98]',
  secondary: 'bg-[#F1ECFE] text-[#4C1ED1] hover:bg-[#E6DCFD] active:bg-[#DCD0FB] active:scale-[0.98]',
  outline: 'bg-transparent text-[#5B2BE8] hover:bg-[#F6F2FE] border border-[#DDD0FA] active:scale-[0.98]',
  coral: 'bg-[#FFF0F4] text-[#ED3C65] hover:bg-[#FFE2EA] active:bg-[#FED4DF] border border-[#FECDD8] active:scale-[0.98]',
  mint: 'bg-[#ECFDF5] text-[#059669] hover:bg-[#D1FAE5] active:bg-[#A7F3D0] border border-[#A7F3D0] active:scale-[0.98]',
  ghost: 'bg-transparent text-[#5B2BE8] hover:bg-[#F3ECFD] active:bg-[#ECE4FD]',
}

export const SoftPillButton = forwardRef<HTMLButtonElement, Props>(
  ({ className, children, variant = 'light', size = 'md', type = 'button', disabled, ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      disabled={disabled}
      data-slot="soft-pill-button"
      data-variant={variant}
      data-size={size}
      className={twMerge(clsx(
        'inline-flex cursor-pointer items-center justify-center font-sans tracking-tight transition-all duration-150 outline-none select-none focus-visible:ring-2 focus-visible:ring-[#5B2BE8] focus-visible:ring-offset-2 focus-visible:ring-offset-[#FAF7F2] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none',
        sizeClasses[size], variantClasses[variant], className,
      ))}
      {...props}
    >
      {children}
    </button>
  ),
)

SoftPillButton.displayName = 'SoftPillButton'
