"use client";

import { forwardRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

function RoughFilters() {
  return (
    <svg className="absolute h-0 w-0" aria-hidden="true">
      <defs>
        <filter
          id="hd-rough"
          x="-30%"
          y="-30%"
          width="160%"
          height="160%"
        >
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.045"
            numOctaves={2}
            seed={4}
            result="n"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="n"
            scale={2.6}
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
        <filter
          id="hd-rough-soft"
          x="-30%"
          y="-30%"
          width="160%"
          height="160%"
        >
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.035"
            numOctaves={2}
            seed={11}
            result="n2"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="n2"
            scale={1.5}
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </defs>
    </svg>
  );
}

function WavyDecoration({ className }: Readonly<{ className?: string }>) {
  return (
    <svg
      className={className}
      viewBox="0 0 140 14"
      fill="none"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d="M2,6 Q5.5,3 9,6 T17,6 T25,6 T33,6 T41,6 T49,6 T57,6 T65,6 T73,6 T81,6 T89,6 T97,6 T105,6 T113,6 T121,6 T129,6 T137,6"
        stroke="currentColor"
        strokeWidth={2.2}
        strokeLinecap="round"
        fill="none"
        filter="url(#hd-rough-soft)"
      />
    </svg>
  );
}

function UnderlineDecoration({ className }: Readonly<{ className?: string }>) {
  return (
    <svg
      className={className}
      viewBox="0 0 140 10"
      fill="none"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d="M3,5 C40,7 100,3 137,5"
        stroke="currentColor"
        strokeWidth={2.4}
        strokeLinecap="round"
        fill="none"
        filter="url(#hd-rough-soft)"
      />
    </svg>
  );
}

function HighlightDecoration({ className }: Readonly<{ className?: string }>) {
  return (
    <svg
      className={className}
      viewBox="0 0 140 24"
      fill="none"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d="M2,14 C40,11 100,10 138,13"
        stroke="currentColor"
        strokeWidth={18}
        strokeLinecap="round"
        fill="none"
        opacity={0.5}
        filter="url(#hd-rough-soft)"
      />
    </svg>
  );
}

function CircleDecoration({ className }: Readonly<{ className?: string }>) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 64"
      fill="none"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d="M20,32 C18,12 80,6 138,14 C158,18 156,44 130,52 C84,64 22,58 10,42 C4,28 34,16 68,14"
        stroke="currentColor"
        strokeWidth={2.4}
        strokeLinecap="round"
        fill="none"
        filter="url(#hd-rough)"
      />
    </svg>
  );
}

function BoxDecoration({ className }: Readonly<{ className?: string }>) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 64"
      fill="none"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d="M12,10 C60,6 140,6 188,10 C193,26 193,40 188,54
           C140,58 60,58 12,54 C7,40 7,26 12,10 Z"
        stroke="currentColor"
        strokeWidth={2.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        filter="url(#hd-rough)"
      />
    </svg>
  );
}

const annotationStyles = {
  wavy: {
    wrapper: "relative inline-block whitespace-nowrap",
    Decoration: WavyDecoration,
    decorationClassName:
      "pointer-events-none absolute bottom-[-0.4em] left-[-2%] h-[0.7em] w-[104%]",
    defaultColor: "text-rose-400",
  },
  circle: {
    wrapper: "relative inline-block px-1 whitespace-nowrap",
    Decoration: CircleDecoration,
    decorationClassName:
      "pointer-events-none absolute inset-[-0.6em_-0.55em] h-[calc(100%+1.2em)] w-[calc(100%+1.1em)]",
    defaultColor: "text-emerald-400",
  },
  highlight: {
    wrapper: "relative inline-block whitespace-nowrap",
    Decoration: HighlightDecoration,
    decorationClassName:
      "pointer-events-none absolute inset-x-[-4%] bottom-[-0.08em] z-0 h-[1.15em] w-[108%]",
    defaultColor: "text-amber-200/60",
  },
  underline: {
    wrapper: "relative inline-block whitespace-nowrap",
    Decoration: UnderlineDecoration,
    decorationClassName:
      "pointer-events-none absolute bottom-[-0.32em] left-[-1%] h-[0.5em] w-[102%]",
    defaultColor: "text-neutral-900",
  },
  box: {
    wrapper: "relative inline-block px-[0.4em] whitespace-nowrap",
    Decoration: BoxDecoration,
    decorationClassName:
      "pointer-events-none absolute inset-[-0.4em_-0.4em] h-[calc(100%+0.8em)] w-[calc(100%+0.8em)]",
    defaultColor: "text-violet-400",
  },
} as const;

export type AnnotationVariant = keyof typeof annotationStyles;

export type AnnotatedTextProps = Readonly<{
  children: ReactNode;
  variant?: AnnotationVariant;
  color?: string;
  className?: string;
}>;

export const AnnotatedText = forwardRef<HTMLSpanElement, AnnotatedTextProps>(
  ({ children, variant = "wavy", color, className }, ref) => {
    const resolvedVariant: AnnotationVariant =
      variant in annotationStyles ? variant : "wavy";
    const style = annotationStyles[resolvedVariant];
    const Decoration = style.Decoration;
    const decorationClass = cn(
      style.decorationClassName,
      color ?? style.defaultColor,
    );

    const isBehindText = resolvedVariant === "highlight";

    if (isBehindText) {
      return (
        <>
          <RoughFilters />
          <span ref={ref} className={cn(style.wrapper, className)}>
            <span className="relative z-10 font-normal text-inherit">
              {children}
            </span>
            <Decoration className={cn(decorationClass, "z-0")} />
          </span>
        </>
      );
    }

    return (
      <>
        <RoughFilters />
        <span
          ref={ref}
          className={cn(
            style.wrapper,
            "font-normal text-inherit",
            className,
          )}
        >
          {children}
          <Decoration className={decorationClass} />
        </span>
      </>
    );
  },
);

AnnotatedText.displayName = "AnnotatedText";
