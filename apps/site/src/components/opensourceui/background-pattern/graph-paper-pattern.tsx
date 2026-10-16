import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface GraphPaperPatternProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export const GraphPaperPattern = forwardRef<HTMLDivElement, GraphPaperPatternProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        data-slot="graph-paper-pattern"
        className={cn(
          "relative isolate overflow-hidden bg-white [background-image:linear-gradient(to_right,rgba(0,0,0,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.04)_1px,transparent_1px)] [background-size:24px_24px]",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);

GraphPaperPattern.displayName = "GraphPaperPattern";
