import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface DotGridPatternProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export const DotGridPattern = forwardRef<HTMLDivElement, DotGridPatternProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        data-slot="dot-grid-pattern"
        className={cn(
          "relative isolate overflow-hidden bg-neutral-50 [background-image:radial-gradient(circle,#d4d4d4_1px,transparent_1px)] [background-size:16px_16px]",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);

DotGridPattern.displayName = "DotGridPattern";
