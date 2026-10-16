"use client";

import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";

const browserThemes = {
  light: {
    shell: "border-neutral-200 bg-white",
    chrome: "border-neutral-200 bg-neutral-50",
    urlBar: "bg-white border border-neutral-200",
    urlText: "text-neutral-500",
    content: "bg-white",
  },
  dark: {
    shell: "border-neutral-800 bg-neutral-900",
    chrome: "border-neutral-800 bg-neutral-900",
    urlBar: "bg-neutral-800 border border-neutral-700",
    urlText: "text-neutral-400",
    content: "bg-neutral-950",
  },
} as const;

export type BrowserTheme = keyof typeof browserThemes;

export type BrowserMockupCardProps = Readonly<
  ComponentPropsWithoutRef<"div"> & {
    theme?: BrowserTheme;
    url?: string;
    children?: ReactNode;
  }
>;

export const BrowserMockupCard = forwardRef<
  HTMLDivElement,
  BrowserMockupCardProps
>(
  (
    {
      className,
      children,
      theme = "light",
      url = "https://benchwitness.local",
      ...props
    },
    ref,
  ) => {
    const styles = browserThemes[theme];

    return (
      <div
        ref={ref}
        data-slot="browser-mockup-card"
        data-theme={theme}
        className={cn(
          "w-full max-w-full min-w-0 overflow-hidden rounded-2xl border font-sans select-none shadow-sm",
          styles.shell,
          className,
        )}
        {...props}
      >
        <div
          className={cn(
            "flex items-center gap-2 border-b px-4 py-3",
            styles.chrome,
          )}
        >
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-rose-400" />
            <div className="h-2.5 w-2.5 rounded-full bg-amber-400" />
            <div className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </div>
          <div
            className={cn(
              "flex h-7 flex-1 items-center rounded-lg px-3 max-w-md mx-auto",
              styles.urlBar,
            )}
          >
            <span
              className={cn("truncate font-mono text-xs", styles.urlText)}
            >
              {url}
            </span>
          </div>
        </div>

        <div className={cn("relative w-full overflow-hidden", styles.content)}>
          <div className="relative size-full">{children}</div>
        </div>
      </div>
    );
  },
);

BrowserMockupCard.displayName = "BrowserMockupCard";
