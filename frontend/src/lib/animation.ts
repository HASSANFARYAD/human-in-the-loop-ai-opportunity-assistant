import type { Transition, Variants } from "framer-motion";

export const springTap: Transition = {
  type: "spring",
  stiffness: 400,
  damping: 17,
  mass: 0.8,
};

export const springBouncy: Transition = {
  type: "spring",
  stiffness: 300,
  damping: 20,
};

export const springStagger: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 24,
};

export const easeOut: Transition = {
  type: "tween",
  ease: [0.25, 0.46, 0.45, 0.94],
  duration: 0.4,
};

export const easeInOut: Transition = {
  type: "tween",
  ease: [0.76, 0, 0.24, 1],
  duration: 0.5,
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: easeOut },
};

export const slideUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: easeOut },
};

export const slideDown: Variants = {
  hidden: { opacity: 0, y: -16 },
  visible: { opacity: 1, y: 0, transition: easeOut },
};

export const slideLeft: Variants = {
  hidden: { opacity: 0, x: 24 },
  visible: { opacity: 1, x: 0, transition: easeOut },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.9 },
  visible: { opacity: 1, scale: 1, transition: easeOut },
};

export const scaleInPop: Variants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { type: "spring", stiffness: 400, damping: 22 },
  },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.06, delayChildren: 0.08 },
  },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 260, damping: 24 },
  },
};

export const cardHover3D = {
  rest: { rotateX: 0, rotateY: 0, scale: 1 },
  hover: { scale: 1.02 },
};

export const buttonPress = {
  rest: { scale: 1 },
  hover: { scale: 1.03 },
  tap: { scale: 0.96 },
};

export const iconRotate = {
  rest: { rotate: 0 },
  hover: { rotate: 12, scale: 1.1 },
};
