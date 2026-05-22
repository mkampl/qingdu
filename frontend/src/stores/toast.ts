import { defineStore } from "pinia";
import { ref } from "vue";

export type ToastKind = "info" | "success" | "error";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

let nextId = 1;

export const useToastStore = defineStore("toast", () => {
  const toasts = ref<Toast[]>([]);

  function push(message: string, kind: ToastKind = "info", durationMs = 4000) {
    const toast: Toast = { id: nextId++, kind, message };
    toasts.value.push(toast);
    if (durationMs > 0) {
      window.setTimeout(() => dismiss(toast.id), durationMs);
    }
    return toast.id;
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }

  const success = (message: string) => push(message, "success");
  const error = (message: string) => push(message, "error", 6000);
  const info = (message: string) => push(message, "info");

  return { toasts, push, dismiss, success, error, info };
});
