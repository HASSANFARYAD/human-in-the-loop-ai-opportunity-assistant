"use client";

import { type ElementType, type ReactNode, useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform, type HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  fadeIn,
  slideUp,
  scaleIn,
  scaleInPop,
  staggerContainer as staggerVariants,
  staggerItem as staggerItemVariants,
  springTap,
} from "@/lib/animation";

type MotionDivProps = HTMLMotionProps<"div"> & { as?: ElementType };

export function FadeIn({ children, className, ...props }: MotionDivProps) {
  return (
    <motion.div variants={fadeIn} initial="hidden" animate="visible" className={className} {...props}>
      {children}
    </motion.div>
  );
}

export function SlideUp({ children, className, ...props }: MotionDivProps) {
  return (
    <motion.div variants={slideUp} initial="hidden" animate="visible" className={className} {...props}>
      {children}
    </motion.div>
  );
}

export function ScaleIn({ children, className, ...props }: MotionDivProps) {
  return (
    <motion.div variants={scaleIn} initial="hidden" animate="visible" className={className} {...props}>
      {children}
    </motion.div>
  );
}

export function ScaleInPop({ children, className, ...props }: MotionDivProps) {
  return (
    <motion.div variants={scaleInPop} initial="hidden" animate="visible" className={className} {...props}>
      {children}
    </motion.div>
  );
}

export function StaggerContainer({ children, className, ...props }: MotionDivProps) {
  return (
    <motion.div variants={staggerVariants} initial="hidden" animate="visible" className={className} {...props}>
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className, ...props }: MotionDivProps) {
  return (
    <motion.div variants={staggerItemVariants} className={className} {...props}>
      {children}
    </motion.div>
  );
}

export function AnimatedGroup({
  children,
  className,
  staggerDelay = 0.05,
  ...props
}: MotionDivProps & { staggerDelay?: number }) {
  return (
    <motion.div
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: staggerDelay, delayChildren: 0.1 } },
      }}
      initial="hidden"
      animate="visible"
      className={className}
      {...props}
    >
      {Array.isArray(children)
        ? children.map((child, i) => (
            <motion.div
              key={i}
              variants={{
                hidden: { opacity: 0, y: 20 },
                visible: {
                  opacity: 1,
                  y: 0,
                  transition: { type: "spring", stiffness: 260, damping: 24 },
                },
              }}
            >
              {child}
            </motion.div>
          ))
        : children}
    </motion.div>
  );
}

export function HoverTilt3D({
  children,
  className,
  tiltDegree = 8,
  ...props
}: MotionDivProps & { tiltDegree?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0.5);
  const y = useMotionValue(0.5);

  const rotateX = useSpring(useTransform(y, [0, 1], [tiltDegree, -tiltDegree]), {
    stiffness: 300,
    damping: 30,
  });
  const rotateY = useSpring(useTransform(x, [0, 1], [-tiltDegree, tiltDegree]), {
    stiffness: 300,
    damping: 30,
  });

  function handleMouse(e: React.MouseEvent) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    x.set((e.clientX - rect.left) / rect.width);
    y.set((e.clientY - rect.top) / rect.height);
  }

  function handleLeave() {
    x.set(0.5);
    y.set(0.5);
  }

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouse}
      onMouseLeave={handleLeave}
      style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
      className={cn("will-change-transform", className)}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function HoverScale({ children, className, scale = 1.02, ...props }: MotionDivProps & { scale?: number }) {
  return (
    <motion.div
      whileHover={{ scale }}
      whileTap={{ scale: 0.98 }}
      transition={springTap}
      className={cn("cursor-pointer will-change-transform", className)}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function StaggerList({ children, className, ...props }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.04, delayChildren: 0.05 } },
      }}
      initial="hidden"
      animate="visible"
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function StaggerListItem({ children, className, ...props }: MotionDivProps) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, x: -12 },
        visible: { opacity: 1, x: 0, transition: { type: "spring", stiffness: 260, damping: 24 } },
      }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}
