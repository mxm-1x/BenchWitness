"use client";

import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";

export type LaptopMockupCardProps = Readonly<
  ComponentPropsWithoutRef<"div"> & {
    children?: ReactNode;
  }
>;

export const LaptopMockupCard = forwardRef<
  HTMLDivElement,
  LaptopMockupCardProps
>(({ className, children, ...props }, ref) => {
  return (
    <div
      ref={ref}
      data-slot="laptop-mockup-card"
      className={cn("flex flex-col items-center font-sans w-full max-w-4xl mx-auto", className)}
      {...props}
    >
      <div className="w-full overflow-hidden rounded-t-2xl border-2 border-b-0 border-neutral-300 shadow-2xl bg-neutral-900 p-2 pb-0">
        <div className="relative overflow-hidden rounded-t-lg bg-neutral-950 aspect-[16/10]">
          <div className="relative size-full overflow-hidden">
            {children}
          </div>
        </div>
      </div>

      <div className="relative h-3 w-[104%] rounded-b-xl bg-gradient-to-b from-neutral-200 to-neutral-300 shadow-md">
        <div
          className="absolute top-0 left-1/2 h-1.5 w-20 -translate-x-1/2 rounded-b-md bg-neutral-400"
          aria-hidden="true"
        />
      </div>
    </div>
  );
});

LaptopMockupCard.displayName = "LaptopMockupCard";
