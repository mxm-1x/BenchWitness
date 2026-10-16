// Adapted from Opensource UI's MIT-licensed soft-pill-button.tsx.
// https://github.com/bidyut10/opensourceui/blob/main/components/buttons/soft-pill-button.tsx
import { forwardRef, type ComponentPropsWithoutRef, type ReactNode } from 'react'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

type Variant = 'light' | 'dark'
type Size = 'sm' | 'md' | 'lg'

type Props = Readonly<
  {
    children: ReactNode
    variant?: Variant
    size?: Size
  } & ComponentPropsWithoutRef<'button'>
>

const sizeClasses: Record<Size, string> = {
  sm: 'h-9 gap-1.5 rounded-full px-4 text-xs',
  md: 'h-10 gap-2 rounded-full px-5 text-sm',
  lg: 'h-12 gap-2 rounded-full px-6 text-sm',
}

const variantClasses: Record<Variant, string> = {
  light: 'bg-white text-neutral-800 shadow-[0_2px_4px_rgba(0,0,0,0.06),0_8px_20px_rgba(0,0,0,0.08)] hover:bg-neutral-50 active:bg-neutral-100',
  dark: 'bg-neutral-800 text-white shadow-[0_2px_4px_rgba(0,0,0,0.2),0_8px_20px_rgba(0,0,0,0.25)] hover:bg-neutral-700 active:bg-neutral-900',
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
        'inline-flex cursor-pointer items-center justify-center font-sans font-semibold outline-none select-none transition-[background-color,box-shadow,color,transform] duration-200 motion-reduce:transition-none active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime-300 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40',
        sizeClasses[size], variantClasses[variant], className,
      ))}
      {...props}
    >
      {children}
    </button>
  ),
)

SoftPillButton.displayName = 'SoftPillButton'
