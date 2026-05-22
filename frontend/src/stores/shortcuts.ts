import { defineStore } from "pinia";
import { ref } from "vue";

export const useShortcutsStore = defineStore("shortcuts", () => {
  const overlayOpen = ref(false);
  function openOverlay() {
    overlayOpen.value = true;
  }
  function closeOverlay() {
    overlayOpen.value = false;
  }
  function toggleOverlay() {
    overlayOpen.value = !overlayOpen.value;
  }
  return { overlayOpen, openOverlay, closeOverlay, toggleOverlay };
});
