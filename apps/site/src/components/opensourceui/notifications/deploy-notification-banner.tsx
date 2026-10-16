"use client";

import {
  forwardRef,
  useEffect,
  useState,
  type ComponentPropsWithoutRef,
} from "react";

import { cn } from "@/lib/cn";
import { CheckCircle2, X } from "lucide-react";

const EXIT_MS = 260;

export type DeployNotificationBannerProps = Readonly<
  {
    appName?: string;
    project?: string;
    branch?: string;
    duration?: string;
    showTriggerLabel?: string;
    onDismiss?: () => void;
    onShow?: () => void;
  } & ComponentPropsWithoutRef<"output">
>;

export const DeployNotificationBanner = forwardRef<
  HTMLOutputElement,
  DeployNotificationBannerProps
>(
  (
    {
      className,
      appName = "BenchWitness",
      project = "falkordb-graph",
      branch = "main",
      duration = "Just now",
      showTriggerLabel = "Show verification alert",
      onDismiss,
      onShow,
      ...props
    },
    ref,
  ) => {
    const [phase, setPhase] = useState<"open" | "closing" | "closed">("open");

    useEffect(() => {
      if (phase !== "closing") return;
      const timer = globalThis.setTimeout(() => setPhase("closed"), EXIT_MS);
      return () => globalThis.clearTimeout(timer);
    }, [phase]);

    const handleDismiss = () => {
      if (phase !== "open") return;
      setPhase("closing");
      onDismiss?.();
    };

    const handleShow = () => {
      setPhase("open");
      onShow?.();
    };

    if (phase === "closed") {
      return (
        <button
          type="button"
          onClick={handleShow}
          className={cn(
            "cursor-pointer rounded-xl bg-neutral-100 px-3.5 py-1.5 text-xs font-medium text-neutral-700",
            "transition-opacity duration-200 hover:bg-neutral-200",
            className,
          )}
        >
          {showTriggerLabel}
        </button>
      );
    }

    return (
      <output
        ref={ref}
        data-slot="deploy-notification-banner"
        data-phase={phase}
        className={cn(
          "relative block w-full max-w-sm overflow-hidden rounded-2xl border border-neutral-200/80 bg-white/95 p-0 font-sans shadow-md backdrop-blur-xl",
          className,
        )}
        {...props}
      >
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss notification"
          className="absolute top-2.5 right-2.5 z-10 flex size-5 cursor-pointer items-center justify-center rounded-full text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600"
        >
          <X size={12} />
        </button>

        <div className="grid grid-cols-[2.25rem_minmax(0,1fr)] items-start gap-x-3 gap-y-1 p-3.5 pr-8">
          <div className="row-span-2 mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-neutral-900 text-white shadow-xs">
            <CheckCircle2 size={18} className="text-emerald-400" />
          </div>

          <div className="col-start-2 flex min-w-0 items-center justify-between gap-2">
            <p className="truncate text-xs font-bold text-neutral-900">
              {appName}
            </p>
            <span className="shrink-0 text-[10px] text-neutral-400">
              {duration}
            </span>
          </div>

          <p className="col-start-2 text-xs leading-snug text-neutral-600">
            <span className="font-semibold text-neutral-900">{project}</span>
            <span> graph authoritative and ready on </span>
            <span className="font-mono text-neutral-800">{branch}</span>
          </p>
        </div>
      </output>
    );
  },
);

DeployNotificationBanner.displayName = "DeployNotificationBanner";
