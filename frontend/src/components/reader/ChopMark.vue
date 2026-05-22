<script setup lang="ts">
withDefaults(
  defineProps<{
    char?: string;
    size?: number;
    rotated?: boolean;
    settled?: boolean;
  }>(),
  { char: "读", size: 28, rotated: true, settled: false },
);
</script>

<template>
  <span
    class="chop"
    :class="{ rotated, settled }"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      fontSize: `${Math.round(size * 0.72)}px`,
    }"
    aria-hidden="true"
  >
    {{ char }}
  </span>
</template>

<style scoped>
.chop {
  /* Inherits .chop utility from global.css for colour/shadow.
     This component just composes positioning + the settle animation. */
  transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
}
.chop.rotated {
  transform: rotate(-3deg);
}
.chop.settled {
  animation: chop-settle 320ms cubic-bezier(0.4, 0, 0.2, 1);
}
@keyframes chop-settle {
  0% {
    transform: rotate(-12deg) scale(1.4);
    opacity: 0;
  }
  60% {
    transform: rotate(-1deg) scale(1.05);
    opacity: 1;
  }
  100% {
    transform: rotate(-3deg) scale(1);
    opacity: 1;
  }
}
</style>
